"""Tests the detection of the commands and modes a projector supports.

The tests run against a simulated W1110 with and without a command prompt, or with
--hardware against the real projector, see the `connected_projector` fixture in conftest.py.
Against the simulated W1110 the detected commands and modes are known exactly.

Created on 16 Jan 2023

@author: Rogier van Staveren
"""

import asyncio

import pytest

from benqprojector import BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import (
    MODE_COMMANDS,
    NO_PICTURE,
    PICTURE_MODES,
    expected_features,
    remove_examine_pauses,
)
from .simulation import SimulatedProjector

MODEL = "W1110"

# A real projector refuses most commands and modes while it is off, the tests are skipped then
pytestmark = pytest.mark.simulated_projector(values={"pow": "ON"})


@pytest.fixture
async def connected_examine(
    connected_projector: BenQProjectorSerial,
    hardware: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> BenQProjectorExamine:
    """An examiner of the connected projector."""
    if not hardware:
        remove_examine_pauses(monkeypatch)

    await connected_projector.update()
    return BenQProjectorExamine(connected_projector)


async def test_detect_commands(
    connected_examine: BenQProjectorExamine, hardware: bool
) -> None:
    """The supported commands are detected."""
    commands = await connected_examine.detect_commands()
    assert commands is not None
    assert "pow" in commands
    if not hardware:
        assert set(commands) == expected_features(MODEL)["commands"]


@pytest.mark.parametrize("key", list(MODE_COMMANDS))
async def test_detect_modes(
    connected_examine: BenQProjectorExamine,
    connected_projector: BenQProjectorSerial,
    hardware: bool,
    key: str,
) -> None:
    """The supported modes are detected."""
    # The modes are only detected for the supported commands
    await connected_examine.detect_commands()

    modes = await getattr(connected_examine, f"detect_{key}")()
    assert modes is not None
    if key in PICTURE_MODES and connected_projector.supports_command(
        MODE_COMMANDS[key]
    ):
        assert modes, f"No {key} detected, {NO_PICTURE}"
    if not hardware:
        assert set(modes) == expected_features(MODEL)[key]


async def test_detect_video_sources(
    connected_examine: BenQProjectorExamine, connected_projector: BenQProjectorSerial
) -> None:
    """The detected video sources include the current one."""
    await connected_projector.update_video_source()
    current = connected_projector.video_source

    await connected_examine.detect_commands()
    sources = await connected_examine.detect_video_sources()
    assert current in sources


async def test_modes_restored(
    connected_examine: BenQProjectorExamine, connected_projector: BenQProjectorSerial
) -> None:
    """Detecting the modes leaves every setting as it was."""
    # The modes are only detected for the supported commands
    await connected_examine.detect_commands()
    commands = [
        command
        for command in MODE_COMMANDS.values()
        if connected_projector.supports_command(command)
    ]
    before = {
        command: await connected_projector.send_command(command) for command in commands
    }

    for key in MODE_COMMANDS:
        await getattr(connected_examine, f"detect_{key}")()

    after = {
        command: await connected_projector.send_command(command) for command in commands
    }
    assert after == before


# Restoring the settings, only against the simulated projector


async def test_examine_restores_after_cancel(
    projector: BenQProjectorSerial,
    projector_simulation: SimulatedProjector,
    examine: BenQProjectorExamine,
) -> None:
    """When detecting the video sources is cancelled, the original source is restored."""
    assert await projector.connect()
    await examine.detect_commands()
    original = projector_simulation.get("sour")

    # Slow the projector down, so the detection is cancelled while trying the sources
    projector_simulation.delay = 0.05
    task = asyncio.create_task(examine.detect_video_sources())
    await asyncio.sleep(0.3)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert projector_simulation.get("sour") == original


async def test_examine_restore_refused(
    projector: BenQProjectorSerial,
    projector_simulation: SimulatedProjector,
    examine: BenQProjectorExamine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A refused restore is retried with the exact reported value, and then logged."""
    assert await projector.connect()
    await examine.detect_commands()
    original = projector_simulation.get("sour")
    assert original == "HDMI"
    projector_simulation.blocked = {f"*sour={original.lower()}#"}

    await examine.detect_video_sources()

    # The restore sends the source exactly as reported, the detection sends it lowercase
    assert projector_simulation.commands.count(f"*sour={original}#") == 3
    assert f"Unable to restore sour to {original}" in caplog.text
