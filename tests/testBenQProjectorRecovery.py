# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
"""
Recovery when a serial bridge stops returning the command prompt.
"""

import time
import unittest

from benqprojector import BenQProjector
from benqprojector.benqclasses import (
    BenQBlockedItemError,
    BenQPromptTimeoutError,
    BenQUnsupportedItemError,
)


class FakeConnection:
    def __init__(self):
        self.closed = False

    def is_open(self):
        return not self.closed

    async def close(self):
        self.closed = True
        return True

    def __str__(self):
        return "fake"


class Test(unittest.IsolatedAsyncioTestCase):
    def _projector(self, has_prompt=True):
        projector = BenQProjector(FakeConnection())
        projector.has_prompt = has_prompt
        projector._interval = 5
        projector._supported_commands = ["pow", "ltim", "ltim2"]
        projector._listener_commands = ["ltim", "ltim2"]
        return projector

    async def test_prompt_timeout_closes_serial_connection_and_pauses(self):
        projector = self._projector(True)
        calls = []

        async def fail(command, check_supported=True, lowercase_response=True):
            calls.append(command.command)
            raise BenQPromptTimeoutError(command)

        projector._send_command = fail

        self.assertIsNone(await projector.send_command("pow"))
        self.assertTrue(projector.connection.closed)
        self.assertGreater(projector._poll_pause_until, time.monotonic())

        projector.connection.closed = False

        async def succeed(command, check_supported=True, lowercase_response=True):
            calls.append("again")
            return "on"

        projector._send_command = succeed
        self.assertIsNone(await projector.send_command("pow"))
        self.assertNotIn("again", calls)
        self.assertFalse(projector.connection.closed)

    async def test_prompt_timeout_keeps_native_network_connection(self):
        projector = self._projector(False)

        async def fail(command, check_supported=True, lowercase_response=True):
            raise BenQPromptTimeoutError(command)

        projector._send_command = fail

        self.assertIsNone(await projector.send_command("pow"))
        self.assertFalse(projector.connection.closed)
        self.assertEqual(projector._poll_pause_until, 0.0)

    async def test_refused_second_lamp_is_not_polled_again(self):
        projector = self._projector()

        async def blocked(command, check_supported=True, lowercase_response=True):
            raise BenQBlockedItemError(command)

        projector._send_command = blocked

        self.assertIsNone(await projector.send_command("ltim2"))
        self.assertFalse(projector.supports_command("ltim2"))
        self.assertNotIn("ltim2", projector._listener_commands)
        self.assertTrue(projector.supports_command("pow"))
        self.assertIn("ltim", projector._listener_commands)

    async def test_unsupported_second_lamp_is_not_polled_again(self):
        projector = self._projector()

        async def unsupported(command, check_supported=True, lowercase_response=True):
            raise BenQUnsupportedItemError(command)

        projector._send_command = unsupported

        self.assertIsNone(await projector.send_command("ltim2"))
        self.assertFalse(projector.supports_command("ltim2"))

    async def test_blocked_power_command_stays_polled(self):
        projector = self._projector()

        async def blocked(command, check_supported=True, lowercase_response=True):
            raise BenQBlockedItemError(command)

        projector._send_command = blocked

        self.assertIsNone(await projector.send_command("pow"))
        self.assertTrue(projector.supports_command("pow"))


if __name__ == "__main__":
    unittest.main()
