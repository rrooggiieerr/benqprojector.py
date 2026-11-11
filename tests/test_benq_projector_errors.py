"""
Created on 5 Dec 2022

@author: rogier
"""

import pytest

from benqprojector import (
    BenQBlockedItemError,
    BenQEmptyResponseError,
    BenQIllegalFormatError,
    BenQInvallidResponseError,
    BenQProjectorError,
    BenQUnsupportedItemError,
)


@pytest.mark.parametrize(
    "error_class",
    [
        BenQProjectorError,
        BenQIllegalFormatError,
        BenQEmptyResponseError,
        BenQUnsupportedItemError,
        BenQBlockedItemError,
        BenQInvallidResponseError,
    ],
)
def test_error(error_class):
    error = error_class()
    assert isinstance(error, BenQProjectorError)
