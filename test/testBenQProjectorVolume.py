"""
Created on 27 Nov 2022

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
        self._projector.update()

    def tearDown(self):
        self._projector.disconnect()

    def test_mute(self):
        self._projector.unmute()
        response = self._projector.mute()
        self.assertTrue(response)

    def test_unmute(self):
        self._projector.mute()
        response = self._projector.unmute()
        self.assertTrue(response)

    def test_volume_up(self):
        self._projector.volume_level(10)
        volume = self._projector.volume
        response = self._projector.volume_up()
        self.assertTrue(response)
        self.assertEquals(volume + 1, self._projector.volume)

    def test_volume_down(self):
        self._projector.volume_level(10)
        volume = self._projector.volume
        response = self._projector.volume_down()
        self.assertTrue(response)
        self.assertEquals(volume - 1, self._projector.volume)

    def test_volume_level_up(self):
        self._projector.volume_level(0)
        response = self._projector.volume_level(20)
        self.assertTrue(response)

    def test_volume_level_down(self):
        self._projector.volume_level(20)
        response = self._projector.volume_level(0)
        self.assertTrue(response)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
