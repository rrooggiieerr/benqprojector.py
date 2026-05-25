# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
import unittest
from unittest.mock import AsyncMock, Mock, patch

import serialx

from benqprojector.benqconnection import BenQSerialConnection

BAUD_RATE = 115200


class Test(unittest.IsolatedAsyncioTestCase):
    async def _test_open(self, serial_port: str):
        connection = BenQSerialConnection(serial_port, BAUD_RATE)
        reader = Mock()
        writer = Mock()
        writer.close = Mock()
        writer.wait_closed = AsyncMock()

        with patch(
            "benqprojector.benqconnection.serialx.open_serial_connection",
            AsyncMock(return_value=(reader, writer)),
        ) as open_serial_connection:
            result = await connection.open()

        self.assertTrue(result)
        self.assertTrue(connection.is_open())
        open_serial_connection.assert_awaited_once_with(
            url=serial_port,
            baudrate=BAUD_RATE,
            byte_size=serialx.EIGHTBITS,
            parity=serialx.Parity.NONE,
            stopbits=serialx.StopBits.ONE,
        )

        await connection.close()

    async def test_open_uses_serial_path(self):
        await self._test_open("/dev/tty.usbserial-10")

    async def test_open_uses_serial_uri(self):
        await self._test_open("esphome-hass://esphome/abc123?port_name=uart0")
