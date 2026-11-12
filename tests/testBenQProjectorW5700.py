# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=protected-access
"""
Emulates the W5700 serial behaviour, no projector needed.

When on, the W5700 does not answer a bare <CR> with a prompt and the bare <CR> corrupts the next
command. Commands framed as <CR>*command#<CR> always work.
"""

import asyncio
import unittest

from benqprojector import BenQProjector
from benqprojector.benqclasses import BenQCommand, BenQUnsupportedItemError
from benqprojector.benqconnection import BenQConnection


class W5700Emulator(BenQConnection):
    _read_timeout = 0.05

    def __init__(self, power="off"):
        super().__init__()
        self.power = power
        self.appmod_blocked = False
        self.source = "hdmi"
        self._corrupted = False

    def __str__(self):
        return "w5700-emulator"

    async def open(self) -> bool:
        self._reader = asyncio.StreamReader()
        self._writer = True
        return True

    async def close(self) -> bool:
        self._reader = None
        self._writer = None
        return True

    async def reset(self) -> bool:
        await self.read(-1)
        return True

    async def write(self, data: bytes) -> int:
        if data == b"\r":
            if self.power == "off":
                self._reader.feed_data(b">")
            else:
                self._corrupted = True
            return len(data)

        if self._corrupted or not data.startswith(b"\r"):
            # Not properly framed, the projector stays silent
            self._corrupted = False
            return len(data)

        command = data.strip(b"\r").decode()
        key, value = command[1:-1].split("=")
        if key == "freeze":
            # The real W5700 answers without * and #
            self._reader.feed_data(f">{command}\r\r\nUnsupported item\r\n".encode())
            return len(data)
        if key == "appmod" and self.appmod_blocked:
            self._reader.feed_data(f">{command}\r\r\n*Block item#\r\n".encode())
            return len(data)
        if key == "pow" and value != "?":
            self.power = value
        elif key == "sour" and value != "?":
            self.source = value
        state = {
            "pow": self.power,
            "sour": self.source,
            "modelname": "W5700",
            "macaddr": "00:00:00:00:00:00",
            "appmod": "cine",
        }
        self._reader.feed_data(
            f">{command}\r\r\n*{key.upper()}={state[key].upper()}#\r\n".encode()
        )
        return len(data)


class Test(unittest.IsolatedAsyncioTestCase):
    async def test_w5700_on(self):
        projector = BenQProjector(W5700Emulator(power="on"), "W5700")
        projector.has_prompt = True  # As BenQProjectorSerial does
        self.assertTrue(await projector.connect())
        self.assertEqual(projector.POWERSTATUS_ON, projector.power_status)

        # An unsupported item must not desynchronise the following commands
        with self.assertRaises(BenQUnsupportedItemError):
            await projector._send_command(BenQCommand("freeze"), check_supported=False)
        self.assertEqual("on", await projector.send_command("pow"))

        self.assertTrue(await projector.select_video_source("hdmi2"))
        self.assertEqual("hdmi2", await projector.send_command("sour"))
        self.assertTrue(await projector.select_video_source("hdmi"))

        self.assertTrue(await projector.turn_off())
        self.assertEqual(projector.POWERSTATUS_POWERINGOFF, projector.power_status)

    async def test_w5700_blocked_item_warns_once(self):
        projector = BenQProjector(W5700Emulator(power="on"), "W5700")
        projector.has_prompt = True
        self.assertTrue(await projector.connect())
        projector.connection.appmod_blocked = True

        def blocked_warnings(logs):
            return [r for r in logs.records if "blocked item" in r.getMessage()]

        with self.assertLogs("benqprojector", "WARNING") as logs:
            self.assertIsNone(await projector.send_command("appmod"))
            self.assertIsNone(await projector.send_command("appmod"))
            # Answering again re-arms the warning
            projector.connection.appmod_blocked = False
            self.assertEqual("cine", await projector.send_command("appmod"))
            projector.connection.appmod_blocked = True
            self.assertIsNone(await projector.send_command("appmod"))
        self.assertEqual(2, len(blocked_warnings(logs)))

    async def test_w5700_off_then_on(self):
        projector = BenQProjector(W5700Emulator(power="off"), "W5700")
        projector.has_prompt = True
        self.assertTrue(await projector.connect())
        self.assertEqual(projector.POWERSTATUS_OFF, projector.power_status)

        self.assertTrue(await projector.turn_on())
        self.assertEqual("on", await projector.send_command("pow"))

    async def test_w5700_still_reports_on_while_powering_off(self):
        projector = BenQProjector(W5700Emulator(power="on"), "W5700")
        self.assertTrue(await projector.connect())
        self.assertTrue(await projector.turn_off())
        # The real W5700 keeps answering on for ~13 seconds after pow=off
        projector.connection.power = "on"
        self.assertTrue(await projector.update_power())
        self.assertEqual(projector.POWERSTATUS_POWERINGOFF, projector.power_status)


if __name__ == "__main__":
    unittest.main()
