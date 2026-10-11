# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=protected-access
"""
Connection robustness tests against a fake projector on the native network protocol.

These need no projector: tests/fake_projector.py serves the protocol on 127.0.0.1.
"""

import asyncio
import unittest
from unittest.mock import patch

import benqprojector
from benqprojector import BenQProjector, BenQProjectorTelnet

from .fake_projector import FakeProjector


class Recorder:
    def __init__(self):
        self.events: list[tuple[str, object]] = []

    def __call__(self, command, data):
        self.events.append((command, data))

    def last(self, command):
        for name, data in reversed(self.events):
            if name == command:
                return data
        return None


async def wait_for(condition, timeout: float = 10.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.05)


class Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = FakeProjector()
        await self.fake.start()
        self.projectors: list[BenQProjector] = []
        patcher_min = patch.object(benqprojector, "_RECONNECT_DELAY_MIN", 0.2)
        patcher_max = patch.object(benqprojector, "_RECONNECT_DELAY_MAX", 0.4)
        patcher_min.start()
        patcher_max.start()
        self.addCleanup(patcher_min.stop)
        self.addCleanup(patcher_max.stop)

    async def asyncTearDown(self):
        for projector in self.projectors:
            await projector.disconnect()
        await self.fake.stop()

    def projector(self, model_hint="LK935", port=None) -> BenQProjectorTelnet:
        projector = BenQProjectorTelnet("127.0.0.1", port or self.fake.port, model_hint)
        self.projectors.append(projector)
        return projector

    async def test_telnet_projector_can_be_created(self):
        projector = BenQProjectorTelnet("127.0.0.1", 8000)
        self.assertEqual(projector.unique_id, "127.0.0.1:8000")
        self.assertIsNone(projector.has_prompt)

    async def test_connect_detects_model_and_mac(self):
        projector = self.projector(model_hint=None)
        self.assertTrue(await projector.connect())
        self.assertFalse(projector.has_prompt)
        self.assertEqual(projector.model, "LK935")
        self.assertEqual(projector.unique_id, "c0:c4:f9:18:a6:2f")
        self.assertEqual(projector.power_status, BenQProjector.POWERSTATUS_OFF)

    async def test_connect_returns_false_when_model_unknown(self):
        self.fake.silent.add("modelname")
        projector = self.projector(model_hint=None)
        self.assertFalse(await projector.connect())
        self.assertFalse(projector.connected())

    async def test_connect_uses_model_hint_when_modelname_fails(self):
        self.fake.silent.add("modelname")
        projector = self.projector()
        self.assertTrue(await projector.connect())
        self.assertEqual(projector.model, "LK935")

    async def test_connect_returns_false_on_reset(self):
        self.fake.refuse = True
        self.assertFalse(await self.projector().connect())

    async def test_connect_returns_false_when_nothing_listens(self):
        self.assertFalse(await self.projector(port=1).connect())

    async def test_read_loop_recovers_after_reset(self):
        projector = self.projector()
        events = Recorder()
        self.assertTrue(await projector.connect(interval=0.1))
        projector.add_listener(events)
        await wait_for(lambda: events.last("pow") == BenQProjector.POWERSTATUS_OFF)

        self.fake.reset_connections()
        await wait_for(lambda: events.last("pow") == BenQProjector.POWERSTATUS_UNKNOWN)

        self.fake.power = "on"
        await wait_for(lambda: events.last("pow") == BenQProjector.POWERSTATUS_ON)
        self.assertTrue(projector.connected())

    async def test_read_loop_recovers_after_outage(self):
        port = self.fake.port
        projector = self.projector()
        events = Recorder()
        self.assertTrue(await projector.connect(interval=0.1))
        projector.add_listener(events)
        await wait_for(lambda: events.last("pow") == BenQProjector.POWERSTATUS_OFF)

        await self.fake.stop()
        await wait_for(lambda: events.last("pow") == BenQProjector.POWERSTATUS_UNKNOWN)
        await asyncio.sleep(0.5)

        await self.fake.start(port)
        await wait_for(lambda: events.last("pow") == BenQProjector.POWERSTATUS_OFF)

    async def test_read_loop_survives_unexpected_error(self):
        self.fake.power = "on"
        projector = self.projector()
        events = Recorder()
        self.assertTrue(await projector.connect(interval=0.1))

        calls = 0
        original = projector.update_video_source

        async def broken():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("boom")
            return await original()

        projector.update_video_source = broken
        projector.add_listener(events)
        await wait_for(lambda: calls >= 3)
        self.assertFalse(projector._read_task.done())
        await wait_for(lambda: events.last("sour") == "hdmi")

    async def test_disconnect_stops_read_task_while_disconnected(self):
        projector = self.projector()
        events = Recorder()
        self.assertTrue(await projector.connect(interval=0.1))
        projector.add_listener(events)
        await wait_for(lambda: events.last("pow") == BenQProjector.POWERSTATUS_OFF)
        task = projector._read_task

        self.fake.refuse = True
        self.fake.reset_connections()
        await wait_for(lambda: events.last("pow") == BenQProjector.POWERSTATUS_UNKNOWN)
        self.assertFalse(projector.connected())

        await projector.disconnect()
        self.assertTrue(task.done())

        self.fake.refuse = False
        connections = self.fake.connections
        await asyncio.sleep(1)
        self.assertEqual(self.fake.connections, connections)

    async def test_unsupported_commands_stop_being_polled(self):
        self.fake.power = "on"
        projector = self.projector()
        self.assertTrue(await projector.connect(interval=0.05))
        projector.add_listener(command="micvol")
        projector.add_listener(command="bri")
        events = Recorder()
        projector.add_listener(events)
        await wait_for(lambda: self.fake.count("bri") >= 10)
        self.assertEqual(
            self.fake.count("micvol"), benqprojector._MAX_UNSUPPORTED_RESPONSES
        )
        self.assertEqual(events.last("bri"), "50")

    async def test_user_command_waits_for_slow_poll(self):
        self.fake.power = "on"
        self.fake.delays["bri"] = 1.5
        projector = self.projector()
        self.assertTrue(await projector.connect(interval=0.05))
        projector.add_listener(command="bri")
        projector.add_listener(Recorder())
        await wait_for(lambda: self.fake.count("bri") >= 1)

        self.assertTrue(await projector.turn_off())
        self.assertEqual(self.fake.power, "off")

    async def test_volume_up_without_known_volume(self):
        self.fake.power = "on"
        projector = self.projector()
        self.assertTrue(await projector.connect())
        projector.volume = None
        self.assertTrue(await projector.volume_up())
        self.assertEqual(projector.volume, 6)

    async def test_blocked_power_keeps_state(self):
        self.fake.power = "on"
        projector = self.projector()
        events = Recorder()
        self.assertTrue(await projector.connect(interval=0.1))
        projector.add_listener(events)
        await wait_for(lambda: events.last("pow") == BenQProjector.POWERSTATUS_ON)

        self.fake.blocked.add("pow")
        count = self.fake.count("pow")
        await wait_for(lambda: self.fake.count("pow") >= count + 5)
        self.assertEqual(events.last("pow"), BenQProjector.POWERSTATUS_ON)


if __name__ == "__main__":
    unittest.main()
