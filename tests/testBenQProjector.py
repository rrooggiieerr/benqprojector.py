# pylint: disable=R0801
# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import logging
import time
import unittest

from benqprojector import BenQProjectorSerial

# from benqprojector import BenQProjectorTelnet

logger = logging.getLogger(__name__)

SERIAL_PORT = "/dev/tty.usbserial-110"
BAUD_RATE = 115200


class Test(unittest.IsolatedAsyncioTestCase):
    _projector = None

    async def asyncSetUp(self):
        self._projector = BenQProjectorSerial(SERIAL_PORT, BAUD_RATE)
        # self._projector = BenQProjectorTelnet("rs232-bridge.local")
        await self._projector.connect()
        await self._projector.update()

    async def asyncTearDown(self):
        await self._projector.disconnect()

    # async def test_turn_on(self):
    #     result = await self._projector.turn_on()
    #     self.assertTrue(result)
    #     self.assertEquals(self._projector.POWERSTATE_POWERINGON, self._projector.power_state)

    # async def test_turn_off(self):
    #     result = await self._projector.turn_off()
    #     self.assertTrue(result)
    #     self.assertEquals(self._projector.POWERSTATE_POWERINGOFF, self._projector.power_state)

    # def test_power_on_time(self):
    #     pass

    # async def test_power_off_time(self):
    #     logger.info("Measuring off time")
    #     timestamp = time.time()
    #     while await self._projector.send_command("pow", "off") == "off":
    #         time.sleep(1)
    #     while await self._projector.send_command("pow", "on") != "on":
    #         time.sleep(1)
    #     off_time = time.time() - timestamp
    #     logger.info("Off time: %s seconds", off_time)

    def test_status(self):
        logger.info("Model: %s", self._projector.model)
