"""Tests for the BenQ MS521PTS537 projector.

The MS521PTS537 opens and closes the menu, but doesn't report the menu state: it answers
*menu=?# with *Unsupported item#, followed by a null byte.

Captured on a real MS521PTS537 over serial:

    \\r*menu=on#\\r  ->  >*menu=on#\\r\\r\\n*MENU=ON#\\r\\n
    \\r*menu=?#\\r   ->  >*menu=?#\\r\\r\\n*Unsupported item#\\r\\n\\x00
"""

import asyncio

import pytest

from benqprojector import BenQCommand, BenQProjectorSerial, BenQUnsupportedItemError
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features

MODEL = "MS521PTS537"
VALUES = {"pow": "ON"}
OPTIONS = {
    "raw_responses": {
        "*menu=?#": b">*menu=?#\r\r\n*Unsupported item#\r\n\x00",
    }
}

# A real projector needs some time between menu commands
DELAY = 0.2


async def test_menu(projector: BenQProjectorSerial) -> None:
    """The menu opens and closes."""
    assert await projector.connect()

    try:
        assert await projector.send_command("menu", "on") == "on"
        await asyncio.sleep(DELAY)
    finally:
        assert await projector.send_command("menu", "off") == "off"


async def test_menu_status_unsupported(projector: BenQProjectorSerial) -> None:
    """The menu state isn't reported, and the null byte after the error is ignored."""
    assert await projector.connect()

    with pytest.raises(BenQUnsupportedItemError):
        await projector._send_command(BenQCommand("menu", "?"))
    assert await projector.send_command("pow") == "on"


async def test_examine(
    projector: BenQProjectorSerial, examine: BenQProjectorExamine
) -> None:
    """Examining finds the commands and modes of the configuration."""
    await assert_examine(projector, examine, expected_features(MODEL))
