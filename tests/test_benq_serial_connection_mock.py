from unittest.mock import AsyncMock, Mock, patch

import pytest
import serialx

from benqprojector.benqconnection import BenQSerialConnection

BAUD_RATE = 115200


@pytest.mark.parametrize(
    "serial_port",
    [
        pytest.param("/dev/tty.usbserial-10", id="serial_path"),
        pytest.param("esphome-hass://esphome/abc123?port_name=uart0", id="serial_uri"),
    ],
)
async def test_open(serial_port):
    connection = BenQSerialConnection(serial_port, BAUD_RATE)
    reader = Mock()
    writer = Mock()
    writer.close = Mock()
    writer.wait_closed = AsyncMock()

    with patch(
        "benqprojector.benqconnection.serialx.open_serial_connection",
        AsyncMock(return_value=(reader, writer)),
    ) as open_serial_connection:
        result = await connection.open()

    assert result
    assert connection.is_open()
    open_serial_connection.assert_awaited_once_with(
        url=serial_port,
        baudrate=BAUD_RATE,
        byte_size=serialx.EIGHTBITS,
        parity=serialx.Parity.NONE,
        stopbits=serialx.StopBits.ONE,
    )

    await connection.close()
