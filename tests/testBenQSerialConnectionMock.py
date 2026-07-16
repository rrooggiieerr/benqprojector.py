# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
import unittest
from unittest.mock import AsyncMock, Mock, patch

import serialx

from benqprojector import BenQProjectorSerial
from benqprojector.benqclasses import BenQResponseTimeoutError
from benqprojector.benqconnection import BenQConnectionError, BenQSerialConnection

BAUD_RATE = 115200


class Test(unittest.IsolatedAsyncioTestCase):
    async def _test_open(self, serial_port: str):
        connection = BenQSerialConnection(serial_port, BAUD_RATE)
        reader = Mock()
        reader.at_eof.return_value = False
        writer = Mock()
        writer.close = Mock()
        writer.is_closing.return_value = False
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
            timeout=1,
        )

        await connection.close()

    async def test_open_uses_serial_path(self):
        await self._test_open("/dev/tty.usbserial-10")

    async def test_open_uses_serial_uri(self):
        await self._test_open("esphome-hass://esphome/abc123?port_name=uart0")

    async def test_closed_transport_is_replaced(self):
        connection = BenQSerialConnection("/dev/tty.old", BAUD_RATE)
        old_reader = Mock()
        old_reader.at_eof.return_value = True
        old_writer = Mock()
        old_writer.close = Mock()
        old_writer.is_closing.return_value = False
        old_writer.wait_closed = AsyncMock()
        connection._reader = old_reader
        connection._writer = old_writer

        new_reader = Mock()
        new_reader.at_eof.return_value = False
        new_writer = Mock()
        new_writer.is_closing.return_value = False

        with patch(
            "benqprojector.benqconnection.serialx.open_serial_connection",
            AsyncMock(return_value=(new_reader, new_writer)),
        ):
            self.assertTrue(await connection.open())

        old_writer.close.assert_called_once_with()
        old_writer.wait_closed.assert_awaited_once_with()
        self.assertIs(connection._reader, new_reader)
        self.assertIs(connection._writer, new_writer)

    async def test_backend_write_error_closes_connection(self):
        connection = BenQSerialConnection("esphome://device", BAUD_RATE)
        connection._reader = Mock()
        connection._reader.at_eof.return_value = False
        connection._writer = Mock()
        connection._writer.is_closing.return_value = False
        connection._writer.drain = AsyncMock(side_effect=RuntimeError("API stopped"))
        connection._writer.wait_closed = AsyncMock()

        with self.assertRaisesRegex(BenQConnectionError, "API stopped"):
            await connection.write(b"test")

        self.assertFalse(connection.is_open())

    async def test_response_timeout_closes_connection(self):
        projector = BenQProjectorSerial("esphome://device", BAUD_RATE)
        projector._send_command = AsyncMock(side_effect=BenQResponseTimeoutError())
        projector.connection.close = AsyncMock()

        self.assertIsNone(await projector.send_command("pow"))

        projector.connection.close.assert_awaited_once_with()
