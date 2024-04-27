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
        self._projector.send_command("menu", "off")
        time.sleep(0.2)

    def tearDown(self):
        time.sleep(0.2)
        self._projector.send_command("menu", "off")
        time.sleep(0.2)
        self._projector.disconnect()

    def test_menu_off_status(self):
        # Fails on w1110 but should work on other projectors
        response = self._projector.send_command("menu", "?")
        time.sleep(0.2)
        self.assertIsNotNone(response)
        self.assertEqual("off", response)

    def test_menu_on_status(self):
        # Fails on w1110 but should work on other projectors
        self._projector.send_command("menu", "on")
        time.sleep(0.2)
        response = self._projector.send_command("menu", "?")
        time.sleep(0.2)
        self.assertIsNotNone(response)
        self.assertEqual("on", response)

    def test_menu_on(self):
        response = self._projector.send_command("menu", "on")
        self.assertIsNotNone(response)
        self.assertEqual("on", response)

    def test_menu_off(self):
        self._projector.send_command("menu", "on")
        time.sleep(0.2)
        response = self._projector.send_command("menu", "off")
        self.assertIsNotNone(response)
        self.assertEqual("off", response)

    def test_menu_up(self):
        self._projector.send_command("menu", "on")
        time.sleep(0.2)
        self._projector.send_raw_command("*down#")
        time.sleep(0.2)
        response = self._projector.send_raw_command("*up#")
        self.assertIsNotNone(response)
        self.assertEqual("*up#", response.lower())

    def test_menu_down(self):
        self._projector.send_command("menu", "on")
        time.sleep(0.2)
        response = self._projector.send_raw_command("*down#")
        self.assertIsNotNone(response)
        self.assertEqual("*down#", response.lower())

    def test_menu_left(self):
        self._projector.send_command("menu", "on")
        time.sleep(0.2)
        self._projector.send_raw_command("*right#")
        time.sleep(0.2)
        response = self._projector.send_raw_command("*left#")
        self.assertIsNotNone(response)
        self.assertEqual("*left#", response.lower())

    def test_menu_right(self):
        self._projector.send_command("menu", "on")
        time.sleep(0.2)
        response = self._projector.send_raw_command("*right#")
        self.assertIsNotNone(response)
        self.assertEqual("*right#", response.lower())


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
