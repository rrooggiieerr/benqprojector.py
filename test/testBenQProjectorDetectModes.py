"""
Created on 16 Jan 2023

@author: Rogier van Staveren
"""
import logging
import unittest

from benqprojector import BenQProjector

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s", level=logging.DEBUG
)

serial_port = "/dev/tty.usbserial-10"


class Test(unittest.TestCase):
    _projector = None

    def setUp(self):
        self._projector = BenQProjector(serial_port, 115200)
        self._projector.connect()

    def tearDown(self):
        self._projector.disconnect()

    def test_detect_video_sources(self):
        response = self._projector.detect_video_sources()
        self.assertIsNotNone(response)

    def test_detect_audio_sources(self):
        response = self._projector.detect_audio_sources()
        self.assertIsNotNone(response)

    def test_detect_picture_modes(self):
        response = self._projector.detect_picture_modes()
        self.assertIsNotNone(response)

    def test_detect_color_temperatures(self):
        response = self._projector.detect_color_temperatures()
        self.assertIsNotNone(response)

    def test_detect_aspect_ratios(self):
        response = self._projector.detect_aspect_ratios()
        self.assertIsNotNone(response)

    def test_detect_projector_positions(self):
        response = self._projector.detect_projector_positions()
        self.assertIsNotNone(response)

    def test_detect_lamp_modes(self):
        response = self._projector.detect_lamp_modes()
        self.assertIsNotNone(response)

    def test_detect_3d_modes(self):
        response = self._projector.detect_3d_modes()
        self.assertIsNotNone(response)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
