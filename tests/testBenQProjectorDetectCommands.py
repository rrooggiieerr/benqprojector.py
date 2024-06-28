# pylint: disable=R0801
# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
"""
Created on 16 Jan 2023

@author: Rogier van Staveren
"""

import logging
import unittest

from benqprojector import BenQProjectorSerial

# from benqprojector import BenQProjectorTelnet

logger = logging.getLogger(__name__)

SERIAL_PORT = "/dev/tty.usbserial-10"
BAUD_RATE = 115200


class Test(unittest.IsolatedAsyncioTestCase):
    _projector = None

    async def asyncSetUp(self):
        self._projector = BenQProjectorSerial(SERIAL_PORT, BAUD_RATE)
        # self._projector = BenQProjectorTelnet("rs232-bridge.local", 32)
        await self._projector.connect()
        await self._projector.update()

    async def asyncTearDown(self):
        await self._projector.disconnect()

    async def test_detect_commands(self):
        response = await self._projector.detect_commands()
        self.assertIsNotNone(response)
