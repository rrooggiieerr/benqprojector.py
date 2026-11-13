"""Tests for the BenQ W700 projector.

The W700 doesn't follow the protocol for its model name. When on it sends only the model name,
W700 instead of *MODELNAME=W700#. When off it also sends the command echo and the model name on
one line, >*modelname=?#W700. Its prompt is followed by a null byte, >\\x00, and it echoes
other commands without the prompt. The W700 has no configuration file.

Seen in benqprojector.py issue #26.
"""

import pytest

from benqprojector import BenQProjector, BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features

MODEL = "W700"
OPTIONS = {
    "prompt_response": b">\x00",
    "echo_prefix": b"",
    "raw_responses": {
        "*modelname=?#": {
            "on": b"*modelname=?#\r\nW700\r\n",
            "off": b">*modelname=?#W700\r\n",
        }
    },
}


async def test_model_name_on(projector: BenQProjectorSerial) -> None:
    """When on, the model name without *MODELNAME= and # is read."""
    assert await projector.connect()

    assert projector.model == "W700"
    assert projector.power_status == BenQProjector.POWERSTATUS_ON


@pytest.mark.simulated_projector(values={"pow": "OFF"})
async def test_model_name_off(projector: BenQProjectorSerial) -> None:
    """When off, the model name on the same line as the command echo is read."""
    assert await projector.connect()

    assert projector.model == "W700"
    assert projector.power_status == BenQProjector.POWERSTATUS_OFF


async def test_prompt_with_null_byte(projector: BenQProjectorSerial) -> None:
    """Commands work, although the prompt is followed by a null byte."""
    assert await projector.connect()

    assert await projector.send_command("pow") == "on"
    assert await projector.send_command("pow") == "on"


async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds pow and the model name, the W700 has no configuration file."""
    await assert_examine(
        projector, examine, expected_features(commands={"pow", "modelname"})
    )
