"""Tests for the BenQ W1070 and W1250 projectors.

The W1070 and W1250 refuse the modelname command while off, they answer *Block item#. They
have no configuration file.
"""

import pytest

from benqprojector import BenQProjector, BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features
from .simulation import BLOCK_ITEM

MODEL = "W1070"
OPTIONS = {
    "raw_responses": {
        "*modelname=?#": {"off": f"*modelname=?#\r\n{BLOCK_ITEM}\r\n".encode("ascii")}
    }
}


async def test_model_name_on(projector: BenQProjectorSerial) -> None:
    """When on, the projector reports its model name."""
    assert await projector.connect()

    assert projector.model == "W1070"


@pytest.mark.simulated_projector(values={"pow": "OFF"})
async def test_model_name_off(projector: BenQProjectorSerial) -> None:
    """When off, the projector connects without a model name."""
    assert await projector.connect()

    assert projector.model is None
    assert projector.power_status == BenQProjector.POWERSTATUS_OFF


async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds pow and the model name, the W1070 has no configuration file."""
    await assert_examine(
        projector, examine, expected_features(commands={"pow", "modelname"})
    )
