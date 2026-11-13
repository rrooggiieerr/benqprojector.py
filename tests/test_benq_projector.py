"""Tests the BenQ projector library on any projector.

Every test runs against a simulated W1110 with and without a command prompt, or with
--hardware against the real projector at the --hardware url, see the `connected_projector`
fixture in conftest.py. The tests don't depend on the state of the projector, but it has to
be on for the source, volume and menu tests, they are skipped when a real projector is off. The
tests set what they change back: the volume and mute to what they were, the menu closed. The
power and connection tests only run against the simulated projector.

Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import asyncio
from collections.abc import AsyncIterator

import pytest

import benqprojector
from benqprojector import (
    BenQCommand,
    BenQProjector,
    BenQProjectorSerial,
    BenQUnsupportedItemError,
)

from .conftest import RestoreSettings
from .simulation import SimulatedProjector

MODEL = "W1110"
VALUES = {
    "vol": "5",
    # The menu navigation commands are not in the W1110 configuration
    "up": "",
    "down": "",
    "left": "",
    "right": "",
}

# Real projectors need some time between menu commands
DELAY = 0.2

# A real projector refuses these commands while it is off, the test is skipped then
needs_power_on = pytest.mark.simulated_projector(values={"pow": "ON"})


# Commands


async def test_status(connected_projector: BenQProjectorSerial) -> None:
    """All known states are read."""
    assert await connected_projector.update()
    assert connected_projector.model is not None


@pytest.mark.simulated_projector(values={"pow": "OFF"})
async def test_connect_off(connected_projector: BenQProjectorSerial) -> None:
    """The projector connects while off."""
    assert connected_projector.power_status == BenQProjector.POWERSTATUS_OFF


async def test_send_command(connected_projector: BenQProjectorSerial) -> None:
    """A command gets its response."""
    assert await connected_projector.send_command("pow") in ("on", "off")


async def test_send_raw_command(connected_projector: BenQProjectorSerial) -> None:
    """A raw command gets its raw response."""
    response = await connected_projector.send_raw_command("*pow=?#")
    assert response is not None
    assert response.lower() in ("*pow=on#", "*pow=off#")


async def test_unsupported_command(connected_projector: BenQProjectorSerial) -> None:
    """A command the projector doesn't know gives no response."""
    response = await connected_projector.send_command(
        "nonexisting", check_supported=False
    )
    assert response is None
    # The next command gets its own response
    assert await connected_projector.send_command("pow") in ("on", "off")


@needs_power_on
async def test_select_video_source(connected_projector: BenQProjectorSerial) -> None:
    """Selecting the current video source succeeds."""
    await connected_projector.update_video_source()
    source = connected_projector.video_source
    assert source is not None

    assert await connected_projector.select_video_source(source)
    assert connected_projector.video_source == source


# Volume


@needs_power_on
async def test_mute(
    connected_projector: BenQProjectorSerial, restore_settings: RestoreSettings
) -> None:
    """The projector is muted."""
    await restore_settings(connected_projector, "vol", "mute")
    await connected_projector.unmute()
    assert await connected_projector.mute()
    assert connected_projector.muted is True


@needs_power_on
async def test_unmute(
    connected_projector: BenQProjectorSerial, restore_settings: RestoreSettings
) -> None:
    """The projector is unmuted."""
    await restore_settings(connected_projector, "vol", "mute")
    await connected_projector.mute()
    assert await connected_projector.unmute()
    assert connected_projector.muted is False


@needs_power_on
async def test_volume_up(
    connected_projector: BenQProjectorSerial, restore_settings: RestoreSettings
) -> None:
    """The volume goes up by one."""
    await restore_settings(connected_projector, "vol", "mute")
    await connected_projector.volume_level(10)
    volume = connected_projector.volume
    assert volume is not None

    assert await connected_projector.volume_up()
    assert connected_projector.volume == volume + 1


@needs_power_on
async def test_volume_down(
    connected_projector: BenQProjectorSerial, restore_settings: RestoreSettings
) -> None:
    """The volume goes down by one."""
    await restore_settings(connected_projector, "vol", "mute")
    await connected_projector.volume_level(10)
    volume = connected_projector.volume
    assert volume is not None

    assert await connected_projector.volume_down()
    assert connected_projector.volume == volume - 1


