"""
Shared pytest configuration and fixtures for the BenQ projector tests.

Most tests talk to a real projector over a serial port or a Telnet bridge. Those
tests are marked with ``hardware`` and are skipped unless pytest is run with
``--hardware``. The connection details can be set on the command line:

    pytest --hardware --serial-port /dev/tty.usbserial-10 --baud-rate 115200
    pytest --hardware --telnet-host benqprojector-livingroom.local
"""

import pytest

DEFAULT_SERIAL_PORT = "/dev/tty.usbserial-10"
DEFAULT_BAUD_RATE = 115200
DEFAULT_TELNET_HOST = "benqprojector-livingroom.local"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line options for the hardware tests."""
    group = parser.getgroup("benqprojector", "BenQ projector hardware tests")
    group.addoption(
        "--hardware",
        action="store_true",
        default=False,
        help="Run tests that need a real BenQ projector.",
    )
    group.addoption(
        "--serial-port",
        default=DEFAULT_SERIAL_PORT,
        help=f"Serial port of the projector (default: {DEFAULT_SERIAL_PORT}).",
    )
    group.addoption(
        "--baud-rate",
        type=int,
        default=DEFAULT_BAUD_RATE,
        help=f"Baud rate of the serial port (default: {DEFAULT_BAUD_RATE}).",
    )
    group.addoption(
        "--telnet-host",
        default=DEFAULT_TELNET_HOST,
        help=f"Host name of the Telnet bridge (default: {DEFAULT_TELNET_HOST}).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip the hardware tests unless --hardware is given."""
    if config.getoption("--hardware"):
        return

    skip_hardware = pytest.mark.skip(reason="needs a real projector, use --hardware")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hardware)


@pytest.fixture
def serial_port(request: pytest.FixtureRequest) -> str:
    """Serial port the projector is connected to."""
    return request.config.getoption("--serial-port")


@pytest.fixture
def baud_rate(request: pytest.FixtureRequest) -> int:
    """Baud rate of the serial port."""
    return request.config.getoption("--baud-rate")


@pytest.fixture
def telnet_host(request: pytest.FixtureRequest) -> str:
    """Host name of the Telnet bridge the projector is connected to."""
    return request.config.getoption("--telnet-host")
