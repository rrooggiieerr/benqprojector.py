"""Tests for the BenQ W6000L projector.

The W6000L sends only its model name, W6000L instead of *MODELNAME=W6000L#. It reports its MAC
address, which becomes its unique id.
"""

from benqprojector import BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

from .conftest import assert_examine, expected_features

MODEL = "W6000L"
VALUES = {"macaddr": "00:11:22:AA:BB:CC"}
OPTIONS = {"raw_responses": {"*modelname=?#": b"*modelname=?#\r\nW6000L\r\n"}}


async def test_model_name(projector: BenQProjectorSerial) -> None:
    """The model name without *MODELNAME= and # is read."""
    assert await projector.connect()

    assert projector.model == "W6000L"


async def test_unique_id(projector: BenQProjectorSerial, hardware: bool) -> None:
    """The MAC address is the unique id."""
    assert await projector.connect()

    assert projector.unique_id is not None
    assert projector.unique_id.count(":") == 5
    if not hardware:
        assert projector.unique_id == "00:11:22:aa:bb:cc"


async def test_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
) -> None:
    """Examining finds the commands and modes of the configuration."""
    await assert_examine(projector, examine, expected_features(MODEL))
