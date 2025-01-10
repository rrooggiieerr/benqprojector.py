# pylint: disable=R0801
# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
"""
Created on 5 Dec 2022

@author: rogier
"""

import unittest

from benqprojector.benqprojector import (
    BenQBlockedItemError,
    BenQEmptyResponseError,
    BenQIllegalFormatError,
    BenQInvallidResponseError,
    BenQProjectorError,
    BenQUnsupportedItemError,
)


class Test(unittest.TestCase):
    def testBenQProjectorError(self):
        BenQProjectorError()

    def testBenQIllegalFormatError(self):
        BenQIllegalFormatError()

    def testBenQEmptyResponseError(self):
        BenQEmptyResponseError()

    def testBenQUnsupportedItemError(self):
        BenQUnsupportedItemError()

    def testBenQBlockedItemError(self):
        BenQBlockedItemError()

    def testBenQInvallidResponseError(self):
        BenQInvallidResponseError()


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testBenQProjectorError']
    unittest.main()
