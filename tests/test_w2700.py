"""Tests for the BenQ W2700 projector, also sold as HT3550.

Over serial the W2700 answers an empty line with the prompt in standby, but not while its lamp
is on. It still sends the prompt in front of the echo of a command, and answers commands, which
the library sends without waiting for the prompt. It answers some unsupported commands with
*Unsupporteditem#, without a space.

Captured in homeassistant-benqprojector issue #67:

    \\r*pow=?#\\r  ->  >*pow=?#\\r\\r\\n*POW=ON#\\r\\n
    \\r          ->  nothing, while the lamp is on
"""

import pytest

from benqprojector import (
    BenQCommand,
    BenQProjector,
    BenQProjectorSerial,
    BenQUnsupportedItemError,
)
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features
from .simulation import SimulatedProjector

MODEL = "W2700"
VALUES = {"pow": "OFF"}
OPTIONS = {
    "empty_line_prompt": {"on": False, "off": True},
    "raw_responses": {"*micvol=?#": b">*micvol=?#\r\r\n*Unsupporteditem#\r\n"},
}


async def test_connect_standby(projector: BenQProjectorSerial) -> None:
    """In standby the projector connects."""
    assert await projector.connect()

    assert projector.model == "W2700"
    assert projector.power_status == BenQProjector.POWERSTATUS_OFF


@pytest.mark.simulated_projector(values={"pow": "ON"})
async def test_connect_lamp_on(projector: BenQProjectorSerial) -> None:
    """With the lamp on the projector connects."""
    assert await projector.connect()

    assert projector.power_status == BenQProjector.POWERSTATUS_ON


async def test_status_after_turn_on(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """After turning the projector on, its state can still be read."""
    assert await projector.connect()
    assert await projector.turn_on()
    assert projector_simulation.get("pow") == "ON"

    assert await projector.send_command("pow") == "on"


async def test_unsupported_item_without_space(projector: BenQProjectorSerial) -> None:
    """*Unsupporteditem#, without a space, is an unsupported item."""
    assert await projector.connect()

    with pytest.raises(BenQUnsupportedItemError):
        await projector._send_command(BenQCommand("micvol"), check_supported=False)


@pytest.mark.simulated_projector(values={"pow": "ON"})
async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds the commands and modes of the configuration."""
    await assert_examine(projector, examine, expected_features(MODEL))
