"""
Implements the connection types for connecting to BenQ projectors.

Created on 25 Aug 2023

@author: Rogier van Staveren
"""
import logging
import telnetlib
from abc import ABC, abstractmethod

import serial

logger = logging.getLogger(__name__)

_SERIAL_TIMEOUT = 0.1
_TELNET_TIMEOUT = 1.0


class BenQConnectionError(Exception):
    """
    BenQ Connection Error.
    
    When an error occurs while connecting to the BenQ Projector.
    """


class BenQConnection(ABC):
    """
    Abstract class on which the different connection types are build.
    """

    is_open: bool = None

    @abstractmethod
    def open(self) -> bool:
        """
        Opens the connection to the BenQ projector.
        """
        raise NotImplementedError

    @abstractmethod
    def close(self) -> bool:
        """
        Closes the connection to the BenQ projector.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> bool:
        """
        Resets the input and output buffers of the connection.
        """
        raise NotImplementedError

    @abstractmethod
    def read(self, size: int = 1) -> bytes:
        """
        Read size bytes from the connection.
        """
        raise NotImplementedError

    @abstractmethod
    def readline(self) -> bytes:
        """
        Reads a line from the connection.
        """
        raise NotImplementedError

    def readlines(self) -> list[bytes]:
        """
        Reads all lines from the connection.
        """
        lines = []

        while True:
            line = self.readline()
            if not line:
                break
            lines.append(line)

        return lines

    @abstractmethod
    def write(self, data: bytes) -> int:
        """
        Output the given string over the connection.
        """
        raise NotImplementedError

    def flush(self) -> None:
        """
        Flush write buffers, if applicable.
        """


class BenQSerialConnection(BenQConnection):
    """
    Class to handle the serial connection type.
    """

    _connection = None

    def __init__(self, serial_port: str, baud_rate: int):
        assert serial_port is not None

        self._serial_port = serial_port
        self._baud_rate = baud_rate

    def __str__(self):
        return self._serial_port

    def open(self) -> bool:
        try:
            if self._connection is None:
                connection = serial.Serial(
                    port=self._serial_port,
                    baudrate=self._baud_rate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=_SERIAL_TIMEOUT,
                )

                # Open the connection
                if not connection.is_open:
                    connection.open()

                self._connection = connection
            elif not self._connection.is_open:
                # Try to repair the connection
                self._connection.open()

            if self._connection.is_open:
                return True

            return False
        except serial.SerialException as ex:
            raise BenQConnectionError(str(ex)) from ex

    @property
    def is_open(self):
        if self._connection:
            return self._connection.is_open

        return False

    def close(self) -> bool:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

        return True

    def reset(self) -> bool:
        self._connection.reset_input_buffer()
        self._connection.reset_output_buffer()

        return True

    def read(self, size: int = 1) -> bytes:
        try:
            return self._connection.read(size)
        except serial.SerialException as ex:
            raise BenQConnectionError(str(ex)) from ex

    def readline(self) -> bytes:
        try:
            return self._connection.readline()
        except serial.SerialException as ex:
            raise BenQConnectionError(str(ex)) from ex

    def readlines(self) -> bytes:
        try:
            return self._connection.readlines()
        except serial.SerialException as ex:
            raise BenQConnectionError(str(ex)) from ex

    def write(self, data: bytes) -> int:
        try:
            return self._connection.write(data)
        except serial.SerialException as ex:
            raise BenQConnectionError(str(ex)) from ex

    def flush(self) -> None:
        try:
            self._connection.flush()
        except serial.SerialException as ex:
            raise BenQConnectionError(str(ex)) from ex


class BenQTelnetConnection(BenQConnection):
    """
    Class to handle the telnet connection type.
    """

    _connection = None

    def __init__(self, host: str, port: int):
        assert host is not None
        assert port is not None

        self._host = host
        self._port = port

    def __str__(self):
        return f"{self._host}:{self._port}"

    def open(self) -> bool:
        try:
            if self._connection is None:
                connection = telnetlib.Telnet(self._host, self._port, _TELNET_TIMEOUT)
                self._connection = connection
    
            return True
        except (OSError, TimeoutError) as ex:
            raise BenQConnectionError(str(ex)) from ex

    @property
    def is_open(self):
        if self._connection:
            return True

        return False

    def close(self) -> bool:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

        return True

    def reset(self) -> bool:
        try:
            self._connection.read_very_eager()

            return True
        except EOFError as ex:
            logger.error("Connection lost: %s", ex)
            self.close()
            raise BenQConnectionError(str(ex)) from ex

    def read(self, size: int = 1) -> bytes:
        raise NotImplementedError

    def readline(self) -> bytes:
        try:
            # A short timeout makes the connection a lot more responsive
            return self._connection.read_until(b"\n", _TELNET_TIMEOUT / 5)
        except EOFError as ex:
            logger.error("Connection lost: %s", ex)
            self.close()
            raise BenQConnectionError(str(ex)) from ex

    def write(self, data: bytes) -> int:
        try:
            self._connection.write(data)
        except OSError as ex:
            raise BenQConnectionError(str(ex)) from ex

        return len(data)
