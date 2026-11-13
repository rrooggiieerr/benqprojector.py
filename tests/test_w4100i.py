"""Tests for the BenQ W4100i projector on a serial to network bridge.

The W4100i ends its answers with \\r only. In standby it drops the first byte it receives
after a pause, to wake up, so a command needs a leading \\r. In standby it refuses *pow=?# with
*Block item#, and for a moment after such a query it also refuses *pow=on#.

Captured in homeassistant-benqprojector issue #64:

    *pow=?#\\r          ->  >*pow=?#\\r\\r\\n*POW=ON#\\r      (on)
    *pow=?#\\r          ->  >                           (standby, first byte dropped)
    \\r*pow=?#\\r        ->  ... *Block item#\\r          (standby)
"""

import asyncio

import pytest

from benqprojector import BenQProjector, BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features
from .simulation import BLOCK_ITEM, SimulatedProjector

ISSUE_64 = "homeassistant-benqprojector#64: W4100i standby behaviour"

# The W4100i is on a serial to network bridge
pytestmark = pytest.mark.parametrize("url", ["network"], indirect=True)


class W4100iSimulation(SimulatedProjector):
    """A W4100i, which refuses to power on for a moment after a power query in standby."""

    POWER_ON_BLOCKED = 1.0  # Seconds, a few seconds on the real projector

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._power_query: float | None = None

    def answer(self, line: str) -> str:
        command = line.strip().lower()
        now = asyncio.get_running_loop().time()
        if self.power == "off" and command == "*pow=?#":
            self._power_query = now
        elif (
            self.power == "off"
            and command == "*pow=on#"
            and self._power_query is not None
            and now - self._power_query < self.POWER_ON_BLOCKED
        ):
            return BLOCK_ITEM
        return super().answer(line)


PROJECTOR_CLASS = W4100iSimulation
MODEL = "W4100i"
VALUES = {"pow": "OFF"}
OPTIONS = {
    "prompt": True,
    "line_ending": b"\r",
    "drop_first_byte": {"off": True},
    "blocked": {"off": {"*pow=?#"}},
}


@pytest.mark.simulated_projector(values={"pow": "ON"})
async def test_connect_on(projector: BenQProjectorSerial) -> None:
    """When on, the projector connects, although its answers end with \\r only."""
    assert await projector.connect()

    assert projector.model == "W4100i"
    assert projector.power_status == BenQProjector.POWERSTATUS_ON


@pytest.mark.xfail(strict=True, reason=ISSUE_64)
async def test_prompt_detected_in_standby(projector: BenQProjectorSerial) -> None:
    """In standby the prompt of the bridge is detected, although the first byte is dropped."""
    assert await projector.connect()

    assert projector.has_prompt is True


@pytest.mark.xfail(strict=True, reason=ISSUE_64)
async def test_standby(projector: BenQProjectorSerial) -> None:
    """In standby the projector is off, although it refuses the power query."""
    assert await projector.connect()

    assert projector.power_status == BenQProjector.POWERSTATUS_OFF


@pytest.mark.xfail(strict=True, reason=ISSUE_64)
async def test_turn_on_from_standby(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """The projector turns on from standby."""
    assert await projector.connect()

    assert await projector.turn_on()
    assert projector_simulation.get("pow") == "ON"


async def test_command_after_pause(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """In standby a command after a pause is answered, although its first byte is dropped."""
    assert await projector.connect()
    await asyncio.sleep(projector_simulation.idle_time + 0.1)

    assert await projector.send_command("modelname") == "w4100i"


@pytest.mark.xfail(
    strict=True, reason="homeassistant-benqprojector#64: seco unsupported"
)
async def test_lamp_modes(projector: BenQProjectorSerial) -> None:
    """The W4100i doesn't support the SmartEco lamp mode, seco."""
    assert await projector.connect()

    assert projector.lamp_modes is not None
    assert "seco" not in projector.lamp_modes


@pytest.mark.simulated_projector(values={"pow": "ON"})
async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds the commands and modes of the configuration."""
    await assert_examine(projector, examine, expected_features(MODEL))
