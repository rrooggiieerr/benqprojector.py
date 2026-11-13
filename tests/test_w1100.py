"""Tests for the BenQ W1100 projector.

The W1100 answers ltim, bri, con, color and sharp with a space before the value and without a
closing #, e.g. *ltim= 1386 instead of *LTIM=1386#, and the lamp time with a null byte before
the value. It echoes bri, con, color and sharp twice, with empty lines in between.

Seen in benqprojector.py issue #5:

    >*ltim=?#\\r\\n\\r\\n*ltim= 1386
    >*bri=?#\\r\\n\\r\\n*bri=?#\\r\\n\\r\\n*bri= 51
"""

import pytest

from benqprojector import BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features


def _double_echo(command: str, value: str) -> bytes:
    return (
        f">*{command}=?#\r\n\r\n*{command}=?#\r\n\r\n*{command}= {value}\r\n".encode()
    )


MODEL = "W1100"
OPTIONS = {
    "raw_responses": {
        "*ltim=?#": b">*ltim=?#\r\n\r\n*ltim=\x00 1386\r\n",
        "*bri=?#": _double_echo("bri", "51"),
        "*con=?#": _double_echo("con", "50"),
        "*color=?#": _double_echo("color", "10"),
        "*sharp=?#": _double_echo("sharp", "5"),
    }
}


async def test_lamp_time(projector: BenQProjectorSerial, hardware: bool) -> None:
    """The lamp time is read, despite the null byte and space before it and no closing #."""
    assert await projector.connect()

    lamp_time = await projector.send_command("ltim")
    assert lamp_time is not None
    assert lamp_time.isdigit()
    if not hardware:
        assert lamp_time == "1386"


@pytest.mark.parametrize(
    ("command", "expected"),
    [("bri", "51"), ("con", "50"), ("color", "10"), ("sharp", "5")],
)
async def test_double_echo(
    projector: BenQProjectorSerial,
    command: str,
    expected: str,
    hardware: bool,
) -> None:
    """The value is read, although the command is echoed twice."""
    assert await projector.connect()

    value = await projector.send_command(command)
    assert value is not None
    assert value != "?"
    if not hardware:
        assert value == expected
    # The next command gets its own response
    assert await projector.send_command("pow") == "on"


async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds the commands and modes of the configuration, despite the double echoes."""
    await assert_examine(projector, examine, expected_features(MODEL))
