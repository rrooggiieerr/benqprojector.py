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
    yield examine
    await projector.disconnect()


@pytest.mark.parametrize(
    "method",
    [
        "detect_video_sources",
        "detect_audio_sources",
        "detect_picture_modes",
        "detect_color_temperatures",
        "detect_aspect_ratios",
        "detect_projector_positions",
        "detect_lamp_modes",
        "detect_3d_modes",
    ],
)
async def test_detect(examine, method):
    response = await getattr(examine, method)()
    assert response is not None
