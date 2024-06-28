# pylint: disable=R0801
# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import logging
import unittest

from benqprojector import BenQProjectorSerial

logger = logging.getLogger(__name__)

SERIAL_PORT = "/dev/tty.usbserial-10"
BAUD_RATE = 115200


class Test(unittest.IsolatedAsyncioTestCase):
    _projector = None

    async def asyncSetUp(self):
        self._projector = BenQProjectorSerial(SERIAL_PORT, BAUD_RATE)
        await self._projector.connect()
        await self._projector.update()

    async def asyncTearDown(self):
        await self._projector.disconnect()

    async def test_mute(self):
        await self._projector.unmute()
        response = await self._projector.mute()
        self.assertTrue(response)

    async def test_unmute(self):
        await self._projector.mute()
        response = await self._projector.unmute()
        self.assertTrue(response)

    async def test_volume_up(self):
        await self._projector.volume_level(10)
        volume = self._projector.volume
        response = await self._projector.volume_up()
        self.assertTrue(response)
        self.assertEqual(volume + 1, self._projector.volume)

    async def test_volume_down(self):
        await self._projector.volume_level(10)
        volume = self._projector.volume
        response = await self._projector.volume_down()
        self.assertTrue(response)
        self.assertEqual(volume - 1, self._projector.volume)

    async def test_volume_level_up(self):
        await self._projector.volume_level(0)
        response = await self._projector.volume_level(20)
        self.assertTrue(response)

    async def test_volume_level_down(self):
        await self._projector.volume_level(20)
        response = await self._projector.volume_level(0)
        self.assertTrue(response)
