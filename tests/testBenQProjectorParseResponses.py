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

from benqprojector.benqprojector import (
    BenQBlockedItemError,
    BenQCommand,
    BenQIllegalFormatError,
    BenQProjector,
    BenQUnsupportedItemError,
)

logger = logging.getLogger(__name__)

SERIAL_PORT = "/dev/tty.usbserial-10"
BAUD_RATE = 115200


class Test(unittest.TestCase):
    _projector = None

    def setUp(self):
        self._projector = BenQProjector(SERIAL_PORT, BAUD_RATE)
        # Don't need to connect to the projector to test parsing responses

    def test_parse_response_w1100_bri(self):
        # The W1100 bri command does include spaces and does not end with #
        response = self._projector._parse_response(BenQCommand("bri", "?"), "*bri= 51")
        self.assertEqual("51", response)

    def test_parse_response_w1100_ltim(self):
        # The W1100 ltim command does include spaces and does not end with #
        response = self._projector._parse_response(BenQCommand("ltim"), "*ltim= 1383")
        self.assertEqual("1383", response)

    def test_parse_response_w1100_modelname(self):
        # The W1110 modelname command returns a lowercase response
        response = self._projector._parse_response(
            BenQCommand("modelname"), "*modelname=W1100#", False
        )
        self.assertEqual("W1100", response)

    def test_parse_response_w1110_modelname(self):
        # The W1110 modelname command returns an uppercase response
        response = self._projector._parse_response(
            BenQCommand("modelname"), "*MODELNAME=W1110#", False
        )
        self.assertEqual("W1110", response)

    def test_parse_response_w1110_directpower_projectoroff(self):
        # The W1110 directpower command does not send the leading #  when the projector is turned
        # off
        response = self._projector._parse_response(
            BenQCommand("directpower"), "DIRECTPOWER=OFF#", False
        )
        self.assertEqual("OFF", response)

    def test_parse_response_w1110_directpower_projectoron(self):
        # The W1110 directpower command sends the leading *  when the projector is turned on
        response = self._projector._parse_response(
            BenQCommand("directpower"), "*DIRECTPOWER=OFF#", False
        )
        self.assertEqual("OFF", response)

    def test_parse_response_w700_modelname(self):
        # The W700 modelname command returns only the model name and does not start with
        # *MODELNAME= and does not end with #
        response = self._projector._parse_response(
            BenQCommand("modelname"), "W700", False
        )
        self.assertEqual("W700", response)

    def test_parse_response_w6000l_modelname(self):
        # The W6000L modelname command returns only the model name and does not start with
        # *MODELNAME= and does not end with #
        response = self._projector._parse_response(
            BenQCommand("modelname"), "W6000L", False
        )
        self.assertEqual("W6000L", response)

    def test_parse_response_w2000_modelname_projectoroff(self):
        # The W2000 modelname command returns W1110 when the projector is turned off
        response = self._projector._parse_response(
            BenQCommand("modelname"), "*MODELNAME=W1110#", False
        )
        self.assertEqual("W1110", response)

    def test_parse_response_w2000_modelname_projectoron(self):
        # The W2000 modelname command returns W2000 when the projector is turned on
        response = self._projector._parse_response(
            BenQCommand("modelname"), "*MODELNAME=W2000#", False
        )
        self.assertEqual("W2000", response)

    def test_parse_response_illegal_format(self):
        self.assertRaises(
            BenQIllegalFormatError,
            self._projector._parse_response,
            BenQCommand("whatever"),
            "*Illegal format#",
        )

    def test_parse_response_unsupported_item(self):
        self.assertRaises(
            BenQUnsupportedItemError,
            self._projector._parse_response,
            BenQCommand("whatever"),
            "*Unsupported item#",
        )

    def test_parse_response_W1100_unsupported_item(self):
        # The W1100  returns the error withouth leading * and trailing #
        self.assertRaises(
            BenQUnsupportedItemError,
            self._projector._parse_response,
            BenQCommand("whatever"),
            "Unsupported item",
        )

    def test_parse_response_block_item(self):
        self.assertRaises(
            BenQBlockedItemError,
            self._projector._parse_response,
            BenQCommand("whatever"),
            "*Block item#",
        )

    def test_parse_response_up(self):
        # Some commands don't take any actions, like the up command for navigating the menu.
        response = self._projector._parse_response(BenQCommand("up", None), "*UP#")
        self.assertEqual("up", response)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
