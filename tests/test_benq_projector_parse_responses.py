"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import pytest

from benqprojector import (
    BenQBlockedItemError,
    BenQCommand,
    BenQIllegalFormatError,
    BenQProjectorSerial,
    BenQUnsupportedItemError,
)

SERIAL_PORT = "/dev/tty.usbserial-10"
BAUD_RATE = 115200


@pytest.fixture
def projector():
    # Don't need to connect to the projector to test parsing responses
    return BenQProjectorSerial(SERIAL_PORT, BAUD_RATE)


@pytest.mark.parametrize(
    ("command", "raw_response", "lowercase", "expected"),
    [
        pytest.param(
            BenQCommand("bri", "?"),
            "*bri= 51",
            True,
            "51",
            # The W1100 bri command does include spaces and does not end with #
            id="w1100_bri",
        ),
        pytest.param(
            BenQCommand("ltim"),
            "*ltim= 1383",
            True,
            "1383",
            # The W1100 ltim command does include spaces and does not end with #
            id="w1100_ltim",
        ),
        pytest.param(
            BenQCommand("modelname"),
            "*modelname=W1100#",
            False,
            "W1100",
            # The W1100 modelname command returns a lowercase response
            id="w1100_modelname",
        ),
        pytest.param(
            BenQCommand("modelname"),
            "*MODELNAME=W1110#",
            False,
            "W1110",
            # The W1110 modelname command returns an uppercase response
            id="w1110_modelname",
        ),
        pytest.param(
            BenQCommand("directpower"),
            "DIRECTPOWER=OFF#",
            False,
            "OFF",
            # The W1110 directpower command does not send the leading * when the
            # projector is turned off
            id="w1110_directpower_projectoroff",
        ),
        pytest.param(
            BenQCommand("directpower"),
            "*DIRECTPOWER=OFF#",
            False,
            "OFF",
            # The W1110 directpower command sends the leading * when the projector
            # is turned on
            id="w1110_directpower_projectoron",
        ),
        pytest.param(
            BenQCommand("modelname"),
            ">*modelname=?#W700",
            False,
            "W700",
            # The W700 modelname command returns the command echo and model name
            # without *MODELNAME= and # on one line when the projector is turned off
            id="w700_modelname_projectoroff",
        ),
        pytest.param(
            BenQCommand("modelname"),
            "W700",
            False,
            "W700",
            # The W700 modelname command returns only the model name and does not
            # start with *MODELNAME= and does not end with # when the projector is
            # turned on
            id="w700_modelname_projectoron",
        ),
        pytest.param(
            BenQCommand("modelname"),
            "W6000L",
            False,
            "W6000L",
            # The W6000L modelname command returns only the model name and does not
            # start with *MODELNAME= and does not end with #
            id="w6000l_modelname",
        ),
        pytest.param(
            BenQCommand("modelname"),
            "*MODELNAME=W1110#",
            False,
            "W1110",
            # The W2000 modelname command returns W1110 when the projector is
            # turned off
            id="w2000_modelname_projectoroff",
        ),
        pytest.param(
            BenQCommand("modelname"),
            "*MODELNAME=W2000#",
            False,
            "W2000",
            # The W2000 modelname command returns W2000 when the projector is
            # turned on
            id="w2000_modelname_projectoron",
        ),
        pytest.param(
            BenQCommand("up", None),
            "*UP#",
            True,
            "up",
            # Some commands don't take any actions, like the up command for
            # navigating the menu.
            id="up",
        ),
    ],
)
def test_parse_response(projector, command, raw_response, lowercase, expected):
    response = projector._parse_response(command, raw_response, lowercase)
    assert response == expected


@pytest.mark.parametrize(
    ("raw_response", "error_class"),
    [
        pytest.param("*Illegal format#", BenQIllegalFormatError, id="illegal_format"),
        pytest.param(
            "*Unsupported item#", BenQUnsupportedItemError, id="unsupported_item"
        ),
        pytest.param(
            "Unsupported item",
            BenQUnsupportedItemError,
            # The W1100 returns the error without leading * and trailing #
            id="w1100_unsupported_item",
        ),
        pytest.param("*Block item#", BenQBlockedItemError, id="block_item"),
    ],
)
def test_parse_response_error(projector, raw_response, error_class):
    with pytest.raises(error_class):
        projector._parse_response(BenQCommand("whatever"), raw_response)
