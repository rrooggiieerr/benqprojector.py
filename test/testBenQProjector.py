"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""
import logging
import time
import unittest

from benqprojector import BenQProjector

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s", level=logging.DEBUG
)

serial_port = "/dev/tty.usbserial-10"


class Test(unittest.TestCase):
    _projector = None

    def setUp(self):
        self._projector = BenQProjector(serial_port, 115200)
        self._projector.connect()

    def tearDown(self):
        self._projector.disconnect()

    def test_mute(self):
        self._projector.unmute()
        response = self._projector.mute()
        self.assertTrue(response)

    def test_unmute(self):
        self._projector.mute()
        response = self._projector.unmute()
        self.assertTrue(response)

    def test_volume_up(self):
        self._projector.volume_level(10)
        volume = self._projector.volume
        response = self._projector.volume_up()
        self.assertTrue(response)
        self.assertEquals(volume + 1, self._projector.volume)

    def test_volume_down(self):
        self._projector.volume_level(10)
        volume = self._projector.volume
        response = self._projector.volume_down()
        self.assertTrue(response)
        self.assertEquals(volume - 1, self._projector.volume)

    def test_volume_level_up(self):
        self._projector.volume_level(0)
        response = self._projector.volume_level(20)
        self.assertTrue(response)

    def test_volume_level_down(self):
        self._projector.volume_level(20)
        response = self._projector.volume_level(0)
        self.assertTrue(response)

    def test_detect_commands(self):
        commands = self._projector.detect_commands()
        self.assertIsNotNone(commands)
        logger.info("Supported commands: %s", commands)

    def test_detect_sources(self):
        sources = self._projector.detect_commands()
        self.assertIsNotNone(sources)
        logger.info("Supported sources: %s", sources)

    # def test_turn_on(self):
    #     result = self._projector.turn_on()
    #     self.assertTrue(result)
    #     self.assertEquals(self._projector.POWERSTATE_POWERINGON, self._projector.power_state)

    # def test_turn_off(self):
    #     result = self._projector.turn_off()
    #     self.assertTrue(result)
    #     self.assertEquals(self._projector.POWERSTATE_POWERINGOFF, self._projector.power_state)

    # def test_power_on_time(self):
    #     pass

    # def test_power_off_time(self):
    #     logger.info("Measuring off time")
    #     timestamp = time.time()
    #     while self._projector.send_command("pow", "off") == "off":
    #         time.sleep(1)
    #     while self._projector.send_command("pow", "on") != "on":
    #         time.sleep(1)
    #     off_time = time.time() - timestamp
    #     logger.info("Off time: %s seconds", off_time)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
