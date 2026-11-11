"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import logging

import pytest

from benqprojector import BenQProjectorSerial

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.hardware


@pytest.fixture
async def projector(serial_port, baud_rate):
    projector = BenQProjectorSerial(serial_port, baud_rate)
    await projector.connect()
    await projector.update()
    yield projector
    await projector.disconnect()


# async def test_turn_on(projector):
#     result = await projector.turn_on()
#     assert result
#     assert projector.power_state == projector.POWERSTATE_POWERINGON


# async def test_turn_off(projector):
#     result = await projector.turn_off()
#     assert result
#     assert projector.power_state == projector.POWERSTATE_POWERINGOFF


# async def test_power_off_time(projector):
#     logger.info("Measuring off time")
#     timestamp = time.time()
#     while await projector.send_command("pow", "off") == "off":
#         await asyncio.sleep(1)
#     while await projector.send_command("pow", "on") != "on":
#         await asyncio.sleep(1)
#     off_time = time.time() - timestamp
#     logger.info("Off time: %s seconds", off_time)


def test_status(projector):
    logger.info("Model: %s", projector.model)
