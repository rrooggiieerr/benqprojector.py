"""
Implements the connection types for connecting to BenQ projectors.

Created on 25 Aug 2023

@author: Rogier van Staveren
"""

import asyncio
import logging
import socket
import time
from abc import ABC, abstractmethod

import aiofiles
import serial
import serial_asyncio_fast as serial_asyncio

logger = logging.getLogger(__name__)

# Timeout in seconds
_SERIAL_TIMEOUT = 0.05
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
    _record_file = None

    def __init__(self, record: bool = False):
        super().__init__()

        self._record = record

    @abstractmethod
    async def open(self) -> bool:
        """
        Opens the connection to the BenQ projector.
        """
        if self._record:
            file_name = time.strftime("%Y%m%d-%H%M%S.txt")
            self._record_file = await aiofiles.open(file_name, "wb")

    def is_open(self):
        """
        Checks if the connection is open.
        """
        return self._writer is not None

    async def close(self) -> bool:
        """
        Closes the connection to the BenQ projector.
        """
        if self._record_file:
            await self._record_file.close()

        if not self.is_open():
            return True

        try:
            self._writer.close()
            await self._writer.wait_closed()
        except (ConnectionError, TimeoutError):
            pass
        except OSError as ex:
            if ex.errno in [64, 113]:
                # logger.exception("Connection error")
                pass
            else:
                logger.exception("Unhandeled OSError")

        self._reader = None
        self._writer = None

        if not self.is_open():
            logger.debug("Connection closed")
            return True

        logger.error("Failed to close connection")
        return False

    async def reset(self) -> bool:
        """
        Resets the reader and drains the writer of the connection.
        """
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
            response = await asyncio.wait_for(
                self._reader.read(size), timeout=self._read_timeout
            )

            if self._record_file:
                await self._record_file.write(response)

            return response
        except asyncio.exceptions.TimeoutError:
            return b""
        except (ConnectionError, TimeoutError) as ex:
            await self.close()
            raise BenQConnectionError(ex.strerror) from ex
        except OSError as ex:
            if ex.errno in [64, 113]:
                await self.close()
                raise BenQConnectionError(ex.strerror) from ex
            logger.exception("Unhandeled OSError")
            await self.close()

        return b""

    async def readline(self) -> bytes:
        """
        Reads a line from the connection.
        """
        if self._reader.at_eof():
            return b""

        try:
            response = await asyncio.wait_for(
                self._reader.readline(), timeout=self._read_timeout
            )

            if self._record_file:
                await self._record_file.write(response)

            return response
        except asyncio.exceptions.TimeoutError:
            return b""
        except (ConnectionError, TimeoutError) as ex:
            await self.close()
            raise BenQConnectionError(ex.strerror) from ex
        except OSError as ex:
            if ex.errno in [64, 113]:
                await self.close()
                raise BenQConnectionError(ex.strerror) from ex
            logger.exception("Unhandeled OSError")
            await self.close()

        return b""

    async def readuntil(self, separator=b"\n"):
        """
        Read data until separator is found.
        """
        if self._reader.at_eof():
            return b""

        try:
            response = await asyncio.wait_for(
                self._reader.readuntil(separator), timeout=self._read_timeout
            )

            if self._record_file:
                await self._record_file.write(response)

            return response
        except asyncio.exceptions.TimeoutError:
            return b""
        except asyncio.IncompleteReadError as ex:
            logger.exception("Incomplete read")
            if ex.partial is not None:
                return ex.partial
            return b""
        except (ConnectionError, TimeoutError) as ex:
            await self.close()
            raise BenQConnectionError(ex.strerror) from ex
        except OSError as ex:
            if ex.errno in [64, 113]:
                await self.close()
                raise BenQConnectionError(ex.strerror) from ex
            logger.exception("Unhandeled OSError")
            await self.close()

        return b""

    async def write(self, data: bytes) -> int:
        """
        Output the given string over the connection.
        """
        try:
            self._writer.write(data)
            await self._writer.drain()

            return len(data)
        except (ConnectionError, TimeoutError) as ex:
            await self.close()
            raise BenQConnectionError(ex.strerror) from ex
        except OSError as ex:
            if ex.errno in [64, 113]:
                await self.close()
                raise BenQConnectionError(ex.strerror) from ex
            logger.exception("Unhandeled OSError")
            await self.close()

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

    def __init__(self, serial_port: str, baud_rate: int, record: bool = False):
        super().__init__(record)
        assert serial_port is not None

        self._serial_port = serial_port
        self._baud_rate = baud_rate

    def __str__(self):
        return self._serial_port

    async def open(self) -> bool:
        await super().open()

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

    def __init__(self, host: str, port: int = DEFAULT_PORT, record: bool = False):
        super().__init__(record)
        assert host is not None
        assert port is not None

        self._host = host
        self._port = port

    def __str__(self):
        return f"{self._host}:{self._port}"

    async def open(self) -> bool:
        await super().open()

        try:
            if not self.is_open():
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port), timeout=10
                )

            return True
        except asyncio.exceptions.TimeoutError as ex:
            raise BenQConnectionTimeoutError(str(ex)) from ex
        except socket.gaierror as ex:
            raise BenQConnectionError(ex.strerror) from ex
        except OSError as ex:
            if ex.errno in [64, 113]:
                await self.close()
                raise BenQConnectionError(ex.strerror) from ex
            logger.exception("Unhandeled OSError")
            await self.close()

        return False
