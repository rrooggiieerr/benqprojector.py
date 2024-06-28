# pylint: disable=R0801
# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=protected-access
"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import logging
import unittest

from benqprojector import BenQProjector

logger = logging.getLogger(__name__)

SERIAL_PORT = "/dev/tty.usbserial-10"
BAUD_RATE = 115200


class Test(unittest.TestCase):
    _projector = None

    def setUp(self):
        self._projector = BenQProjector(SERIAL_PORT, BAUD_RATE)
        # Don't need to connect to the projector to test parsing responses

    def test_parse_response_w1100_bri(self):
        # The W1100 ltim command does include spaces and does not end with #
        response = self._projector._parse_response("bri", "?", "*bri=?#", "*bri= 51")
        self.assertEqual("51", response)

    def test_parse_response_w1100_ltim(self):
        # The W1100 ltim command does include spaces and does not end with #
        response = self._projector._parse_response(
            "ltim", "?", "*ltim=?#", "*ltim= 1383"
        )
        self.assertEqual("1383", response)

    def test_parse_response_w1100_modelname(self):
        # The W1110 modelname command returns an lowercase response #
        response = self._projector._parse_response(
            "modelname", "?", "*modelname=?#", "*modelname=W1100#"
        )
        self.assertEqual("w1100", response)

    def test_parse_response_w1110_modelname(self):
        # The W1110 modelname command returns an uppercase response #
        response = self._projector._parse_response(
            "modelname", "?", "*modelname=?#", "*MODELNAME=W1110#"
        )
        self.assertEqual("w1110", response)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
