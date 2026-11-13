"""Tests for the BenQ W4000i projector, also sold as HT4550i, on its integrated network interface.

The W4000i has no prompt and doesn't echo commands. Its answers end with # and nothing after
it, and it spells *Unsupported Item# with a capital I.

Seen in benqprojector.py issue #24:

    *pow=?#\\r  ->  *POW=ON#
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

# The W4000i is on its integrated network interface
pytestmark = pytest.mark.parametrize("url", ["network"], indirect=True)

MODEL = "W4000i"
VALUES = {"macaddr": "0:17:CA:E4:8D:30", "ltim": "140"}
OPTIONS = {
    "prompt": False,
    "echo": False,
    "line_ending": b"",
    "raw_responses": {"*ltim2=?#": b"*Unsupported Item#"},
}


async def test_connect(projector: BenQProjectorSerial, hardware: bool) -> None:
    """The projector connects without a prompt and without command echoes."""
    assert await projector.connect()

    assert projector.has_prompt is False
    assert projector.model == "W4000i"
    assert projector.power_status == BenQProjector.POWERSTATUS_ON
    # The unique id is the MAC address
    assert projector.unique_id is not None
    assert projector.unique_id.count(":") == 5
    if not hardware:
        assert projector.unique_id == "0:17:ca:e4:8d:30"


async def test_lamp_time(projector: BenQProjectorSerial, hardware: bool) -> None:
    """An answer which ends with # and nothing after it is read."""
    assert await projector.connect()

    lamp_time = await projector.send_command("ltim")
    assert lamp_time is not None
    assert lamp_time.isdigit()
    if not hardware:
        assert lamp_time == "140"


async def test_unsupported_item(projector: BenQProjectorSerial) -> None:
    """*Unsupported Item#, with a capital I, is an unsupported item."""
    assert await projector.connect()

    with pytest.raises(BenQUnsupportedItemError):
        await projector._send_command(BenQCommand("ltim2"), check_supported=False)


async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds the commands and modes of the configuration, without echoes."""
    await assert_examine(projector, examine, expected_features(MODEL))
