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

from benqprojector import BenQProjectorTelnet

logger = logging.getLogger(__name__)

HOSTNAME = "rs232-bridge.local"


class Test(unittest.IsolatedAsyncioTestCase):
    _projector = None

    async def asyncSetUp(self):
        self._projector = BenQProjectorTelnet(HOSTNAME)

    async def asyncTearDown(self):
        await self._projector.disconnect()

    async def test__connect(self):
        result = await self._projector._connect()
        self.assertTrue(result)

    # async def test_connect(self):
    #     result = await self._projector.connect()
    #     self.assertTrue(result)

    async def test__wait_for_prompt(self):
        await self._projector._connect()
        result = await self._projector._wait_for_prompt()
        self.assertTrue(result)

    async def test__send_command(self):
        await self._projector._connect()
        await self._projector._wait_for_prompt()
        result = await self._projector._send_command("pow")
        self.assertTrue(result)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
