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

from .benqclasses import (
    BenQBlockedItemError,
    BenQCommand,
    BenQEmptyResponseError,
    BenQIllegalFormatError,
    BenQInvallidResponseError,
    BenQProjectorError,
    BenQPromptTimeoutError,
    BenQRawCommand,
    BenQResponseTimeoutError,
    BenQTooBusyError,
    BenQUnsupportedItemError,
)
from .benqconnection import (
    DEFAULT_PORT,
    BenQConnection,
    BenQConnectionError,
    BenQSerialConnection,
    BenQTelnetConnection,
)

logger = logging.getLogger(__name__)

BAUD_RATES = [2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200]

RESPONSE_RE_STRICT = re.compile(r"^\*([^=]*)=([^#]*)#$")
RESPONSE_RE_LOOSE = re.compile(r"^\*?([^=]*)=([^#]*)#?$")
RESPONSE_RE_STATE_ONLY = re.compile(r"^\*?()([^#]*?)#?$")

WHITESPACE = string.whitespace + "\x00"
END_OF_RESPONSE = b"#\n\r\x00"

_RESPONSE_TIMEOUT = 5.0
_CONNECTION_LOCK_TIMEOUT = 1


background_tasks = set()


def _add_background_task(task: asyncio.Task) -> None:
    # Add task to the set. This creates a strong reference.
    background_tasks.add(task)

    # To prevent keeping references to finished tasks forever, make each task remove its own
    # reference from the set after completion:
    task.add_done_callback(background_tasks.discard)


