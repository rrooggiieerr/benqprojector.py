"""Tests the serial connection to a projector.

The tests run against a simulated W1110 on a simulated serial port and on a simulated network
connection, or with --hardware against the real projector at the --hardware url. The settings
the connection is opened with, which a simulated serial port ignores, are checked on a mock.

Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import asyncio
from collections.abc import AsyncIterator
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
import serialx

from benqprojector import END_OF_LINE
from benqprojector.benqconnection import BenQSerialConnection

from .simulation import SimulatedProjector, serial_simulation, tcp_simulation

logger = logging.getLogger(__name__)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Run the tests over a serial and a network connection, or once over the --hardware url."""
    if "connection" in metafunc.fixturenames and not metafunc.config.getoption(
        "--hardware"
    ):
        metafunc.parametrize("connection", ["serial", "network"], indirect=True)


@pytest.fixture
async def connection(
    request: pytest.FixtureRequest, hardware: bool, baud_rate: int
) -> AsyncIterator[BenQSerialConnection]:
    """A connection to the real or simulated projector, closed at the end of the test."""
    if hardware:
        connection = BenQSerialConnection(
            request.config.getoption("--hardware"), baud_rate
        )
    else:
        if request.param == "network":
            url = await tcp_simulation()
        else:
            url = await serial_simulation()
        SimulatedProjector(url, "W1110")
        connection = BenQSerialConnection(url, 9600)
    yield connection
    await connection.close()


@pytest.mark.parametrize(
    ("url", "network"),
    [
        pytest.param("/dev/tty.usbserial-10", False, id="serial_port"),
        pytest.param("socket://projector.local:8000", True, id="socket"),
        pytest.param("tcp://projector.local:8000", True, id="tcp"),
        pytest.param("rfc2217://projector.local:8000", True, id="rfc2217"),
        pytest.param("esphome://esphome.local/?port_name=uart0", True, id="esphome"),
    ],
)
def test_is_network(url: str, network: bool) -> None:
    """A url is a network connection, a path a serial port."""
    assert BenQSerialConnection(url, 115200).is_network is network


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("/dev/tty.usbserial-10", id="serial_port"),
        pytest.param(
            "esphome-hass://esphome/abc123?port_name=uart0", id="esphome_hass"
        ),
    ],
)
async def test_open_settings(url: str) -> None:
    """The connection is opened with the url as given, the baud rate and 8N1."""
    connection = BenQSerialConnection(url, 115200)
    writer = Mock()
    writer.wait_closed = AsyncMock()

    with patch(
        "benqprojector.benqconnection.serialx.open_serial_connection",
        AsyncMock(return_value=(Mock(), writer)),
    ) as open_serial_connection:
        assert await connection.open()

    assert connection.is_open()
    open_serial_connection.assert_awaited_once_with(
        url=url,
        baudrate=115200,
        byte_size=serialx.EIGHTBITS,
        parity=serialx.Parity.NONE,
        stopbits=serialx.StopBits.ONE,
        timeout=1,
    )

    await connection.close()


async def _read_lines(connection: BenQSerialConnection) -> list[bytes]:
    """The lines the projector sends, read like the library does."""
    lines = []
    for _ in range(10):
        line = await connection.readuntil(END_OF_LINE)
        if not line:
            break
        lines.append(line)
    return lines


async def test_open(connection: BenQSerialConnection) -> None:
    """The connection opens."""
    assert await connection.open()
    assert connection.is_open()


async def test_close(connection: BenQSerialConnection) -> None:
    """The connection closes."""
    await connection.open()
    assert await connection.close()
    assert not connection.is_open()


async def test_read(connection: BenQSerialConnection) -> None:
    """The first byte of the answer to a command is read."""
    await connection.open()
    await connection.write(b"\r*pow=?#\r")
    result = await connection.read(1)
    logger.debug(result)
    assert len(result) == 1


async def test_write(connection: BenQSerialConnection) -> None:
    """A written command is answered, every line read ends with # or a newline."""
    await connection.open()
    await connection.write(b"\r*pow=?#\r")

    lines = await _read_lines(connection)
    logger.debug(lines)
    assert lines
    assert all(line.endswith(END_OF_LINE) for line in lines)
    assert any(line.strip().startswith(b"*POW=") for line in lines)


async def test_reset(connection: BenQSerialConnection) -> None:
    """Resetting the connection discards what was received."""
    await connection.open()
    await connection.write(b"\r*pow=?#\r")
    await asyncio.sleep(0.5)

    assert await connection.reset()
    assert await connection.read(1) == b""
