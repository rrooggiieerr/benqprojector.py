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

from benqprojector import BenQProjector
from benqprojector.benqexamine import BenQProjectorExamine

logger = logging.getLogger(__name__)

SERIAL_PORT = "/dev/tty.usbserial-10"
BAUD_RATE = 115200


class Test(unittest.IsolatedAsyncioTestCase):
    _projector = None
    _examine = None

    async def asyncSetUp(self):
        self._projector = BenQProjector(SERIAL_PORT, BAUD_RATE)
        self._examine = BenQProjectorExamine(self._projector)
        await self._projector.connect()

    async def asyncTearDown(self):
        await self._projector.disconnect()

    async def test_detect_video_sources(self):
        response = await self._examine.detect_video_sources()
        self.assertIsNotNone(response)

    async def test_detect_audio_sources(self):
        response = await self._examine.detect_audio_sources()
        self.assertIsNotNone(response)

    async def test_detect_picture_modes(self):
        response = await self._examine.detect_picture_modes()
        self.assertIsNotNone(response)

    async def test_detect_color_temperatures(self):
        response = await self._examine.detect_color_temperatures()
        self.assertIsNotNone(response)

    async def test_detect_aspect_ratios(self):
        response = await self._examine.detect_aspect_ratios()
        self.assertIsNotNone(response)

    async def test_detect_projector_positions(self):
        response = await self._examine.detect_projector_positions()
        self.assertIsNotNone(response)

    async def test_detect_lamp_modes(self):
        response = await self._examine.detect_lamp_modes()
        self.assertIsNotNone(response)

    async def test_detect_3d_modes(self):
        response = await self._examine.detect_3d_modes()
        self.assertIsNotNone(response)
