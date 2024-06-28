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

logger = logging.getLogger(__name__)

SERIAL_PORT = "/dev/tty.usbserial-10"
BAUD_RATE = 115200


class Test(unittest.IsolatedAsyncioTestCase):
    _projector = None

    async def asyncSetUp(self):
        self._projector = BenQProjectorSerial(SERIAL_PORT, BAUD_RATE)
        await self._projector.connect()
        await self._projector.send_command("menu", "off")
        time.sleep(0.2)

    async def asyncTearDown(self):
        time.sleep(0.2)
        await self._projector.send_command("menu", "off")
        time.sleep(0.2)
        await self._projector.disconnect()

    async def test_menu_off_status(self):
        # Fails on w1110 but should work on other projectors
        response = await self._projector.send_command("menu", "?")
        time.sleep(0.2)
        self.assertIsNotNone(response)
        self.assertEqual("off", response)

    async def test_menu_on_status(self):
        # Fails on w1110 but should work on other projectors
        await self._projector.send_command("menu", "on")
        time.sleep(0.2)
        response = await self._projector.send_command("menu", "?")
        time.sleep(0.2)
        self.assertIsNotNone(response)
        self.assertEqual("on", response)

    async def test_menu_on(self):
        response = await self._projector.send_command("menu", "on")
        self.assertIsNotNone(response)
        self.assertEqual("on", response)

    async def test_menu_off(self):
        await self._projector.send_command("menu", "on")
        time.sleep(0.2)
        response = await self._projector.send_command("menu", "off")
        self.assertIsNotNone(response)
        self.assertEqual("off", response)

    async def test_menu_up(self):
        await self._projector.send_command("menu", "on")
        time.sleep(0.2)
        await self._projector.send_raw_command("*down#")
        time.sleep(0.2)
        response = await self._projector.send_raw_command("*up#")
        self.assertIsNotNone(response)
        self.assertEqual("*up#", response.lower())

    async def test_menu_down(self):
        await self._projector.send_command("menu", "on")
        time.sleep(0.2)
        response = await self._projector.send_raw_command("*down#")
        self.assertIsNotNone(response)
        self.assertEqual("*down#", response.lower())

    async def test_menu_left(self):
        await self._projector.send_command("menu", "on")
        time.sleep(0.2)
        await self._projector.send_raw_command("*right#")
        time.sleep(0.2)
        response = await self._projector.send_raw_command("*left#")
        self.assertIsNotNone(response)
        self.assertEqual("*left#", response.lower())

    async def test_menu_right(self):
        await self._projector.send_command("menu", "on")
        time.sleep(0.2)
        response = await self._projector.send_raw_command("*right#")
        self.assertIsNotNone(response)
        self.assertEqual("*right#", response.lower())
