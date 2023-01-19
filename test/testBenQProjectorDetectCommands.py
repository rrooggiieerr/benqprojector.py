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
        self._projector.update()

    def tearDown(self):
        self._projector.disconnect()

    def test_detect_commands(self):
        response = self._projector.detect_commands()
        self.assertIsNotNone(response)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
