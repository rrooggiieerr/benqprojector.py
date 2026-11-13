"""Tests the command prompt of BenQProjector.

Projectors on a serial port, and thus also on a serial to network bridge, have a command
prompt. Projectors with an integrated network interface don't. The library assumes a prompt on
a serial port, and detects it on a network connection.

The detection tests use a simulated projector, the default tests don't need a projector.
"""

import pytest

from benqprojector import BenQProjectorSerial, BenQProjectorTelnet

from .simulation import SimulatedProjector

MODEL = "W1110"

network = pytest.mark.parametrize("url", ["network"], indirect=True)


@network
@pytest.mark.parametrize(
    "projector_simulation",
    [
        pytest.param({"prompt": True}, id="bare_prompt"),
        pytest.param(
            {"prompt": True, "prompt_response": b"\r\n>"}, id="newline_prompt"
        ),
        pytest.param(
            {"prompt": True, "prompt_response": b"\x00\r\n>\x00"},
            id="null_padded_prompt",
        ),
        pytest.param({"prompt": True, "delay": 0.05}, id="delayed_prompt"),
    ],
    indirect=True,
)
async def test_detect_prompt(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """A projector which answers an empty line with a prompt has a prompt."""
    assert await projector._connect()

    assert await projector._detect_prompt() is True
    assert projector_simulation.received == b"\r"


@network
@pytest.mark.parametrize(
    "projector_simulation",
    [
        pytest.param({"prompt": False}, id="silent"),
        pytest.param({"prompt": False, "no_prompt_response": b"\r\n"}, id="empty_line"),
        pytest.param(
            {"prompt": False, "no_prompt_response": b"*Illegal format#\r\n"},
            id="error_response",
        ),
    ],
    indirect=True,
)
async def test_detect_no_prompt(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """A projector which doesn't answer an empty line with a prompt has no prompt."""
    assert await projector._connect()

    assert await projector._detect_prompt() is False
    assert projector_simulation.received == b"\r"


@network
@pytest.mark.simulated_projector(prompt=True, delay=0.5)
async def test_detect_prompt_too_late(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """A prompt which arrives after the read timeout is not detected."""
    assert await projector._connect()

    assert await projector._detect_prompt() is False


@network
@pytest.mark.parametrize(
    ("projector_simulation", "has_prompt"),
    [
        pytest.param({"prompt": False}, False, id="integrated_network"),
        pytest.param({"prompt": True}, True, id="serial_bridge"),
    ],
    indirect=["projector_simulation"],
)
async def test_connect_network(
    projector: BenQProjectorSerial,
    projector_simulation: SimulatedProjector,
    has_prompt: bool,
) -> None:
    """On a network connection the prompt is detected, and commands work with and without it."""
    assert projector.has_prompt is None

    assert await projector.connect()

    assert projector.has_prompt is has_prompt
    assert projector.model == "W1110"
    assert await projector.send_command("pow") == "on"


async def test_connect_serial(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """On a serial port the projector is assumed to have a prompt."""
    assert projector.has_prompt is True

    assert await projector.connect()

    assert projector.has_prompt is True
    assert projector.model == "W1110"


# Defaults, without a projector


@pytest.mark.parametrize(
    ("serial_port", "expected"),
    [
        ("/dev/ttyUSB0", True),
        ("COM3", True),
        ("socket://projector.local:8000", None),
        ("tcp://projector.local:8000", None),
        ("rfc2217://bridge.local:4000", None),
        ("esphome://bridge.local", None),
    ],
)
def test_has_prompt_default(serial_port: str, expected: bool | None) -> None:
    """Local serial ports have a prompt, network connections detect it."""
    projector = BenQProjectorSerial(serial_port, 9600)
    assert projector.has_prompt is expected


def test_telnet_has_prompt() -> None:
    """BenQProjectorTelnet passes has_prompt on and detects it by default."""
    assert BenQProjectorTelnet("projector.local").has_prompt is None
    assert BenQProjectorTelnet("projector.local", has_prompt=True).has_prompt is True
