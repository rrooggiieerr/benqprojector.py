"""Tests for the BenQ X3000i projector.

The X3000i doesn't echo commands, it sends an empty line instead. It positions the menu in the
center with center, where the W1110 uses cen.
"""

from benqprojector import BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features
from .simulation import SimulatedProjector, both_transports

MODEL = "X3000i"
OPTIONS = {"echo": b"\r\n"}


@both_transports
async def test_commands_without_echo(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """Commands work although the projector sends an empty line instead of an echo."""
    assert await projector.connect()

    assert projector.model == "X3000i"
    assert await projector.send_command("pow") == "on"
    assert await projector.select_video_source("hdmi2")
    assert projector_simulation.get("sour") == "HDMI2"


async def test_menu_position_center(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """The menu is positioned in the center with center."""
    assert await projector.connect()

    assert projector.menu_positions is not None
    assert "center" in projector.menu_positions
    assert "cen" not in projector.menu_positions
    assert await projector.send_command("menuposition", "center") == "center"
    assert projector_simulation.get("menuposition") == "CENTER"


async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds the commands and modes of the configuration, without echoes."""
    await assert_examine(projector, examine, expected_features(MODEL))