class BenQProjector(ABC):
    """
    BenQProjector base class for controlling BenQ projectors.
    """

    connection: BenQConnection | None = None
    # Projectors with integrated network don't seem to have a command prompt, the code tries to
    # detect if this is the case
    has_prompt = None
    _separator = b"\n"

    _init: bool = True
    _has_to_wait_for_prompt = True
    _use_volume_increments = False

    _read_task = None
    _loop = None
    _listeners: list[Any]
    _interval: int = None

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

    # Some projectors do not echo the given command, the code tries to detect if this is the case
    _expect_command_echo = True

    def __init__(
        self,
        connection: BenQConnection,
        model_hint: str = None,
    ):
        """
        Initialises the BenQProjector object.
        """
        assert connection is not None

        self.connection = connection
        self.model = model_hint

        self._interactive = False
        if sys.stdin and sys.stdin.isatty() and logging.root.level == logging.INFO:
            # running interactively
            self._interactive = True

        self._connection_lock = asyncio.Lock()
        self._listeners = []
        self._listener_commands = []

    def busy(self):
        """
        True if the connection is already in use.
        """
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
        """
        Get the config for the given key.
        """
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
            logger.info("Connecting to %s", self.connection)
            if await self.connection.open():
                logger.debug("Connected to %s", self.connection)

        return self.connected()

    async def connect(self, loop=None, interval: float = None) -> bool:
        """
        Connect to the BenQ projector.
        """
        assert interval is None or interval > 0

        self._loop = loop
        if self._loop is None:
            self._loop = asyncio.get_event_loop()

        try:
            if not await self._connect():
                return False
        except BenQConnectionError:
            logger.error("Problem communicating with %s", self.unique_id)
            return False

        if not self._init:
            return True

        if not self.model:
            self.projector_config = await self._loop.run_in_executor(
                None, self._read_config, "minimal"
            )

        if self.has_prompt is None:
            self.has_prompt = await self._detect_prompt()

        if self.has_prompt is False:
            self._separator = b"#"

        power = None
        try:
            power = await self._send_command(BenQCommand("pow"))
            if power is None:
                logger.error("Failed to retrieve projector power state.")
        except BenQPromptTimeoutError:
            logger.error(
                "Failed to get projector command prompt, is your projector properly connected?"
            )
            return False
        except BenQBlockedItemError as ex:
            logger.error(
                "Unable to retrieve projector power state, is projector powering down? %s",
                ex,
            )
        except BenQEmptyResponseError as ex:
            logger.warning(ex)
        except BenQProjectorError as ex:
            logger.error("Unable to retrieve projector power state: %s", ex)
            return False

        model = None
        try:
            model = await self._send_command(
                BenQCommand("modelname"), lowercase_response=False
            )
            assert model is not None, "Failed to retrieve projector model"
        except BenQIllegalFormatError as ex:
            # W1000 does not seem to return projector model, but gives an illegal
            # format error. Maybe there are other models with the same problem?
            logger.error("Unable to retrieve projector model")
        except BenQBlockedItemError as ex:
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

        if (
            model is not None
            and model != self.model
            and (power == "on" or self.model is None)
        ):
            self.model = model
            self.projector_config = None

        self._supported_commands = await self.get_config("commands")
        self.video_sources = await self.get_config("video_sources")
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
        self._interval = interval

        if (
            self._read_task is None
            and len(self._listeners) > 0
            and self._interval is not None
        ):
            self._read_task = asyncio.create_task(self._read_coroutine())
            _add_background_task(self._read_task)

        return True

    def connected(self) -> bool:
        """
        True if there is a connection with the projector.
        """
        return self.connection and self.connection.is_open()

    async def _disconnect(self):
        await self.connection.close()

    async def disconnect(self) -> bool:
        """
        Disconnect from the BenQ projector.
        """
        if self.connected():
            await self._cancel_read()
            await self._disconnect()

        return not self.connected()

    def add_listener(self, listener=None, command: str = None):
        """
        Adds a Callback to the BenQ projector.
        """
        if command is not None and command not in self._listener_commands:
            self._listener_commands.append(command)

        if listener is not None:
            self._listeners.append(listener)

            if self._read_task is None and self._interval is not None:
                self._read_task = asyncio.create_task(self._read_coroutine())
                _add_background_task(self._read_task)

    def _forward_to_listeners(self, command: str, data: Any | None):
        for listener in self._listeners:
            try:
                listener(command, data)
            # pylint: disable=broad-exception-caught
            except Exception:
                logger.exception("Exception in listener: %s", listener)

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

                if not self.connected():
                    logger.debug("Not connected")
                elif not self.busy():
                    if await self.update_power():
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
                                if (
                                    command in self._listener_commands
                                    and command not in previous_data
                                ):
                                    data = await self.send_command(command)
                                    if (
                                        data is not None
                                        and previous_data.get(command) != data
                                    ):
                                        self._forward_to_listeners(command, data)
                                        previous_data[command] = data
                    elif (
                        self.power_status == self.POWERSTATUS_UNKNOWN
                        and previous_data.get("pow") != self.power_status
                    ):
                        self._forward_to_listeners("pow", self.power_status)
                        previous_data["pow"] = self.power_status

                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                logger.debug("Read coroutine was canceled")
                break
            except (BrokenPipeError, ConnectionResetError, BenQConnectionError):
                logger.error("Error communicating with BenQ projector")
                await self._disconnect()

        self._read_task = None
        logger.debug("Read coroutine stopped")

    def supports_command(self, command) -> bool:
        """
        Test if a command is supported by the projector.

        If the list of supported commands is not (yet) set it is assumed the command is supported.
        """
        return self._supported_commands is None or command in self._supported_commands

    async def _send_command(
        self,
        command: BenQCommand,
        check_supported: bool = True,
        lowercase_response: bool = True,
    ) -> str:
        """
        Send a command to the BenQ projector.
        """

        if check_supported and not self.supports_command(command.command):
            logger.warning("Command %s not supported", command.command)
            return None

        if not await self._connect():
            logger.error("Connection not available")
            return None

        try:
            locked = await asyncio.wait_for(
                self._connection_lock.acquire(), timeout=_CONNECTION_LOCK_TIMEOUT
            )
            if not locked:
                raise BenQTooBusyError(command)
        except asyncio.exceptions.TimeoutError as ex:
            raise BenQTooBusyError(command) from ex

        try:
            await self._send_raw_command(command.raw_command)

            raw_response = await self._read_raw_response(command)

            return self._parse_response(command, raw_response, lowercase_response)
        except BenQProjectorError as ex:
            ex.command = command
            raise
        except BenQConnectionError:
            logger.exception("Problem communicating with %s", self.unique_id)
            return None
        finally:
            self._connection_lock.release()

    async def _detect_prompt(self) -> bool:
        """
        Apparently native networked BenQ projectors don't use a prompt, while serial and thus
        serial to network bridges do use a prompt.

        This function detects if the connection uses a prompt.
        """
        logger.debug("Detecting prompt")
        await self.connection.write(b"\r")
        response = await self.connection.read(10)
        response = response.strip(WHITESPACE.encode())
        if response == b">":
            logger.debug("Prompt detected")
            return True

        logger.debug("No prompt detected")
        return False

    async def _wait_for_prompt(self) -> bool:
        # Clean input buffer
        await self.connection.reset()

        if not self._has_to_wait_for_prompt:
            await self.connection.write(b"\r")
            if await self.connection.read(1) == b"\r":
                return True
            self._has_to_wait_for_prompt = True
            return False

        start_time = datetime.now()
        while True:
            response = await self.connection.read(100)
            response = response.strip(b"\x00")
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
                raise BenQPromptTimeoutError()

            await asyncio.sleep(0.05)

        return False

    async def _read_response(self) -> str:
        response = b""
        last_response = datetime.now()
        while True:
            _response = await self.connection.readuntil(self._separator)
            if len(_response) > 0:
                response += _response
                if any(c in _response for c in END_OF_RESPONSE):
                    response = response.decode(errors="ignore")
                    # Cleanup response
                    response = response.strip(WHITESPACE)
                    logger.debug("Response: %s", response)

                    return response
                last_response = datetime.now()

            if (datetime.now() - last_response).total_seconds() > _RESPONSE_TIMEOUT:
                logger.warning("Timeout while waiting for response")
                self._has_to_wait_for_prompt = True
                raise BenQResponseTimeoutError()

            logger.debug("Waiting for response")
            await asyncio.sleep(0.05)

    async def _read_raw_response(self, command: BenQCommand) -> str:
        response = None
        empty_line_count = 0
        echo_received = None
        previous_response = None
        while True:
            if empty_line_count > 5:
                if self._init:
                    logger.error("More than 5 empty responses, is your cable right?")
                if echo_received and previous_response:
                    # It's possible that the previous response is
                    # misinterpreted as being the command echo while it
                    # actually was the command response.
                    # In that case we continue the response processing
                    # using the previous response.
                    response = previous_response
                else:
                    raise BenQEmptyResponseError(command)
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

            if (
                command.action == "?"
                and not echo_received
                and response == command.raw_command
            ):
                # Command echo.
                logger.debug("Command successfully sent")
                echo_received = True
                self._expect_command_echo = True
                continue

            if not echo_received and response == f">{command.raw_command}":
                # Command echo.
                logger.debug("Command successfully sent")
                echo_received = True
                self._expect_command_echo = True
                continue

            if self._expect_command_echo and not echo_received:
                if command.action != "?" and response == command.raw_command:
                    # Command echo.
                    logger.debug("Command successfully sent")
                    echo_received = True
                    previous_response = response
                    continue
                logger.warning("No command echo received")
                self._expect_command_echo = False

            return response

    async def _send_raw_command(self, command: str):
        """
        Send a raw command to the BenQ projector.
        """
        if self.has_prompt:
            await self._wait_for_prompt()

        logger.debug("command %s", command)
        await self.connection.write(f"{command}\r".encode("ascii"))

    def _parse_response(self, command: BenQCommand, response, lowercase: bool = True):
        # Lowercase the response
        lowercase_response = response.lower()

        if lowercase_response in ["*illegal format#", "illegal format"]:
            if not self._interactive:
                logger.error("Command %s illegal format", command.raw_command)
            raise BenQIllegalFormatError(command)

        if lowercase_response in ["*unsupported item#", "unsupported item"]:
            if not self._interactive:
                logger.warning("Command %s unsupported item", command.raw_command)
            raise BenQUnsupportedItemError(command)

        if lowercase_response in ["*block item#", "block item"]:
            if not self._interactive:
                logger.warning("Command %s blocked item", command.raw_command)
            raise BenQBlockedItemError(command)

        if command.action is None:
            matches = RESPONSE_RE_STATE_ONLY.match(response)
        else:
            matches = RESPONSE_RE_STRICT.match(response)
            if not matches:
                logger.warning(
                    "Response does not match strict response validation: %s", response
                )
                # Continue using loose response validation
                matches = RESPONSE_RE_LOOSE.match(response)

            if matches and matches.group(1).lower() != command.command:
                raise BenQInvallidResponseError(command, response)
            if not matches and command.command == "modelname":
                # Some projectors only return the model name withouth the modelname command
                # #w700 instad of #modelname=w700*
                matches = RESPONSE_RE_STATE_ONLY.match(response)

        if not matches:
            logger.error("Unexpected response format, response: %s", response)
            raise BenQInvallidResponseError(command, response)
        response: str = matches.group(2)

        # Strip any spaces from the response
        response = response.strip(WHITESPACE)

        if lowercase:
            response = response.lower()

        logger.debug("Processed response: %s", response)

        return response

    async def send_command(
        self, command: str, action: str = "?", check_supported: bool = True
    ) -> str:
        """
        Send a command to the BenQ projector.
        """
        response = None

        try:
            response = await self._send_command(
                BenQCommand(command, action), check_supported
            )
        except BenQConnectionError:
            await self.connection.close()
        except BenQResponseTimeoutError:
            await self.connection.close()
        except BenQProjectorError:
            pass

        return response

    async def send_raw_command(self, raw_command: str) -> str:
        """
        Send a raw command to the BenQ projector.
        """
        command = BenQRawCommand(raw_command)

        try:
            locked = await asyncio.wait_for(
                self._connection_lock.acquire(), timeout=_CONNECTION_LOCK_TIMEOUT
            )
            if not locked:
                raise BenQTooBusyError(command)
        except asyncio.exceptions.TimeoutError as ex:
            raise BenQTooBusyError(command) from ex

        raw_response = None

        try:
            await self._send_raw_command(command.raw_command)

            # Read and log the response
            raw_response = await self._read_raw_response(command)
            logger.debug(raw_response)
        except BenQResponseTimeoutError:
            await self.connection.close()
            ex.command = command
        except BenQProjectorError as ex:
            ex.command = command
            raise
        except BenQConnectionError:
            logger.exception("Problem communicating with %s", self.unique_id)
            return None
        finally:
            self._connection_lock.release()

        return raw_response

    async def update_power(self) -> bool:
        """
        Update the current power state.
        """
        response = await self.send_command("pow")
        if response is None:
            if self.power_status == self.POWERSTATUS_POWERINGON:
                logger.debug("Projector still powering on")
                return True
            if self.power_status == self.POWERSTATUS_POWERINGOFF:
                logger.debug("Projector still powering off")
                return True

            self.power_status = self.POWERSTATUS_UNKNOWN
            return False

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
        return False

    async def update_volume(self) -> bool:
        """
        Update the current volume state.
        """
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
        """
        Update the current video source state.
        """
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

    async def turn_on(self) -> bool:
        """
        Turn the projector on.

        First it tests if the projector is in a state that powering on is possible.
        """
        # Check the actual power state of the projector.
        response = None
        try:
            response = await self._send_command(BenQCommand("pow"))
            if response is None:
                logger.error("Failed to retrieve projector power state.")
        except BenQBlockedItemError as ex:
            logger.error(
                "Unable to retrieve projector power state, is projector already powering down? %s",
                ex,
            )
        except BenQProjectorError as ex:
            logger.error("Unable to retrieve projector power state: %s", ex)
            return False

        if response == "on":
            # The projector is already on.
            if (
                self.power_status == self.POWERSTATUS_POWERINGON
                and (time.time() - self._power_timestamp) <= self._poweron_time
            ):
                logger.debug("Projector still powering on")
            else:
                logger.debug("Projector already on")
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
            try:
                response = await self._send_command(BenQCommand("pow", "on"))
                if response == "on":
                    self.power_status = self.POWERSTATUS_POWERINGON
                    self._power_timestamp = time.time()

                    return True
            except BenQBlockedItemError as ex:
                logger.error(
                    "Failed to turn on projector, is projector already powering on or off? %s",
                    ex,
                )
            except BenQProjectorError as ex:
                pass

            logger.error("Failed to turn on projector, response: %s", response)

        return False

    async def turn_off(self) -> bool:
        """
        Turn the projector off.

        First it tests if the projector is in a state that powering off is possible.
        """
        # Check the actual power state of the projector.
        response = None
        try:
            response = await self._send_command(BenQCommand("pow"))
            if response is None:
                logger.error("Failed to retrieve projector power state.")
        except BenQBlockedItemError as ex:
            logger.error(
                "Unable to retrieve projector power state, is projector already powering down? %s",
                ex,
            )
        except BenQProjectorError as ex:
            logger.error("Unable to retrieve projector power state: %s", ex)
            return False

        if response == "off":
            # The projector is already off.
            if (
                self.power_status == self.POWERSTATUS_POWERINGOFF
                and (time.time() - self._power_timestamp) <= self._poweroff_time
            ):
                logger.debug("Projector still powering off")
            else:
                logger.debug("Projector already off")
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
            try:
                response = await self._send_command(BenQCommand("pow", "off"))
                if response == "off":
                    self.power_status = self.POWERSTATUS_POWERINGOFF
                    self._power_timestamp = time.time()

                    return True
            except BenQBlockedItemError as ex:
                logger.error(
                    "Failed to turn off projector, is projector already powering on or off? %s",
                    ex,
                )
            except BenQProjectorError as ex:
                pass

            logger.error("Failed to turn off projector, response: %s", response)

        return False

    async def mute(self):
        """
        Mutes the volume.
        """
        response = await self.send_command("mute", "on")
        if response == "on":
            self.muted = True
            return True

        return False

    async def unmute(self):
        """
        Unmutes the volume.
        """
        response = await self.send_command("mute", "off")
        if response == "off":
            self.muted = False
            return True

        return False

    async def volume_up(self) -> None:
        """
        Increase volume.
        """
        if self.volume is None:
            self.update_volume()
        elif self.volume >= 20:  # Can't go higher than 20
            return False

        if await self.send_command("vol", "+") == "+":
            self.volume += 1
            return True

        return False

    async def volume_down(self) -> None:
        """
        Decrease volume.
        """
        if self.volume is None:
            self.update_volume()
        elif self.volume <= 0:  # Can't go lower than 0
            return False

        if await self.send_command("vol", "-") == "-":
            self.volume -= 1
            return True

        return False

    async def volume_level(self, level) -> None:
        """
        Set volume to a given level.
        """
        if self.volume == level:
            return True

        if not self._use_volume_increments:
            # Try to set the volume without increments, some projectors seem to support this
            try:
                if await self._send_command(BenQCommand("vol", level)) == str(level):
                    logger.debug("Successfully set volume withouth increments")
                    return True
            except BenQUnsupportedItemError:
                logger.debug("Need increments to set volume")
                self._use_volume_increments = True

        while self.volume < level:
            if not await self.volume_up():
                return False

        while self.volume > level:
            if not await self.volume_down():
                return False

        return True

    async def select_video_source(self, video_source: str):
        """
        Select projector video source.
        """
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

    has_prompt = True

    def __init__(
        self,
        serial_port: str,
        baud_rate: int,
        model_hint: str = None,
    ) -> None:
        """
        Initializes the BenQProjectorSerial object.
        """
        assert serial_port is not None
        assert baud_rate in BAUD_RATES, "Not a valid baud rate"

        self.unique_id = serial_port

        connection = BenQSerialConnection(serial_port, baud_rate)

        super().__init__(connection, model_hint)


class BenQProjectorTelnet(BenQProjector):
    """
    BenQ Projector class for controlling BenQ projectors over a Telnet connection.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        model_hint: str = None,
        has_prompt: bool | None = None,
    ) -> None:
        """
        Initializes the BenQProjectorTelnet object.
        """
        assert host is not None
        assert port is not None

        self.unique_id = f"{host}:{port}"

        connection = BenQTelnetConnection(host, port)
        self.has_prompt = has_prompt

        super().__init__(connection, model_hint)
