"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""
import logging
import time
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

    def test_parse_response_w1100_ltim(self):
        # The W1100 ltim command does include spaces and does not end with #
        response = self._projector._parse_response(
            "ltim", "?", "*ltim=?#", "*ltim= 1383"
        )
        self.assertEqual("1383", response)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
