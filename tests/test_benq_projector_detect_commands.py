"""
Created on 16 Jan 2023

@author: Rogier van Staveren
"""

import pytest

from benqprojector import BenQProjectorSerial
from benqprojector.benqexamine import BenQProjectorExamine

pytestmark = pytest.mark.hardware


@pytest.fixture
async def examine(serial_port, baud_rate):
    projector = BenQProjectorSerial(serial_port, baud_rate)
    examine = BenQProjectorExamine(projector)
    await projector.connect()
    await projector.update()
    yield examine
    await projector.disconnect()


async def test_detect_commands(examine):
    response = await examine.detect_commands()
    assert response is not None
