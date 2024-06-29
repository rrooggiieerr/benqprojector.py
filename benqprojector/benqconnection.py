"""
Implements the connection types for connecting to BenQ projectors.

Created on 25 Aug 2023

@author: Rogier van Staveren
"""

import asyncio
import logging
from abc import ABC, abstractmethod

import serial
import serial_asyncio_fast as serial_asyncio

logger = logging.getLogger(__name__)

_SERIAL_TIMEOUT = 0.1
_TELNET_TIMEOUT = 0.2

DEFAULT_PORT = 8000


class BenQConnectionError(Exception):
    """
    BenQ Connection Error.

    When an error occurs while connecting to the BenQ Projector.
    """


class BenQConnectionTimeoutError(BenQConnectionError):
    """
    BenQ Connection Timeout Error.
    """


class BenQConnection(ABC):
    """
    Abstract class on which the different connection types are build.
    """

    _reader: asyncio.StreamReader = None
    _writer: asyncio.StreamWriter = None
    _read_timeout = None

    @abstractmethod
    async def open(self) -> bool:
        """
        Opens the connection to the BenQ projector.
        """
        raise NotImplementedError

    def is_open(self):
        if self._writer is not None:
            return True

        return False

    async def close(self) -> bool:
        """
        Closes the connection to the BenQ projector.
        """
        if self.is_open():
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError):
                logger.exception("Connection reset")
                self.close()

            self._reader = None
            self._writer = None

        if not self.is_open():
            logger.debug("Connection closed")
            return True

        logger.error("Failed to close connection")
        return False

    async def reset(self) -> bool:
        await self.read(-1)
        await self._writer.drain()
        return True

    async def read(self, size: int = 1) -> bytes:
        """
        Read size bytes from the connection.
        """
        if self._reader.at_eof():
            return b""

        try:
            return await asyncio.wait_for(
                self._reader.read(size), timeout=self._read_timeout
            )
        except TimeoutError:
            return b""

    async def readline(self) -> bytes:
        """
        Reads a line from the connection.
        """
        if self._reader.at_eof():
            return b""

        try:
            return await asyncio.wait_for(
                self._reader.readline(), timeout=self._read_timeout
            )
        except TimeoutError:
            return b""

    async def readlines(self) -> list[bytes]:
        """
        Reads all lines from the connection.
        """
        try:
            return await asyncio.wait_for(
                self._reader.readlines(), timeout=self._read_timeout
            )
        except TimeoutError:
            return []

    async def write(self, data: bytes) -> int:
        """
        Output the given string over the connection.
        """
        try:
            self._writer.write(data)
            await self._writer.drain()

            return len(data)
        except ConnectionResetError as ex:
            await self.close()
            raise BenQConnectionError(str(ex)) from ex

    async def flush(self) -> None:
        """
        Flush write buffers, if applicable.
        """
        # await self.read(-1)


class BenQSerialConnection(BenQConnection):
    """
    Class to handle the serial connection type.
    """

    _read_timeout = _SERIAL_TIMEOUT

    def __init__(self, serial_port: str, baud_rate: int):
        super().__init__()
        assert serial_port is not None

        self._serial_port = serial_port
        self._baud_rate = baud_rate

    def __str__(self):
        return self._serial_port

    async def open(self) -> bool:
        try:
            if not self.is_open():
                self._reader, self._writer = (
                    await serial_asyncio.open_serial_connection(
                        url=self._serial_port,
                        baudrate=self._baud_rate,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        timeout=_SERIAL_TIMEOUT,
                    )
                )

            return True
        except serial.SerialException as ex:
            raise BenQConnectionError(str(ex)) from ex

        return False


class BenQTelnetConnection(BenQConnection):
    """
    Class to handle the telnet connection type.
    """

    _read_timeout = _TELNET_TIMEOUT

    def __init__(self, host: str, port: int = DEFAULT_PORT):
        super().__init__()
        assert host is not None
        assert port is not None

        self._host = host
        self._port = port

    def __str__(self):
        return f"{self._host}:{self._port}"

    async def open(self) -> bool:
        try:
            if not self.is_open():
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port), timeout=10
                )

            return True
        except TimeoutError as ex:
            raise BenQConnectionTimeoutError(str(ex)) from ex
