"""
Created on 5 Dec 2022

@author: rogier
"""
import unittest

from benqprojector.benqprojector import (
    BenQProjectorError,
    BlockedItemError,
    EmptyResponseError,
    IllegalFormatError,
    InvallidResponseError,
    UnsupportedItemError,
)


class Test(unittest.TestCase):
    def testBenQProjectorError(self):
        BenQProjectorError()

    def testIllegalFormatError(self):
        IllegalFormatError()

    def testEmptyResponseError(self):
        EmptyResponseError()

    def testUnsupportedItemError(self):
        UnsupportedItemError()

    def testBlockedItemError(self):
        BlockedItemError()

    def testInvallidResponseError(self):
        InvallidResponseError()


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testBenQProjectorError']
    unittest.main()
