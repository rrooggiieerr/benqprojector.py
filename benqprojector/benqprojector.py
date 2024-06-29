"""
Implements the BenQProjector class for controlling BenQ projectors.

Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import asyncio
import importlib.resources
import json
import logging
import re
import string
import sys
import time
from abc import ABC
from datetime import datetime
from typing import Any

from .benqconnection import (
    DEFAULT_PORT,
    BenQConnection,
    BenQConnectionError,
    BenQSerialConnection,
    BenQTelnetConnection,
)

logger = logging.getLogger(__name__)

BAUD_RATES = [2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200]

RESPONSE_RE_STRICT = r"^\*([^=]*)=([^#]*)#$"
RESPONSE_RE_LOSE = r"^\*?([^=]*)=([^#]*)#?$"

WHITESPACE = string.whitespace + "\x00"

_RESPONSE_TIMEOUT = 5.0
_CONNECTION_LOCK_TIMEOUT = 1


background_tasks = set()


def _add_background_task(task: asyncio.Task) -> None:
    # Add task to the set. This creates a strong reference.
    background_tasks.add(task)

    # To prevent keeping references to finished tasks forever, make each task remove its own
    # reference from the set after completion:
    task.add_done_callback(background_tasks.discard)


class BenQProjectorError(Exception):
    """Generic BenQ Projector error."""

    def __init__(self, command=None, action=None):
        self.command = command
        self.action = action


class IllegalFormatError(BenQProjectorError):
    """
    Illegal command format error.

    If a command format is illegal, it will echo Illegal format.
    """

    def __str__(self):
        return f"Illegal format for command '{self.command}' and action '{self.action}'"


class EmptyResponseError(BenQProjectorError):
    """
    Empty response error.

    If the response is empty.
    """

    def __str__(self):
        return f"Empty response for command '{self.command}' and action '{self.action}'"


class UnsupportedItemError(BenQProjectorError):
    """
    Unsupported item error.

    If a command with correct format is not valid for the projector model it will echo
    `Unsupported item`.
    """

    def __str__(self):
        return (
            f"Unsupported item for command '{self.command}' and action '{self.action}'"
        )


class BlockedItemError(BenQProjectorError):
    """
    Blocked item error.

    If a command with correct format cannot be executed under certain condition it will echo
    `Block item`.
    """

    def __str__(self):
        return f"Block item for command '{self.command}' and action '{self.action}'"


class InvallidResponseError(BenQProjectorError):
    """
    Invalid response error.

    If the response format does not match the expected format.
    """

    def __init__(self, command=None, action=None, response=None):
        super().__init__(command, action)
        self.response = response

    def __str__(self):
        return f"Invalid response for command '{self.command}' and action '{self.action}'. response: {self.response}"


class ResponseTimeoutError(BenQProjectorError, TimeoutError):
    """
    Response timeout error.

    If the response takes to long to receive.
    """

    def __str__(self):
        return (
            f"Response timeout for command '{self.command}' and action '{self.action}'"
        )


class PromptTimeoutError(ResponseTimeoutError):
    """
    Prompt timeout error.

    If the command prompt takes to long to receive.
    """

    def __str__(self):
        return f"Prompt timeout for command '{self.command}' and action '{self.action}'"


class TooBusyError(BenQProjectorError):
    """
    Too busy error.

    If the connection is to busy with processing other commands.
    """

    def __str__(self):
        return f"Too busy to send '{self.command}' and action '{self.action}'"


class BenQProjector(ABC):
    """
    BenQProjector class for controlling BenQ projectors.
    """

    connection = None
    _init: bool = True
    _has_to_wait_for_prompt = True

    _read_task = None
    _loop = None
    _listeners: list[Any]

    model = None
    _mac = None
    unique_id = None

    # Supported commands and modes
    projector_config_all = None
    projector_config = None
    _supported_commands = None
    video_sources = None
    audio_sources = None
    picture_modes = None
    color_temperatures = None
    aspect_ratios = None
    projector_positions = None
    lamp_modes = None
    threed_modes = None  # 3D modes
    menu_positions = None

    # Current modes
    video_source = None
    audio_source = None
    picture_mode = None
    color_temperature = None
    aspect_ratio = None
    projector_position = None
    lamp_mode = None
    threed_mode = None  # 3D mode

    POWERSTATUS_UNKNOWN = -1
    POWERSTATUS_OFF = 0
    POWERSTATUS_POWERINGON = 1
    POWERSTATUS_ON = 2
    POWERSTATUS_POWERINGOFF = 3

    power_status = POWERSTATUS_UNKNOWN
    _poweron_time = None
    _poweroff_time = None
    _power_timestamp = None
    direct_power_on = None

    lamp_time = None
    lamp2_time = None

    volume = None
    muted = None

    brilliant_color = None
    blank = None
    brightness = None
    color_value = None
    contrast = None
    high_altitude = None
    quick_auto_search = None
    sharpness = None

    # Compile regular expression to match the command response.
    _response_re = None

    # Some projectors do not echo the given command, the code tries to detect if this is the case
    _expect_command_echo = True

    def __init__(
        self,
        connection: BenQConnection,
        model_hint: str = None,
        strict_validation: bool = False,
    ):
        """
        Initialises the BenQProjector object.
        """
        assert connection is not None

        self.connection = connection
        self.model = model_hint

        if strict_validation:
            self._response_re = re.compile(RESPONSE_RE_STRICT)
        else:
            self._response_re = re.compile(RESPONSE_RE_LOSE)

        self._interactive = False
        if sys.stdin and sys.stdin.isatty() and logging.root.level == logging.INFO:
            # running interactively
            self._interactive = True

        self._connection_lock = asyncio.Lock()
        self._listeners = []
        self._listener_commands = []

    def busy(self):
        return self._connection_lock.locked()

    def _read_config(self, model: str):
        model_filename = (
            "".join(c if c.isalnum() or c in "._-" else "_" for c in model) + ".json"
        )
        with importlib.resources.open_text(
            "benqprojector.configs", model_filename
        ) as file:
            return json.load(file)

        return None

    async def get_config(self, key):
        if not self.projector_config_all:
            self.projector_config_all = await self._loop.run_in_executor(
                None, self._read_config, "all"
            )

        if not self.projector_config and self.model:
            try:
                self.projector_config = await self._loop.run_in_executor(
                    None, self._read_config, self.model
                )
            except FileNotFoundError:
                pass

        if self.projector_config:
            value = self.projector_config.get(key)
            if value is not None:
                return value

        # Fall back to generic config when key can not be found in configuration for model
        return self.projector_config_all.get(key)

    async def _connect(self) -> bool:
        if not self.connected():
            if self._loop is None:
                self._loop = asyncio.get_event_loop()

            logger.info("Connecting to %s", self.connection)
            await self.connection.open()
            logger.debug("Connected to %s", self.connection)

        if self.connected():
            return True

        return False

    async def connect(self, loop=None) -> bool:
        """
        Connect to the BenQ projector.
        """
        self._loop = loop

        if not await self._connect():
            return False

        if not self._init:
            return True

        if not self.model:
            self.projector_config = await self._loop.run_in_executor(
                None, self._read_config, "minimal"
            )

        power = None
        try:
            power = await self._send_command("pow")
            if power is None:
                logger.error("Failed to retrieve projector power state.")
        except PromptTimeoutError as ex:
            logger.error(
                "Failed to get projector command prompt, is your projector properly connected?"
            )
            return False
        except BlockedItemError as ex:
            logger.error(
                "Unable to retrieve projector power state, is projector powering down? %s",
                ex,
            )
        except EmptyResponseError as ex:
            logger.warning(ex)
        except BenQProjectorError as ex:
            logger.error("Unable to retrieve projector power state: %s", ex)
            return False

        model = None
        try:
            model = await self._send_command("modelname")
            assert model is not None, "Failed to retrieve projector model"
        except IllegalFormatError as ex:
            # W1000 does not seem to return projector model, but gives an illegal
            # format error. Maybe there are other models with the same problem?
            logger.error("Unable to retrieve projector model")
        except BlockedItemError as ex:
            # W1070/W1250 does not seem to return projector model when off, but gives
            # an blocked item error. Maybe there are other models with the same problem?
            if power == "off":
                logger.error(
                    "Unable to retrieve projector model while projector is %s: %s",
                    power,
                    ex,
                )
            else:
                # It could also be that the projector is powering down
                logger.error(
                    "Unable to retrieve projector model while projector is %s, is projector powering down? %s",
                    power,
                    ex,
                )

        if model is not None and model != self.model:
            self.model = model
            self.projector_config = None

        self._supported_commands = await self.get_config("commands")
        self.video_sources = await self.get_config("sources")
        self.audio_sources = await self.get_config("audio_sources")
        self.picture_modes = await self.get_config("picture_modes")
        self.color_temperatures = await self.get_config("color_temperatures")
        self.aspect_ratios = await self.get_config("aspect_ratios")
        self.projector_positions = await self.get_config("projector_positions")
        self.lamp_modes = await self.get_config("lamp_modes")
        self.threed_modes = await self.get_config("3d_modes")
        self.menu_positions = await self.get_config("menu_positions")

        self._poweron_time = await self.get_config("poweron_time")
        self._poweroff_time = await self.get_config("poweroff_time")

        mac = None
        if self.supports_command("macaddr"):
            mac = await self.send_command("macaddr")

        if mac is not None:
            self._mac = mac.lower()
            self.unique_id = self._mac

        logger.info("Device on %s available", self.connection)

        await self.update_power()

        self._init = False

        if self._read_task is None and len(self._listeners) > 0:
            self._read_task = asyncio.create_task(self._read_coroutine())
            _add_background_task(self._read_task)

        return True

    def connected(self) -> bool:
        if self.connection and self.connection.is_open():
            return True

        return False

    async def _disconnect(self):
        await self.connection.close()

    async def disconnect(self):
        """Disconnect from the BenQ projector."""
        if self.connected():
            await self._cancel_read()
            await self._disconnect()

    def add_listener(self, listener=None, command: str = None):
        """
        Adds a Callback to the BenQ projector.
        """
        if command is not None and command not in self._listener_commands:
            self._listener_commands.append(command)

        if listener is not None:
            self._listeners.append(listener)

            if self._read_task == None:
                self._read_task = asyncio.create_task(self._read_coroutine())
                _add_background_task(self._read_task)

    def _forward_to_listeners(self, command: str, data: Any | None):
        for listener in self._listeners:
            try:
                listener(command, data)
            # pylint: disable=broad-exception-caught
            except Exception:
                logger.exception("Exception in Callback: %s", listener)

    async def _cancel_read(self) -> bool:
        if self._read_task is not None and not (
            self._read_task.done() or self._read_task.cancelled()
        ):
            return self._read_task.cancel()

        return True

    async def _read_coroutine(self):
        """
        Reads the current status of the projector in a loop
        """
        previous_data = {}

        while True:
            try:
                if not self.connected():
                    await self._connect()

                if self.connected() and not self.busy():
                    await self.update_power()
                    if self.power_status is not None:
                        if previous_data.get("pow") != self.power_status:
                            self._forward_to_listeners("pow", self.power_status)
                            previous_data["pow"] = self.power_status

                        if self.power_status == self.POWERSTATUS_ON:
                            await self.update_volume()
                            if previous_data.get("mute") != self.muted:
                                self._forward_to_listeners("mute", self.muted)
                                previous_data["mute"] = self.muted
                            if previous_data.get("vol") != self.volume:
                                self._forward_to_listeners("vol", self.volume)
                                previous_data["vol"] = self.volume

                            await self.update_video_source()
                            if previous_data.get("sour") != self.video_source:
                                self._forward_to_listeners("sour", self.video_source)
                                previous_data["sour"] = self.video_source

                            for command in self._listener_commands:
                                if command not in ["pow", "mute", "vol", "sour"]:
                                    data = await self.send_command(command)
                                    if (
                                        data is not None
                                        and previous_data.get(command) != data
                                    ):
                                        self._forward_to_listeners(command, data)
                                        previous_data[command] = data
                        else:
                            for command in ["pp", "ltim", "ltim2"]:
                                if command in self._listener_commands and command not in previous_data:
                                    data = await self.send_command(command)
                                    if (
                                        data is not None
                                        and previous_data.get(command) != data
                                    ):
                                        self._forward_to_listeners(command, data)
                                        previous_data[command] = data

                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                logger.debug("Read coroutine was canceled")
                break
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                logger.exception("Error communicating with BenQ projector")
                await self._disconnect()
                # break
            except Exception:
                logger.exception("Unexpected error")
                break

        self._read_task = None
        logger.debug("Read coroutine stopped")

    def supports_command(self, command) -> bool:
        """
        Test if a command is supported by the projector.

        If the list of supported commands is not (yet) set it is assumed the command is supported.
        """
        return self._supported_commands is None or command in self._supported_commands

    async def _send_command(self, command: str, action: str = "?") -> str:
        """
        Send a command to the BenQ projector.
        """
        command = command.lower()

        if not self.supports_command(command):
            logger.warning("Command %s not supported", command)
            return None

        if await self._connect() is False:
            logger.error("Connection not available")
            return None

        try:
            locked = await asyncio.wait_for(
                self._connection_lock.acquire(), timeout=_CONNECTION_LOCK_TIMEOUT
            )
            if not locked:
                raise TooBusyError(command, action)
        except TimeoutError as ex:
            raise TooBusyError(command, action) from ex

        response = None

        try:
            _command = f"*{command}={action}#"
            await self._send_raw_command(_command)

            empty_line_count = 0
            echo_received = None
            previous_response = None
            while True:
                if empty_line_count > 5:
                    if self._init:
                        logger.error(
                            "More than 5 empty responses, is your cable right?"
                        )
                    if echo_received and previous_response:
                        # It's possible that the previous response is
                        # misinterpreted as being the command echo while it
                        # actually was the command response.
                        # In that case we continue the response processing
                        # using the previous response.
                        response = previous_response
                    else:
                        raise EmptyResponseError(command, action)
                elif (response := await self._read_response()) == "":
                    logger.debug("Empty line")
                    # Empty line
                    empty_line_count += 1
                    # Some projectors (X3000i) seem to return an empty line
                    # instead of a command echo in some cases.
                    # For that reason only give the projector some more time
                    # to respond after more than 1 empty line.
                    if empty_line_count > 1:
                        # Give the projector some more time to response
                        await asyncio.sleep(0.05)
                    continue

                if response == ">":
                    logger.debug("Response is command prompt >")
                    self._has_to_wait_for_prompt = True
                    continue

                if action == "?" and not echo_received and response in (_command, f">{_command}"):
                    # Command echo.
                    logger.debug("Command successfully send")
                    echo_received = True
                    self._expect_command_echo = True
                    continue

                if self._expect_command_echo and not echo_received:
                    if action != "?" and response == _command:
                        # Command echo.
                        logger.debug("Command successfully send")
                        echo_received = True
                        previous_response = response
                        continue
                    logger.debug("No command echo received")
                    self._expect_command_echo = False

                return self._parse_response(command, action, _command, response)
        except BenQProjectorError as ex:
            ex.command = command
            ex.action = action
            raise
        except BenQConnectionError as ex:
            logger.exception(
                "Problem communicating with %s, reason: %s", self.unique_id, ex
            )
            return None
        finally:
            self._connection_lock.release()

    async def _wait_for_prompt(self) -> bool:
        # Clean input buffer
        await self.connection.reset()

        if not self._has_to_wait_for_prompt:
            await self.connection.write(b"\r")
            await self.connection.read(1)
            return True

        start_time = datetime.now()
        while True:
            response = await self.connection.read(100)
            if response == b"":
                await self.connection.write(b"\r")
            elif response[-1:] == b">":
                self._has_to_wait_for_prompt = False
                return True
            elif response.strip(WHITESPACE.encode()) == b"":
                pass
            elif response.strip(WHITESPACE.encode()) == b">":
                pass
            else:
                logger.warning("Unexpected response: %s", response)

            if (datetime.now() - start_time).total_seconds() > 1:
                raise PromptTimeoutError()

            await asyncio.sleep(0.05)

        return False

    async def _read_response(self) -> str:
        response = b""
        last_response = datetime.now()
        while True:
            _response = await self.connection.readline()
            if len(_response) > 0:
                response += _response
                if any(c in _response for c in [b"\n", b"\r", b"\x00"]):
                    response = response.decode()
                    # Cleanup response
                    response = response.strip(WHITESPACE)
                    logger.debug("Response: %s", response)

                    return response
                last_response = datetime.now()

            if (datetime.now() - last_response).total_seconds() > _RESPONSE_TIMEOUT:
                logger.warning("Timeout while waiting for response")
                self._has_to_wait_for_prompt = True
                raise ResponseTimeoutError()

            logger.debug("Waiting for response")
            await asyncio.sleep(0.05)

    async def _send_raw_command(self, command: str) -> str:
        """
        Send a raw command to the BenQ projector.
        """
        await self._wait_for_prompt()

        logger.debug("command %s", command)
        await self.connection.write(f"{command}\r".encode("ascii"))

    def _parse_response(self, command, action, _command, response):
        # Lowercase the response
        response = response.lower()
        logger.debug("LC Response: %s", response)

        if response in ["*illegal format#", "illegal format"]:
            if not self._interactive:
                logger.error("Command %s illegal format", _command)
            raise IllegalFormatError(command, action)

        if response in ["*unsupported item#", "unsupported item"]:
            if not self._interactive:
                logger.warning("Command %s unsupported item", _command)
            raise UnsupportedItemError(command, action)

        if response in ["*block item#", "block item"]:
            if not self._interactive:
                logger.warning("Command %s blocked item", _command)
            raise BlockedItemError(command, action)

        logger.debug("Raw response: '%s'", response)
        matches = self._response_re.match(response)
        if not matches:
            logger.error("Unexpected response format, response: %s", response)
            raise InvallidResponseError(command, action, response)
        response: str = matches.group(2)

        # Strip any spaces from the response
        response = response.strip(WHITESPACE)

        logger.debug("Processed response: %s", response)

        return response

    async def send_command(self, command: str, action: str = "?") -> str:
        """
        Send a command to the BenQ projector.
        """
        response = None

        try:
            response = await self._send_command(command, action)
        except BenQProjectorError:
            pass

        return response

    async def send_raw_command(self, command: str) -> str:
        """
        Send a raw command to the BenQ projector.
        """
        try:
            locked = await asyncio.wait_for(
                self._connection_lock.acquire(), timeout=_CONNECTION_LOCK_TIMEOUT
            )
            if not locked:
                raise TooBusyError(command)
        except TimeoutError as ex:
            raise TooBusyError(command) from ex

        response = None

        try:
            await self._send_raw_command(command)

            # Read and log the response
            while _response := await self._read_response():
                logger.debug(_response)
                response += _response
        except BenQProjectorError as ex:
            ex.command = command
            raise
        except BenQConnectionError as ex:
            logger.exception(
                "Problem communicating with %s, reason: %s", self.unique_id, ex
            )
            return None
        finally:
            self._connection_lock.release()

        return response

    async def detect_commands(self):
        """
        Detects which command are supported by the projector.

        This is done by trying out all know commands.
        """
        if self._interactive:
            print("Supported commands:", end="", flush=True)
        else:
            logger.info("Detecting supported commands")

        # Empty the current list of supported commands.
        self._supported_commands = None
        supported_commands = []
        ignore_commands = [
            "menu",
            "up",
            "down",
            "left",
            "right",
            "enter",
            "back",
            "zoomi",
            "zoomo",
            "auto",
            "focus",
            "error",
        ]
        # Loop through all known commands and test if a response is given.
        for command in self.projector_config_all.get("commands"):
            if command not in ignore_commands:
                retries = 0
                while True:
                    try:
                        try:
                            response = await self._send_command(command)
                            if response is not None:
                                supported_commands.append(command)
                            else:
                                command = None
                        except BlockedItemError:
                            supported_commands.append(command)
                            command = f"{command}?"
                        except ResponseTimeoutError:
                            if retries < 2:
                                retries += 1
                                continue

                            supported_commands.append(command)
                            command = f"{command}¿"

                        if command:
                            # A response is given, the command is supported.
                            if self._interactive:
                                print(f" {command}", end="", flush=True)
                            else:
                                logger.info("Command %s supported", command)
                    except BenQProjectorError:
                        pass
                    finally:
                        # Give the projector some time to process command
                        await asyncio.sleep(0.2)
                    break
        # Set the list of known commands.
        self._supported_commands = supported_commands

        if self._interactive:
            print()

        return self._supported_commands

    async def _detect_modes(self, description, command, all_modes):
        """
        Detect which modes are supported by the projector.

        This is done by trying out all know modes.
        """
        if not self.supports_command(command):
            return []

        if self._interactive:
            print(f"Supported {description}:", end="", flush=True)
        else:
            logger.info("Detecting supported video sources")

        # Store current mode
        current_mode = await self.send_command(command)
        if not self._interactive:
            logger.info("Current %s: %s", description, current_mode)
        if current_mode is None:
            return []

        supported_modes = []
        # Loop through all known modes and test if a response is given.
        for mode in all_modes:
            try:
                try:
                    response = await self._send_command(command, mode)
                    if response is not None:
                        supported_modes.append(mode)
                    else:
                        mode = None
                except BlockedItemError:
                    supported_modes.append(mode)
                    mode = f"{mode}?"
                except ResponseTimeoutError:
                    supported_modes.append(mode)
                    mode = f"{mode}¿"

                if mode:
                    # A response is given, the mode is supported.
                    if self._interactive:
                        print(f" {mode}", end="", flush=True)
                    else:
                        logger.debug("Mode %s supported", mode)
            except BenQProjectorError:
                pass
            finally:
                # Give the projector some time to process command
                await asyncio.sleep(0.2)

        # Revert mode back to current mode
        self.send_command(command, current_mode)

        if self._interactive:
            print()

        return supported_modes

    async def detect_video_sources(self):
        """
        Detect which video sources are supported by the projector.
        """
        self.video_sources = await self._detect_modes(
            "video sources", "sour", self.projector_config_all.get("sources")
        )
        return self.video_sources

    async def detect_audio_sources(self):
        """
        Detect which audio sources are supported by the projector.
        """
        self.audio_sources = await self._detect_modes(
            "audio sources", "audiosour", self.projector_config_all.get("audio_sources")
        )
        return self.audio_sources

    async def detect_picture_modes(self):
        """
        Detect which picture modes are supported by the projector.
        """
        self.picture_modes = await self._detect_modes(
            "picture modes", "appmod", self.projector_config_all.get("picture_modes")
        )
        return self.picture_modes

    async def detect_color_temperatures(self):
        """
        Detect which color temperatures are supported by the projector.
        """
        self.color_temperatures = await self._detect_modes(
            "color temperatures",
            "ct",
            self.projector_config_all.get("color_temperatures"),
        )
        return self.color_temperatures

    async def detect_aspect_ratios(self):
        """
        Detect which aspect ratios are supported by the projector.
        """
        self.aspect_ratios = await self._detect_modes(
            "aspect ratios", "asp", self.projector_config_all.get("aspect_ratios")
        )
        return self.aspect_ratios

    async def detect_projector_positions(self):
        """
        Detect which projector positions are supported by the projector.
        """
        self.projector_positions = await self._detect_modes(
            "projector positions",
            "pp",
            self.projector_config_all.get("projector_positions"),
        )
        return self.projector_positions

    async def detect_lamp_modes(self):
        """
        Detect which lamp modes are supported by the projector.
        """
        self.lamp_modes = await self._detect_modes(
            "lamp modes", "lampm", self.projector_config_all.get("lamp_modes")
        )
        return self.lamp_modes

    async def detect_3d_modes(self):
        """
        Detect which 3d modes are supported by the projector.
        """
        self.threed_modes = await self._detect_modes(
            "3d modes", "3d", self.projector_config_all.get("3d_modes")
        )
        return self.threed_modes

    async def detect_menu_positions(self):
        """
        Detect which menu positions are supported by the projector.
        """
        self.menu_positions = await self._detect_modes(
            "menu positions",
            "menuposition",
            self.projector_config_all.get("menu_positions"),
        )
        return self.menu_positions

    async def detect_projector_features(self):
        """
        Detect which features are supported by the projector.
        """
        if self.power_status == BenQProjector.POWERSTATUS_OFF:
            logger.error("Projector needs to be on to examine it's features.")
            return None

        config = {}

        config["commands"] = await self.detect_commands()
        await asyncio.sleep(2)  # Give the projector some time to settle
        config["video_sources"] = await self.detect_video_sources()
        await asyncio.sleep(2)
        config["audio_sources"] = await self.detect_audio_sources()
        await asyncio.sleep(2)
        config["picture_modes"] = await self.detect_picture_modes()
        await asyncio.sleep(2)
        config["color_temperatures"] = await self.detect_color_temperatures()
        await asyncio.sleep(2)
        config["aspect_ratios"] = await self.detect_aspect_ratios()
        await asyncio.sleep(2)
        config["projector_positions"] = await self.detect_projector_positions()
        await asyncio.sleep(2)
        config["lamp_modes"] = await self.detect_lamp_modes()
        await asyncio.sleep(2)
        config["3d_modes"] = await self.detect_3d_modes()
        await asyncio.sleep(2)
        config["menu_positions"] = await self.detect_menu_positions()

        return config

    async def update_power(self) -> bool:
        """Update the current power state."""
        response = await self.send_command("pow")
        if response is None:
            if self.power_status == self.POWERSTATUS_POWERINGON:
                logger.debug("Projector still powering on")
                return True
            if self.power_status == self.POWERSTATUS_POWERINGOFF:
                logger.debug("Projector still powering off")
                return True

        if response == "off":
            if (
                self.power_status == self.POWERSTATUS_POWERINGOFF
                and (time.time() - self._power_timestamp) <= self._poweroff_time
            ):
                logger.debug("Projector still powering off")
            else:
                self.power_status = self.POWERSTATUS_OFF
                self._power_timestamp = None

            return True

        if response == "on":
            if (
                self.power_status == self.POWERSTATUS_POWERINGON
                and (time.time() - self._power_timestamp) <= self._poweron_time
            ):
                logger.debug("Projector still powering on")
            else:
                self.power_status = self.POWERSTATUS_ON
                self._power_timestamp = None

            return True

        logger.error("Unknown power status: %s", response)
        # self.power_status = self.POWERSTATUS_UNKNOWN
        return False

    async def update_volume(self) -> bool:
        """Update the current volume state."""
        if self.supports_command("mute"):
            self.muted = await self.send_command("mute") == "on"
            logger.debug("Muted: %s", self.muted)

        if self.supports_command("vol"):
            volume = await self.send_command("vol")
            if volume is not None:
                try:
                    volume = int(volume)
                except ValueError:
                    volume = None
            logger.debug("Volume: %s", volume)

            self.volume = volume

    async def update_video_source(self) -> bool:
        """Update the current video source state."""
        if self.supports_command("sour"):
            self.video_source = await self.send_command("sour")
            logger.debug("Video source: %s", self.video_source)

    async def update(self) -> bool:
        """
        Update all known states.

        This takes quite a lot of time.
        """
        if not await self.update_power():
            return False

        if self.supports_command("directpower"):
            self.direct_power_on = await self.send_command("directpower") == "on"
            logger.debug("Direct power on: %s", self.direct_power_on)

        if self.supports_command("ltim"):
            response = await self.send_command("ltim")
            if response is not None:
                self.lamp_time = int(response)

        if self.supports_command("ltim2"):
            response = await self.send_command("ltim2")
            if response is not None:
                self.lamp2_time = int(response)

        if self.power_status in [self.POWERSTATUS_OFF, self.POWERSTATUS_ON]:
            # Commands which only work when powered on or off, not when
            # powering on or off
            if self.supports_command("pp"):
                self.projector_position = await self.send_command("pp")

        if self.power_status in [self.POWERSTATUS_POWERINGOFF, self.POWERSTATUS_OFF]:
            self.threed_mode = None
            self.picture_mode = None
            self.aspect_ratio = None
            self.brilliant_color = None
            self.blank = None
            self.brightness = None
            self.color_value = None
            self.contrast = None
            self.color_temperature = None
            self.high_altitude = None
            self.lamp_mode = None
            self.sharpness = None

            self.video_source = None

            self.muted = None
            self.volume = None
        elif self.power_status in [self.POWERSTATUS_POWERINGON, self.POWERSTATUS_ON]:
            # Commands which only work when powered on
            if self.supports_command("3d"):
                self.threed_mode = await self.send_command("3d")
                logger.debug("3D: %s", self.threed_mode)

            if self.supports_command("appmod"):
                self.picture_mode = await self.send_command("appmod")
                logger.debug("Picture mode: %s", self.picture_mode)

            if self.supports_command("asp"):
                self.aspect_ratio = await self.send_command("asp")
                logger.debug("Aspect ratio: %s", self.aspect_ratio)

            if self.supports_command("bc"):
                self.brilliant_color = await self.send_command("bc") == "on"
                logger.debug("Brilliant color: %s", self.brilliant_color)

            if self.supports_command("blank"):
                self.blank = await self.send_command("blank") == "on"
                logger.debug("Blank: %s", self.blank)

            if self.supports_command("bri"):
                response = await self.send_command("bri")
                if response is not None:
                    self.brightness = int(response)
                    logger.debug("Brightness: %s", self.brightness)

            if self.supports_command("color"):
                response = await self.send_command("color")
                if response is not None:
                    self.color_value = int(response)
                    logger.debug("Color value: %s", self.color_value)

            if self.supports_command("con"):
                response = await self.send_command("con")
                if response is not None:
                    self.contrast = int(response)
                    logger.debug("Contrast: %s", self.contrast)

            if self.supports_command("ct"):
                self.color_temperature = await self.send_command("ct")
                logger.debug("Color temperature: %s", self.color_temperature)

            if self.supports_command("highaltitude"):
                self.high_altitude = await self.send_command("highaltitude") == "on"
                logger.debug("High altitude: %s", self.high_altitude)

            if self.supports_command("lampm"):
                self.lamp_mode = await self.send_command("lampm")
                logger.debug("Lamp mode: %s", self.lamp_mode)

            if self.supports_command("qas"):
                self.quick_auto_search = await self.send_command("qas") == "on"
                logger.debug("Quick auto search: %s", self.quick_auto_search)

            if self.supports_command("sharp"):
                self.sharpness = await self.send_command("sharp")
                logger.debug("Sharpness: %s", self.sharpness)

            await self.update_video_source()
            await self.update_volume()

        return True

    async def turn_on(self):
        """
        Turn the projector on.

        First it tests if the projector is in a state that powering on is possible.
        """
        # Check the actual power state of the projector.
        response = await self.send_command("pow")
        if response == "on":
            # The projector is already on.
            if (
                self.power_status == self.POWERSTATUS_POWERINGON
                and (time.time() - self._power_timestamp) <= self._poweron_time
            ):
                logger.debug("Projector still powering on")
            else:
                self.power_status = self.POWERSTATUS_ON
                self._power_timestamp = None

            return True

        if response == "off":
            # The projector is off, calculate if the power off time has already passed
            if (
                self.power_status == self.POWERSTATUS_POWERINGOFF
                and (time.time() - self._power_timestamp) <= self._poweroff_time
            ):
                logger.warning("Projector still powering off")
                return False
            self.power_status = self.POWERSTATUS_OFF
            self._power_timestamp = None

            # Continue powering on the projector.
            logger.info("Turning on projector")
            response = await self.send_command("pow", "on")
            if response == "on":
                self.power_status = self.POWERSTATUS_POWERINGON
                self._power_timestamp = time.time()

                return True

            logger.error("Failed to turn on projector, response: %s", response)

        return False

    async def turn_off(self):
        """
        Turn the projector off.

        First it tests if the projector is in a state that powering off is possible.
        """
        # Check the actual power state of the projector.
        response = await self.send_command("pow")
        if response == "off":
            # The projector is already off.
            if (
                self.power_status == self.POWERSTATUS_POWERINGOFF
                and (time.time() - self._power_timestamp) <= self._poweroff_time
            ):
                logger.debug("Projector still powering off")
            else:
                self.power_status = self.POWERSTATUS_OFF
                self._power_timestamp = None

            return True

        if response == "on":
            # The projector is on, calculate if the power on time has already passed
            if (
                self.power_status == self.POWERSTATUS_POWERINGON
                and (time.time() - self._power_timestamp) <= self._poweron_time
            ):
                logger.warning("Projector still powering on")
                return False
            self.power_status = self.POWERSTATUS_ON
            self._power_timestamp = None

            # Continue powering off the projector.
            logger.info("Turning off projector")
            response = await self.send_command("pow", "off")
            if response == "off":
                self.power_status = self.POWERSTATUS_POWERINGOFF
                self._power_timestamp = time.time()

                return True

            logger.error("Failed to turn off projector, response: %s", response)

        return False

    async def mute(self):
        """Mutes the volume."""
        response = await self.send_command("mute", "on")
        if response == "on":
            self.muted = True
            return True

        return False

    async def unmute(self):
        """Unmutes the volume."""
        response = await self.send_command("mute", "off")
        if response == "off":
            self.muted = False
            return True

        return False

    async def volume_up(self) -> None:
        """Increase volume."""
        if self.volume is None:
            self.update_volume()
        elif self.volume >= 20:  # Can't go higher than 20
            return False

        if await self.send_command("vol", "+") == "+":
            self.volume += 1
            return True

        return False

    async def volume_down(self) -> None:
        """Decrease volume."""
        if self.volume is None:
            self.update_volume()
        elif self.volume <= 0:  # Can't go lower than 0
            return False

        if await self.send_command("vol", "-") == "-":
            self.volume -= 1
            return True

        return False

    async def volume_level(self, level) -> None:
        """Set volume to a given level."""
        if self.volume == level:
            return True

        while self.volume < level:
            if not await self.volume_up():
                return False

        while self.volume > level:
            if not await self.volume_down():
                return False

        return True

    async def select_video_source(self, video_source: str):
        """Select projector video source."""
        video_source = video_source.lower()

        if video_source not in self.video_sources:
            return False

        if await self.send_command("sour", video_source) == video_source:
            self.video_source = video_source
            return True

        return False


class BenQProjectorSerial(BenQProjector):
    """
    BenQ Projector class for controlling BenQ projectors over a serial connection.
    """

    def __init__(
        self,
        serial_port: str,  # The serial port where the RS-485 interface and
        # screen is connected to.
        baud_rate: int,
        model_hint: str = None,
        strict_validation: bool = False,
    ) -> None:
        """
        Initializes the BenQProjectorSerial object.
        """
        assert serial_port is not None
        assert baud_rate in BAUD_RATES, "Not a valid baud rate"

        self.unique_id = serial_port

        connection = BenQSerialConnection(serial_port, baud_rate)

        super().__init__(connection, model_hint, strict_validation)


class BenQProjectorTelnet(BenQProjector):
    """
    BenQ Projector class for controlling BenQ projectors over a Telnet connection.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        model_hint: str = None,
        strict_validation: bool = False,
    ) -> None:
        """
        Initializes the BenQProjectorTelnet object.
        """
        assert host is not None
        assert port is not None

        self.unique_id = f"{host}:{port}"

        connection = BenQTelnetConnection(host, port)

        super().__init__(connection, model_hint, strict_validation)
