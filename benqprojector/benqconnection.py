"""Implements the connection types for connecting to BenQ projectors.

Created on 25 Aug 2023

@author: Rogier van Staveren
"""

from abc import ABC, abstractmethod
import asyncio
import logging
import time
from typing import Any

import aiofiles
import serialx
from serialx import Parity, StopBits

logger = logging.getLogger(__name__)

# Timeout in seconds
_SERIAL_TIMEOUT = 0.05
_TELNET_TIMEOUT = 0.2

DEFAULT_PORT = 8000

# serialx URL schemes which connect over the network instead of a local serial port
NETWORK_URL_SCHEMES = (
    "socket://",
    "tcp://",
    "rfc2217://",
    "esphome://",
    "esphome-hass://",
)


class BenQConnectionError(Exception):
    """BenQ Connection Error.

    When an error occurs while connecting to the BenQ Projector.
    """


class BenQConnectionTimeoutError(BenQConnectionError):
    """BenQ Connection Timeout Error."""


class BenQConnection(ABC):
    """Abstract class on which the different connection types are build."""

    _reader: asyncio.StreamReader | None = None
    _writer: asyncio.StreamWriter | None = None
    _read_timeout: float | None = None
    _record_file: Any = None

    def __init__(self, record: bool = False):
        """Initialise a connection to the BenQ projector."""
        super().__init__()

        self._record = record

    @abstractmethod
    async def open(self) -> bool:
        """Opens the connection to the BenQ projector."""
        if self._record and self._record_file is None:
            file_name = time.strftime("%Y%m%d-%H%M%S.txt")
            self._record_file = await aiofiles.open(file_name, "ab")

        return True

    def is_open(self) -> bool:
        """Checks if the connection is open."""
        return self._writer is not None

    async def close(self) -> bool:
        """Closes the connection to the BenQ projector."""
        if self._record_file is not None:
            await self._record_file.close()
            self._record_file = None

        if self._writer is None:
            return True

        try:
            self._writer.close()
            await self._writer.wait_closed()
        except OSError, serialx.SerialException:
            pass

        self._reader = None
        self._writer = None

        if not self.is_open():
            logger.debug("Connection closed")
            return True

        logger.error("Failed to close connection")
        return False

    async def reset(self) -> bool:
        """Discard the already received input and drain the writer of the connection."""
        assert self._reader is not None, "Connection is not open"
        assert self._writer is not None, "Connection is not open"

        while True:
            try:
                # Returns buffered data immediately, times out if there is none
                async with asyncio.timeout(0):
                    data = await self._reader.read(1024)
            except TimeoutError:
                break
            if not data:
                break
            if self._record_file:
                await self._record_file.write(data)

        await self._writer.drain()
        return True

    async def read(self, size: int = 1) -> bytes:
        """Read size bytes from the connection."""
        assert self._reader is not None, "Connection is not open"
        if self._reader.at_eof():
            return b""

        try:
            response = await asyncio.wait_for(
                self._reader.read(size), timeout=self._read_timeout
            )

            if self._record_file:
                await self._record_file.write(response)
        except asyncio.exceptions.TimeoutError:
            return b""
        except (OSError, serialx.SerialException) as ex:
            await self.close()
            raise BenQConnectionError(str(ex)) from ex
        else:
            return response

        return b""

    async def readline(self) -> bytes:
        """Reads a line from the connection."""
        assert self._reader is not None, "Connection is not open"
        if self._reader.at_eof():
            return b""

        try:
            response = await asyncio.wait_for(
                self._reader.readline(), timeout=self._read_timeout
            )

            if self._record_file:
                await self._record_file.write(response)
        except asyncio.exceptions.TimeoutError:
            return b""
        except (OSError, serialx.SerialException) as ex:
            await self.close()
            raise BenQConnectionError(str(ex)) from ex
        else:
            return response

        return b""

    async def readuntil(self, separator: bytes | tuple[bytes, ...] = b"\n") -> bytes:
        """Read data until separator is found."""
        assert self._reader is not None, "Connection is not open"
        if self._reader.at_eof():
            return b""

        try:
            response = await asyncio.wait_for(
                self._reader.readuntil(separator), timeout=self._read_timeout
            )

            if self._record_file:
                await self._record_file.write(response)
        except asyncio.exceptions.TimeoutError:
            return b""
        except asyncio.IncompleteReadError as ex:
            logger.exception("Incomplete read")
            if ex.partial is not None:
                if self._record_file:
                    await self._record_file.write(ex.partial)
                return ex.partial
            return b""
        except (OSError, serialx.SerialException) as ex:
            await self.close()
            raise BenQConnectionError(str(ex)) from ex
        else:
            return response

        return b""

    async def write(self, data: bytes) -> int:
        """Output the given string over the connection."""
        assert self._writer is not None, "Connection is not open"
        try:
            self._writer.write(data)
            await self._writer.drain()

            return len(data)
        except (OSError, serialx.SerialException) as ex:
            await self.close()
            raise BenQConnectionError(str(ex)) from ex

    async def flush(self) -> None:  # noqa: B027
        """Flush write buffers, if applicable.

        Intentionally a no-op by default, subclasses can override this.
        """


class BenQSerialConnection(BenQConnection):
    """Class to handle the serial connection type."""

    _read_timeout = _SERIAL_TIMEOUT

    def __init__(self, path: str, baud_rate: int, record: bool = False):
        """Initialise a serial connection to the BenQ projector."""
        super().__init__(record)
        assert path is not None

        self._path = path
        self._baud_rate = baud_rate

        if self.is_network:
            self._read_timeout = _TELNET_TIMEOUT

    @property
    def is_network(self) -> bool:
        """True if the connection is a network connection instead of a local serial port."""
        return self._path.startswith(NETWORK_URL_SCHEMES)

    def __str__(self) -> str:
        """Return the path of the connection."""
        return self._path

    async def open(self) -> bool:
        """Open the connection."""
        try:
            if not self.is_open():
                (
                    self._reader,
                    self._writer,
                ) = await serialx.open_serial_connection(
                    url=self._path,
                    baudrate=self._baud_rate,
                    byte_size=8,
                    parity=Parity.NONE,
                    stopbits=StopBits.ONE,
                    timeout=1,
                )
        except (OSError, serialx.SerialException, serialx.UnsupportedSetting) as ex:
            raise BenQConnectionError(str(ex)) from ex

        return await super().open()