@needs_power_on
@pytest.mark.parametrize(
    ("start_level", "target_level"),
    [(0, 20), (20, 0)],
    ids=["up", "down"],
)
async def test_volume_level(
    connected_projector: BenQProjectorSerial,
    restore_settings: RestoreSettings,
    start_level: int,
    target_level: int,
) -> None:
    """The volume is set to a level."""
    await restore_settings(connected_projector, "vol", "mute")
    await connected_projector.volume_level(start_level)

    assert await connected_projector.volume_level(target_level)
    assert connected_projector.volume == target_level


# Menu


@pytest.fixture
async def menu_projector(
    connected_projector: BenQProjectorSerial,
) -> AsyncIterator[BenQProjectorSerial]:
    """A connected projector with its menu closed, before and after the test.

    The menu tests are skipped when the projector's configuration doesn't have the menu command.
    """
    if not connected_projector.supports_command("menu"):
        pytest.skip(f"{connected_projector.model} doesn't support the menu command")
    await connected_projector.send_command("menu", "off")
    await asyncio.sleep(DELAY)
    yield connected_projector
    await connected_projector.send_command("menu", "off")
    await asyncio.sleep(DELAY)


async def _menu_status(projector: BenQProjectorSerial) -> str | None:
    """The menu state the projector reports.

    The test is skipped when the projector doesn't report the menu state, like the W1110 and
    the MS521PTS537, which answer *menu=?# with *Unsupported item#.
    """
    try:
        return await projector._send_command(BenQCommand("menu", "?"))
    except BenQUnsupportedItemError:
        pytest.skip(f"{projector.model} doesn't report the menu state")


@needs_power_on
async def test_menu_off_status(menu_projector: BenQProjectorSerial) -> None:
    """The closed menu is reported."""
    response = await _menu_status(menu_projector)
    await asyncio.sleep(DELAY)
    assert response == "off"


@needs_power_on
async def test_menu_on_status(menu_projector: BenQProjectorSerial) -> None:
    """The open menu is reported."""
    await menu_projector.send_command("menu", "on")
    await asyncio.sleep(DELAY)
    response = await _menu_status(menu_projector)
    await asyncio.sleep(DELAY)
    assert response == "on"


@needs_power_on
async def test_menu_on(menu_projector: BenQProjectorSerial) -> None:
    """The menu opens."""
    assert await menu_projector.send_command("menu", "on") == "on"


@needs_power_on
async def test_menu_off(menu_projector: BenQProjectorSerial) -> None:
    """The menu closes."""
    await menu_projector.send_command("menu", "on")
    await asyncio.sleep(DELAY)
    assert await menu_projector.send_command("menu", "off") == "off"


@needs_power_on
@pytest.mark.parametrize(
    ("setup_command", "command"),
    [
        ("*down#", "*up#"),
        (None, "*down#"),
        ("*right#", "*left#"),
        (None, "*right#"),
    ],
    ids=["up", "down", "left", "right"],
)
async def test_menu_navigation(
    menu_projector: BenQProjectorSerial, setup_command: str | None, command: str
) -> None:
    """The menu is navigated with raw commands."""
    await menu_projector.send_command("menu", "on")
    await asyncio.sleep(DELAY)
    if setup_command:
        await menu_projector.send_raw_command(setup_command)
        await asyncio.sleep(DELAY)
    response = await menu_projector.send_raw_command(command)
    assert response is not None
    assert response.lower() == command


# Power, only against the simulated projector, so a real projector is never switched


@pytest.mark.simulated_projector(values={"pow": "OFF"})
async def test_turn_on(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """Turning the projector on sends the command and starts powering on."""
    assert await projector.connect()

    assert await projector.turn_on()
    assert projector_simulation.get("pow") == "ON"
    assert projector.power_status == BenQProjector.POWERSTATUS_POWERINGON


async def test_turn_off(
    projector: BenQProjectorSerial, projector_simulation: SimulatedProjector
) -> None:
    """Turning the projector off sends the command and starts powering off."""
    assert await projector.connect()

    assert await projector.turn_off()
    assert projector_simulation.get("pow") == "OFF"
    assert projector.power_status == BenQProjector.POWERSTATUS_POWERINGOFF


# Connection


async def test_cable_pulled(
    projector: BenQProjectorSerial,
    projector_simulation: SimulatedProjector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a cable a command gets no response, once it is back commands work again."""
    # Don't wait the full response timeout
    monkeypatch.setattr(benqprojector, "_RESPONSE_TIMEOUT", 0.5)
    assert await projector.connect()

    projector_simulation.unplug()
    assert await projector.send_command("pow") is None

    projector_simulation.plug()
    assert await projector.send_command("pow") == "on"
