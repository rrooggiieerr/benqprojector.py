"""Tests for the BenQ TK700STi projector.

Over serial, or a serial to network bridge, the TK700STi answers an empty line with the prompt
in standby, but not once the lamp is on. It does keep answering commands, which the library
sends without waiting for the prompt. It refuses the second lamp query, *ltim2=?#, as it has
one lamp. The TK700STi has no configuration file.

Described in benqprojector.py pull request #61. The W5700 (#58) and the W2700/HT3550
(homeassistant-benqprojector#67) lose their prompt the same way.
"""

import pytest

from benqprojector import BenQProjector, BenQProjectorSerial

from .simulation import BLOCK_ITEM, SimulatedProjector

MODEL = "TK700STi"
VALUES = {"pow": "OFF", "ltim": "1000"}
OPTIONS = {
    "empty_line_prompt": {"on": False, "off": True},
    "raw_responses": {
        "*ltim2=?#": f">*ltim2=?#\r\r\n{BLOCK_ITEM}\r\n".encode("ascii"),
    },
}


async def test_connect_standby(projector: BenQProjectorSerial) -> None:
    """In standby the projector connects."""
    assert await projector.connect()

    assert projector.model == "TK700STi"
    assert projector.power_status == BenQProjector.POWERSTATUS_OFF


async def test_second_lamp_refused(projector: BenQProjectorSerial) -> None:
    """The refused second lamp query gives no lamp time, and the next command still works."""
    assert await projector.connect()

    assert await projector.send_command("ltim2", check_supported=False) is None
    assert await projector.send_command("ltim") is not None
    assert await projector.send_command("pow") == "off"


@pytest.mark.simulated_projector(values={"pow": "ON"})
async def test_connect_lamp_on(projector: BenQProjectorSerial) -> None:
    """With the lamp on the projector connects."""
    assert await projector.connect()

    assert projector.power_status == BenQProjector.POWERSTATUS_ON


@pytest.mark.simulated_projector(values={"pow": "ON"})
async def test_commands_lamp_on(projector: BenQProjectorSerial) -> None:
    """With the lamp on commands keep working, one after the other."""
    assert await projector.connect()

    for _ in range(3):
        assert await projector.send_command("pow") == "on"
        assert await projector.send_command("ltim") is not None


async def test_status_after_turn_on(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """After turning the projector on, its state can still be read."""
    assert await projector.connect()
    assert await projector.turn_on()
    assert projector_simulation.get("pow") == "ON"

    assert await projector.send_command("pow") == "on"
