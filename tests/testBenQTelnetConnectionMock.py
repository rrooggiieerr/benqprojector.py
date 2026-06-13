# pylint: disable=invalid-name
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
import unittest
from unittest.mock import AsyncMock, Mock, patch

from benqprojector.benqconnection import (
    BenQConnectionTimeoutError,
    BenQTelnetConnection,
)

HOST = "benqprojector-livingroom.local"
PORT = 8000


class Test(unittest.IsolatedAsyncioTestCase):
    async def _test_open(self, host: str, expected_url: str):
        connection = BenQTelnetConnection(host, PORT)
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
            url=expected_url,
            baudrate=9600,
            connect_timeout=10,
        )

        await connection.close()

    async def test_open_uses_socket_url(self):
        await self._test_open(HOST, f"socket://{HOST}:{PORT}")

    async def test_open_uses_ipv6_socket_url(self):
        await self._test_open("2001:db8::1", f"socket://[2001:db8::1]:{PORT}")

    async def test_open_timeout(self):
        connection = BenQTelnetConnection(HOST, PORT)

        with (
            patch(
                "benqprojector.benqconnection.serialx.open_serial_connection",
                AsyncMock(side_effect=TimeoutError),
            ),
            self.assertRaises(BenQConnectionTimeoutError),
        ):
            await connection.open()

    async def test_open_returns_false_on_connection_error(self):
        connection = BenQTelnetConnection(HOST, PORT)

        with (
            patch(
                "benqprojector.benqconnection.serialx.open_serial_connection",
                AsyncMock(
                    side_effect=ConnectionRefusedError(111, "Connection refused")
                ),
            ),
            patch("benqprojector.benqconnection.logger.exception") as log_exception,
        ):
            self.assertFalse(await connection.open())

        log_exception.assert_called_once_with("Unhandled OSError")
