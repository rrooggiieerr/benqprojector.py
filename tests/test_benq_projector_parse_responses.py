"""Tests parsing the responses of projectors, without a projector.

The responses come from the quirks of real projectors, see quirks.md.

Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import pytest

from benqprojector import (
    BenQBlockedItemError,
    BenQCommand,
    BenQIllegalFormatError,
    BenQInvallidResponseError,
    BenQProjectorError,
    BenQProjectorSerial,
    BenQUnsupportedItemError,
)

SERIAL_PORT = "/dev/tty.usbserial-10"
BAUD_RATE = 115200


@pytest.fixture
def parser() -> BenQProjectorSerial:
    """A projector object to parse responses with, it isn't connected."""
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
            BenQCommand("ltim"),
            "*ltim=\x00 1386",
            True,
            "1386",
            # The W1100 lamp time can have a null byte in front of the value
            id="w1100_ltim_null_byte",
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
            BenQCommand("sour"),
            "*SOUR=HDMI#",
            False,
            "HDMI",
            # The case of the value is kept
            id="keep_case",
        ),
        pytest.param(
            BenQCommand("sour"),
            "*SOUR=HDMI#",
            True,
            "hdmi",
            # Or the value is lowercased
            id="lowercase",
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
def test_parse_response(
    parser: BenQProjectorSerial,
    command: BenQCommand,
    raw_response: str,
    lowercase: bool,
    expected: str,
) -> None:
    """The value is read from the response."""
    response = parser._parse_response(command, raw_response, lowercase)
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
        pytest.param(
            "*Unsupported Item#",
            BenQUnsupportedItemError,
            # The W4000i and W4100i write Item with a capital I
            id="w4100i_unsupported_item",
        ),
        pytest.param(
            "*Unsupporteditem#",
            BenQUnsupportedItemError,
            # The W2700 writes Unsupporteditem without a space
            id="w2700_unsupported_item",
        ),
        pytest.param(
            "Illegal format",
            BenQIllegalFormatError,
            # The W2700 returns the error without leading * and trailing #
            id="w2700_illegal_format",
        ),
        pytest.param("*Block item#", BenQBlockedItemError, id="block_item"),
        pytest.param("Block item", BenQBlockedItemError, id="block_item_bare"),
    ],
)
def test_parse_response_error(
    parser: BenQProjectorSerial,
    raw_response: str,
    error_class: type[BenQProjectorError],
) -> None:
    """An error response raises its error."""
    with pytest.raises(error_class):
        parser._parse_response(BenQCommand("whatever"), raw_response)


@pytest.mark.parametrize(
    ("command", "raw_response"),
    [
        pytest.param(BenQCommand("pow"), "*SOUR=HDMI#", id="other_command"),
        pytest.param(BenQCommand("pow"), "nonsense", id="no_response_format"),
    ],
)
def test_parse_invalid_response(
    parser: BenQProjectorSerial, command: BenQCommand, raw_response: str
) -> None:
    """A response to another command, or something which isn't a response, is invalid."""
    with pytest.raises(BenQInvallidResponseError):
        parser._parse_response(command, raw_response)
