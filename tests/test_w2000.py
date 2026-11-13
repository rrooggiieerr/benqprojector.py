"""Tests for the BenQ W2000 projector.

The W2000 reports a different model name when it is off, W1110, than when it is on, W2000.
The W2000 has no configuration file.
"""

import pytest

from benqprojector import BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features

MODEL = "W2000"
OPTIONS = {
    "raw_responses": {
        "*modelname=?#": {
            "on": b"*modelname=?#\r\n*MODELNAME=W2000#\r\n",
            "off": b"*modelname=?#\r\n*MODELNAME=W1110#\r\n",
        }
    }
}


async def test_model_name_on(projector: BenQProjectorSerial) -> None:
    """When on, the projector is a W2000."""
    assert await projector.connect()

    assert projector.model == "W2000"


@pytest.mark.simulated_projector(values={"pow": "OFF"})
async def test_model_name_off(projector: BenQProjectorSerial) -> None:
    """When off, the projector reports itself as a W1110, and is taken for one."""
    assert await projector.connect()

    assert projector.model == "W1110"


async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds pow and the model name, the W2000 has no configuration file."""
    await assert_examine(
        projector, examine, expected_features(commands={"pow", "modelname"})
    )
