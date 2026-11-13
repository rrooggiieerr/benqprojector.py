"""Tests for the BenQ W1000 projector.

The W1000 doesn't support the modelname command, it answers *Illegal format#. The W1000 has no
configuration file.
"""

from benqprojector import BenQProjector, BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features
from .simulation import ILLEGAL_FORMAT

MODEL = "W1000"
OPTIONS = {
    "raw_responses": {
        "*modelname=?#": f"*modelname=?#\r\n{ILLEGAL_FORMAT}\r\n".encode("ascii")
    }
}


async def test_no_model_name(projector: BenQProjectorSerial) -> None:
    """The projector connects without a model name."""
    assert await projector.connect()

    assert projector.model is None
    assert projector.power_status == BenQProjector.POWERSTATUS_ON


async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds pow, but not the unsupported model name."""
    await assert_examine(projector, examine, expected_features(commands={"pow"}))
