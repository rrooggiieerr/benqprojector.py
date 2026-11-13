"""Tests for the BenQ W1110 projector.

When off, the W1110 answers directpower without the leading *, DIRECTPOWER=OFF#. It positions
the menu in the center with cen, where other models use center.

The W1110 is also the projector of the tests in test_benq_projector*.py.
"""

import pytest

from benqprojector import BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features
from .simulation import SimulatedProjector

MODEL = "W1110"
OPTIONS = {
    "raw_responses": {
        "*directpower=?#": {"off": b"*directpower=?#\r\nDIRECTPOWER=OFF#\r\n"}
    }
}


@pytest.mark.simulated_projector(values={"pow": "OFF", "directpower": "OFF"})
async def test_direct_power_off(projector: BenQProjectorSerial) -> None:
    """When off, direct power is read without the leading *."""
    assert await projector.connect()

    assert await projector.send_command("directpower") == "off"


@pytest.mark.simulated_projector(values={"directpower": "ON"})
async def test_direct_power_on(projector: BenQProjectorSerial) -> None:
    """When on, direct power is read as usual."""
    assert await projector.connect()

    assert await projector.send_command("directpower") == "on"


async def test_menu_position_center(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """The menu is positioned in the center with cen."""
    assert await projector.connect()

    assert projector.menu_positions is not None
    assert "cen" in projector.menu_positions
    assert "center" not in projector.menu_positions
    assert await projector.send_command("menuposition", "cen") == "cen"
    assert projector_simulation.get("menuposition") == "CEN"


async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds the commands and modes of the configuration."""
    await assert_examine(projector, examine, expected_features(MODEL))
