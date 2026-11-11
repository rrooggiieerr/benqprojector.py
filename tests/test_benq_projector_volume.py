"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import pytest

from benqprojector import BenQProjectorSerial

pytestmark = pytest.mark.hardware


@pytest.fixture
async def projector(serial_port, baud_rate):
    projector = BenQProjectorSerial(serial_port, baud_rate)
    await projector.connect()
    await projector.update()
    yield projector
    await projector.disconnect()


async def test_mute(projector):
    await projector.unmute()
    response = await projector.mute()
    assert response


async def test_unmute(projector):
    await projector.mute()
    response = await projector.unmute()
    assert response


async def test_volume_up(projector):
    await projector.volume_level(10)
    volume = projector.volume
    response = await projector.volume_up()
    assert response
    assert projector.volume == volume + 1


async def test_volume_down(projector):
    await projector.volume_level(10)
    volume = projector.volume
    response = await projector.volume_down()
    assert response
    assert projector.volume == volume - 1


@pytest.mark.parametrize(
    ("start_level", "target_level"),
    [(0, 20), (20, 0)],
    ids=["up", "down"],
)
async def test_volume_level(projector, start_level, target_level):
    await projector.volume_level(start_level)
    response = await projector.volume_level(target_level)
    assert response
