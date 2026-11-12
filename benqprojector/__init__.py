"""Implements the BenQ projector library for controlling BenQ projector over the serial interface.

Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import contextlib

with contextlib.suppress(ModuleNotFoundError):
    from ._version import __version__ as __version__

from abc import ABC
import asyncio
from collections.abc import Callable
from datetime import datetime
import importlib.resources
import json
from json.decoder import JSONDecodeError
import logging
import re
import string
import sys
import time
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
    DEFAULT_PORT as DEFAULT_PORT,
    BenQConnection,
    BenQConnectionError,
    BenQSerialConnection,
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

CMD_MODELNAME = "modelname"
CMD_POWER = "pow"
CMD_MUTE = "mute"
CMD_VOLUME = "vol"
CMD_SOURCE = "sour"

ACTION_ON = "on"
ACTION_OFF = "off"


class BenQProjector(ABC):
    """BenQProjector base class for controlling BenQ projectors."""

    connection: BenQConnection
    # Projectors with integrated network don't seem to have a command prompt, the code tries to
    # detect if this is the case
    has_prompt: bool | None = None
    _separator = b"\n"

    _init: bool = True
    _has_to_wait_for_prompt = True
    _use_volume_increments = False

    _read_task: asyncio.Task[None] | None = None
    _listeners: list[Callable[[str, Any], Any]]
    _listener_commands: list[str]
    _interval: float | None = None

    model: str | None = None
    _mac: str | None = None
    unique_id: str | None = None

    # Supported commands and modes
    projector_config_all: dict[str, Any]
    projector_config: dict[str, Any] | None = None
    _supported_commands: list[str] | None = None
    video_sources: list[str] | None = None
    audio_sources: list[str] | None = None
    picture_modes: list[str] | None = None
    color_temperatures: list[str] | None = None
    aspect_ratios: list[str] | None = None
    projector_positions: list[str] | None = None
    lamp_modes: list[str] | None = None
    threed_modes: list[str] | None = None  # 3D modes
    menu_positions: list[str] | None = None

    # Current modes
    video_source: str | None = None
    audio_source: str | None = None
    picture_mode: str | None = None
    color_temperature: str | None = None
    aspect_ratio: str | None = None
    projector_position: str | None = None
    lamp_mode: str | None = None
    threed_mode: str | None = None  # 3D mode

    POWERSTATUS_UNKNOWN = -1
    POWERSTATUS_OFF = 0
    POWERSTATUS_POWERINGON = 1
    POWERSTATUS_ON = 2
    POWERSTATUS_POWERINGOFF = 3

    power_status = POWERSTATUS_UNKNOWN
    _poweron_time: float | None = None
    _poweroff_time: float | None = None
    _power_timestamp: float | None = None
    direct_power_on: bool | None = None

    lamp_time: int | None = None
    lamp2_time: int | None = None

    volume: int | None = None
    muted: bool | None = None

    brilliant_color: bool | None = None
    blank: bool | None = None
    brightness: int | None = None
    color_value: int | None = None
    contrast: int | None = None
    high_altitude: bool | None = None
    quick_auto_search: bool | None = None
    sharpness: str | None = None

    # Some projectors do not echo the given command, the code tries to detect if this is the case
    _expect_command_echo = True

    def __init__(
        self,
        connection: BenQConnection,
        model_hint: str | None = None,
    ):
        """Initialises the BenQProjector object."""
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
        self.projector_config_all = {}

    def busy(self) -> bool:
        """True if the connection is already in use."""
        return self._connection_lock.locked()

    async def _read_config(self, model: str) -> dict[str, Any] | None:
        model_filename = (
            "".join(c if c.isalnum() or c in "._-" else "_" for c in model.lower())
            + ".json"
        )
        logger.info("Using model file %s", model_filename)

        text = await asyncio.get_running_loop().run_in_executor(
            None, importlib.resources.read_text, "benqprojector.configs", model_filename
        )

        try:
            if text is not None and len(text) > 0:
                config: dict[str, Any] = json.loads(text)
                return config

            logger.debug("No or empty read config file %s", model_filename)
        except JSONDecodeError:
            logger.exception("Invalid config file %s", model_filename)

        return None

    async def get_config(self, key: str) -> Any:
        """Get the config for the given key."""
        if not self.projector_config_all:
            self.projector_config_all = await self._read_config("all") or {}

        if not self.projector_config and self.model:
            with contextlib.suppress(FileNotFoundError):
                self.projector_config = await self._read_config(self.model)

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

    async def connect(self, interval: float | None = None) -> bool:
        """Connect to the BenQ projector."""
        assert interval is None or interval > 0

        try:
            if not await self._connect():
                return False
        except BenQConnectionError:
            logger.exception("Problem communicating with %s", self.unique_id)
            return False

        if not self._init:
            return True

        if not self.model:
            await self._read_config("minimal")

        if self.has_prompt is None:
            self.has_prompt = await self._detect_prompt()

        if self.has_prompt is False:
            self._separator = b"#"

        power = None
        try:
            power = await self._send_command(BenQCommand(CMD_POWER))
            if power is None:
                logger.error("Failed to retrieve projector power state.")
        except BenQPromptTimeoutError:
            logger.exception(
                "Failed to get projector command prompt, is your projector properly connected?"
            )
            return False
        except BenQBlockedItemError:
            logger.exception(
                "Unable to retrieve projector power state, is projector powering down?"
            )
        except BenQEmptyResponseError as ex:
            logger.warning(ex)
        except BenQProjectorError:
            logger.exception("Unable to retrieve projector power state.")
            return False

        model = None
        try:
            model = await self._send_command(
                BenQCommand(CMD_MODELNAME), lowercase_response=False
            )
            if model is None:
                logger.error("Failed to retrieve projector model")
        except BenQIllegalFormatError:
            # W1000 does not seem to return projector model, but gives an illegal
            # format error. Maybe there are other models with the same problem?
            logger.exception("Unable to retrieve projector model")
        except BenQBlockedItemError:
            # W1070/W1250 does not seem to return projector model when off, but gives
            # an blocked item error. Maybe there are other models with the same problem?
            if power == "off":
                logger.exception(
                    "Unable to retrieve projector model while projector is %s",
                    power,
                )
            else:
                # It could also be that the projector is powering down
                logger.exception(
                    "Unable to retrieve projector model while projector is %s, is projector powering down?",
                    power,
                )
        except BenQProjectorError:
            # Not knowing the model is not fatal, continue with the generic config
            logger.exception("Unable to retrieve projector model")

        if (
            model is not None
            and model != self.model
            and (power == "on" or self.model is None)
        ):
            if self.model is not None:
                logger.warning(
                    "Projector model unexpectedly changed from %s to %s",
                    self.model,
                    model,
                )
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

        self._start_read_task()

        return True

    def connected(self) -> bool:
        """True if there is a connection with the projector."""
        return self.connection.is_open()

    async def _disconnect(self) -> None:
        await self.connection.close()

    async def disconnect(self) -> bool:
        """Disconnect from the BenQ projector."""
        # Always stop polling, also when the connection is already lost. Otherwise the
        # read coroutine would reconnect after the disconnect was requested.
        await self._cancel_read()

        if self.connected():
            await self._disconnect()

        return not self.connected()

    def add_listener(
        self,
        listener: Callable[[str, Any], Any] | None = None,
        command: str | None = None,
    ) -> None:
        """Adds a Callback to the BenQ projector."""
        if command is not None and command not in self._listener_commands:
            self._listener_commands.append(command)

        if listener is not None:
            self._listeners.append(listener)
            self._start_read_task()

    def _forward_to_listeners(self, command: str, data: Any | None) -> None:
        for listener in self._listeners:
            try:
                listener(command, data)
            except Exception:
                logger.exception("Exception in listener: %s", listener)

    def _start_read_task(self) -> None:
        """Start the read coroutine if there are listeners and it's not running."""
        if self._interval is None or not self._listeners:
            return

        # A finished task is replaced, so polling can be restarted after it stopped
        if self._read_task is not None and not self._read_task.done():
            return

        self._read_task = asyncio.create_task(self._read_coroutine())

    async def _cancel_read(self) -> None:
        """Stop the read coroutine and wait for it to finish."""
        task = self._read_task
        self._read_task = None

        if task is None or task.done():
            return

        task.cancel()
        # Can't wait for ourself when called from within the read coroutine
        if task is not asyncio.current_task():
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _forward_if_changed(
        self, previous_data: dict[str, Any], command: str, value: Any
    ) -> None:
        """Forward the value to the listeners if it changed since the last poll."""
        if previous_data.get(command) != value:
            self._forward_to_listeners(command, value)
            previous_data[command] = value

    async def _poll_states(self, previous_data: dict[str, Any]) -> None:
        """Poll the projector states and forward the changed states to the listeners."""
        if not await self.update_power():
            if self.power_status == self.POWERSTATUS_UNKNOWN:
                self._forward_if_changed(previous_data, CMD_POWER, self.power_status)
            return

        self._forward_if_changed(previous_data, CMD_POWER, self.power_status)

        if self.power_status == self.POWERSTATUS_ON:
            await self.update_volume()
            self._forward_if_changed(previous_data, CMD_MUTE, self.muted)
            self._forward_if_changed(previous_data, CMD_VOLUME, self.volume)

            await self.update_video_source()
            self._forward_if_changed(previous_data, CMD_SOURCE, self.video_source)

            commands = [
                command
                for command in self._listener_commands
                if command not in (CMD_POWER, CMD_MUTE, CMD_VOLUME, CMD_SOURCE)
            ]
        else:
            # Commands which only need to be read once while the projector is not on
            commands = [
                command
                for command in ("pp", "ltim", "ltim2")
                if command in self._listener_commands and command not in previous_data
            ]

        for command in commands:
            data = await self.send_command(command)
            if data is not None:
                self._forward_if_changed(previous_data, command, data)

    async def _read_coroutine(self) -> None:
        """Reads the current status of the projector in a loop."""
        assert self._interval is not None
        previous_data: dict[str, Any] = {}

        try:
            while True:
                try:
                    if not self.connected():
                        await self._connect()

                    if not self.connected():
                        logger.debug("Not connected")
                    elif not self.busy():
                        await self._poll_states(previous_data)
                except BrokenPipeError, ConnectionResetError, BenQConnectionError:
                    logger.exception("Error communicating with BenQ projector")
                    await self._disconnect()
                except Exception:
                    # Keep polling, an unexpected error should not silently stop the
                    # updates to the listeners
                    logger.exception("Unexpected error while reading projector state")

                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            logger.debug("Read coroutine was canceled")
        finally:
            if self._read_task is asyncio.current_task():
                self._read_task = None
            logger.debug("Read coroutine stopped")

    @property
    def supported_commands(self) -> list[str] | None:
        """The commands supported by the projector, None if not (yet) known."""
        return self._supported_commands

    def supports_command(self, command: str | None) -> bool:
        """Test if a command is supported by the projector.

        If the list of supported commands is not (yet) set it is assumed the command is supported.
        """
        return self._supported_commands is None or command in self._supported_commands

    async def _send_command(
        self,
        command: BenQCommand,
        check_supported: bool = True,
        lowercase_response: bool = True,
    ) -> str | None:
        """Send a command to the BenQ projector."""

        if check_supported and not self.supports_command(command.command):
            logger.warning("Command %s not supported", command.command)
            return None

        if not await self._connect():
            logger.error("Connection not available")
            return None

        try:
            await asyncio.wait_for(
                self._connection_lock.acquire(), timeout=_CONNECTION_LOCK_TIMEOUT
            )
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
        """Detects the presence of a prompt.

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
            if await self.connection.read(1) == b">":
                logger.debug("Prompt received")
                return True
            logger.warning("Prompt not received, wait for it")
            self._has_to_wait_for_prompt = True

        start_time = datetime.now()
        while True:
            response = await self.connection.read(100)
            response = response.strip(b"\x00")
            if response == b"":
                await self.connection.write(b"\r")
            elif response[-1:] == b">":
                logger.debug("Prompt detected")
                self._has_to_wait_for_prompt = False
                return True
            elif (
                response.strip(WHITESPACE.encode()) == b""
                or response.strip(WHITESPACE.encode()) == b">"
            ):
                pass
            else:
                logger.warning("Unexpected response: %s", response)

            if (datetime.now() - start_time).total_seconds() > 1:
                raise BenQPromptTimeoutError

            await asyncio.sleep(0.05)

        logger.warning("Prompt not detected")
        return False

    async def _read_response(self) -> str:
        response = b""
        last_response = datetime.now()
        while True:
            _response = await self.connection.readuntil(self._separator)
            if len(_response) > 0:
                response += _response
                if any(c in _response for c in END_OF_RESPONSE):
                    # Decode and cleanup response
                    text = response.decode(errors="ignore").strip(WHITESPACE)
                    logger.debug("Response: %s", text)

                    return text
                last_response = datetime.now()

            if (datetime.now() - last_response).total_seconds() > _RESPONSE_TIMEOUT:
                logger.warning("Timeout while waiting for response")
                self._has_to_wait_for_prompt = True
                raise BenQResponseTimeoutError

            logger.debug("Waiting for response")
            await asyncio.sleep(0.05)

    async def _read_raw_response(self, command: BenQRawCommand) -> str:
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
                logger.warning(
                    "No command echo received for command %s", command.command
                )
                self._expect_command_echo = False

            return response

    async def _send_raw_command(self, command: str) -> None:
        """Send a raw command to the BenQ projector."""
        if self.has_prompt:
            await self._wait_for_prompt()

        logger.debug("command %s", command)
        await self.connection.write(f"{command}\r".encode("ascii"))

    def _parse_response(
        self, command: BenQCommand, response: str, lowercase: bool = True
    ) -> str:
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
            if not matches and command.command == CMD_MODELNAME:
                # Some projectors only return the model name without the modelname command
                # W700 instead of *modelname=W700#
                matches = RESPONSE_RE_STATE_ONLY.match(response)

        if not matches:
            logger.error("Unexpected response format, response: %s", response)
            raise BenQInvallidResponseError(command, response)
        response = matches.group(2)

        # Strip any spaces from the response
        response = response.strip(WHITESPACE)

        if lowercase:
            response = response.lower()

        logger.debug("Processed response: %s", response)

        return response

    async def send_command(
        self, command: str, action: str = "?", check_supported: bool = True
    ) -> str | None:
        """Send a command to the BenQ projector."""
        response = None

        try:
            response = await self._send_command(
                BenQCommand(command, action), check_supported
            )
        except BenQConnectionError:
            await self.connection.close()
        except BenQProjectorError:
            pass

        return response

    async def send_raw_command(self, raw_command: str) -> str | None:
        """Send a raw command to the BenQ projector."""
        command = BenQRawCommand(raw_command)

        if not await self._connect():
            logger.error("Connection not available")
            return None

        try:
            await asyncio.wait_for(
                self._connection_lock.acquire(), timeout=_CONNECTION_LOCK_TIMEOUT
            )
        except asyncio.exceptions.TimeoutError as ex:
            raise BenQTooBusyError(command) from ex

        raw_response = None

        try:
            await self._send_raw_command(command.raw_command)

            # Read and log the response
            raw_response = await self._read_raw_response(command)
            logger.debug(raw_response)
        except BenQProjectorError as ex:
            ex.command = command
            raise
        except BenQConnectionError:
            logger.exception("Problem communicating with %s", self.unique_id)
            return None
        finally:
            self._connection_lock.release()

        return raw_response

    def _is_transitioning(self, status: int, duration: float | None) -> bool:
        """True if still powering on/off within the given duration."""
        return (
            self.power_status == status
            and self._power_timestamp is not None
            and duration is not None
            and (time.time() - self._power_timestamp) <= duration
        )

    async def update_power(self) -> bool:
        """Update the current power state."""
        response = await self.send_command(CMD_POWER)
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
            if self._is_transitioning(
                self.POWERSTATUS_POWERINGOFF, self._poweroff_time
            ):
                logger.debug("Projector still powering off")
            else:
                self.power_status = self.POWERSTATUS_OFF
                self._power_timestamp = None

            return True

        if response == "on":
            if self._is_transitioning(self.POWERSTATUS_POWERINGON, self._poweron_time):
                logger.debug("Projector still powering on")
            else:
                self.power_status = self.POWERSTATUS_ON
                self._power_timestamp = None

            return True

        logger.error("Unknown power status: %s", response)
        return False

    async def update_volume(self) -> None:
        """Update the current volume state."""
        if self.supports_command(CMD_MUTE):
            self.muted = await self.send_command(CMD_MUTE) == "on"
            logger.debug("Muted: %s", self.muted)

        if self.supports_command(CMD_VOLUME):
            response = await self.send_command(CMD_VOLUME)
            volume: int | None = None
            if response is not None:
                try:
                    volume = int(response)
                except ValueError:
                    volume = None
            logger.debug("Volume: %s", volume)

            self.volume = volume

    async def update_video_source(self) -> None:
        """Update the current video source state."""
        if self.supports_command(CMD_SOURCE):
            self.video_source = await self.send_command(CMD_SOURCE)
            logger.debug("Video source: %s", self.video_source)

    def _clear_powered_on_states(self) -> None:
        """Clear the states which are only known when the projector is on."""
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

    async def _update_powered_on_states(self) -> None:
        """Update the states which can only be retrieved when the projector is on."""
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
                try:
                    self.brightness = int(response)
                except ValueError:
                    logger.warning("Invalid brightness: %s", response)
                    self.brightness = None
                logger.debug("Brightness: %s", self.brightness)

        if self.supports_command("color"):
            response = await self.send_command("color")
            if response is not None:
                try:
                    self.color_value = int(response)
                except ValueError:
                    logger.warning("Invalid color value: %s", response)
                    self.color_value = None
                logger.debug("Color value: %s", self.color_value)

        if self.supports_command("con"):
            response = await self.send_command("con")
            if response is not None:
                try:
                    self.contrast = int(response)
                except ValueError:
                    logger.warning("Invalid contrast: %s", response)
                    self.contrast = None
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

    async def update(self) -> bool:
        """Update all known states.

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
                try:
                    self.lamp_time = int(response)
                except ValueError:
                    logger.warning("Invalid lamp time: %s", response)
                    self.lamp_time = None

        if self.supports_command("ltim2"):
            response = await self.send_command("ltim2")
            if response is not None:
                try:
                    self.lamp2_time = int(response)
                except ValueError:
                    logger.warning("Invalid lamp 2 time: %s", response)
                    self.lamp2_time = None

        if self.power_status in [
            self.POWERSTATUS_OFF,
            self.POWERSTATUS_ON,
        ] and self.supports_command("pp"):
            # Commands which only work when powered on or off, not when
            # powering on or off
            self.projector_position = await self.send_command("pp")

        if self.power_status in [self.POWERSTATUS_POWERINGOFF, self.POWERSTATUS_OFF]:
            self._clear_powered_on_states()
        elif self.power_status in [self.POWERSTATUS_POWERINGON, self.POWERSTATUS_ON]:
            await self._update_powered_on_states()

        return True

    async def turn_on(self) -> bool:
        """Turn the projector on.

        First it tests if the projector is in a state that powering on is possible.
        """
        # Check the actual power state of the projector.
        response = None
        try:
            response = await self._send_command(BenQCommand(CMD_POWER))
            if response is None:
                logger.error("Failed to retrieve projector power state.")
        except BenQBlockedItemError:
            logger.exception(
                "Unable to retrieve projector power state, is projector already powering down?",
            )
        except BenQProjectorError:
            logger.exception("Unable to retrieve projector power state.")
            return False

        if response == "on":
            # The projector is already on.
            if self._is_transitioning(self.POWERSTATUS_POWERINGON, self._poweron_time):
                logger.debug("Projector still powering on")
            else:
                logger.debug("Projector already on")
                self.power_status = self.POWERSTATUS_ON
                self._power_timestamp = None

            return True

        if response == "off":
            # The projector is off, calculate if the power off time has already passed
            if self._is_transitioning(
                self.POWERSTATUS_POWERINGOFF, self._poweroff_time
            ):
                logger.warning("Projector still powering off")
                return False
            self.power_status = self.POWERSTATUS_OFF
            self._power_timestamp = None

            # Continue powering on the projector.
            logger.info("Turning on projector")
            try:
                response = await self._send_command(BenQCommand(CMD_POWER, ACTION_ON))
                if response == "on":
                    self.power_status = self.POWERSTATUS_POWERINGON
                    self._power_timestamp = time.time()

                    return True
            except BenQBlockedItemError:
                logger.exception(
                    "Failed to turn on projector, is projector already powering on or off?"
                )
            except BenQProjectorError:
                pass

            logger.error("Failed to turn on projector, response: %s", response)

        return False

    async def turn_off(self) -> bool:
        """Turn the projector off.

        First it tests if the projector is in a state that powering off is possible.
        """
        # Check the actual power state of the projector.
        response = None
        try:
            response = await self._send_command(BenQCommand(CMD_POWER))
            if response is None:
                logger.error("Failed to retrieve projector power state.")
        except BenQBlockedItemError:
            logger.exception(
                "Unable to retrieve projector power state, is projector already powering down?"
            )
        except BenQProjectorError:
            logger.exception("Unable to retrieve projector power state.")
            return False

        if response == "off":
            # The projector is already off.
            if self._is_transitioning(
                self.POWERSTATUS_POWERINGOFF, self._poweroff_time
            ):
                logger.debug("Projector still powering off")
            else:
                logger.debug("Projector already off")
                self.power_status = self.POWERSTATUS_OFF
                self._power_timestamp = None

            return True

        if response == "on":
            # The projector is on, calculate if the power on time has already passed
            if self._is_transitioning(self.POWERSTATUS_POWERINGON, self._poweron_time):
                logger.warning("Projector still powering on")
                return False
            self.power_status = self.POWERSTATUS_ON
            self._power_timestamp = None

            # Continue powering off the projector.
            logger.info("Turning off projector")
            try:
                response = await self._send_command(BenQCommand(CMD_POWER, ACTION_OFF))
                if response == "off":
                    self.power_status = self.POWERSTATUS_POWERINGOFF
                    self._power_timestamp = time.time()

                    return True
            except BenQBlockedItemError:
                logger.exception(
                    "Failed to turn off projector, is projector already powering on or off?"
                )
            except BenQProjectorError:
                pass

            logger.error("Failed to turn off projector, response: %s", response)

        return False

    async def mute(self) -> bool:
        """Mutes the volume."""
        response = await self.send_command(CMD_MUTE, ACTION_ON)
        if response == "on":
            self.muted = True
            return True

        return False

    async def unmute(self) -> bool:
        """Unmutes the volume."""
        response = await self.send_command(CMD_MUTE, ACTION_OFF)
        if response == "off":
            self.muted = False
            return True

        return False

    async def volume_up(self) -> bool:
        """Increase volume."""
        if self.volume is None:
            await self.update_volume()
        if self.volume is not None and self.volume >= 20:  # Can't go higher than 20
            return False

        if await self.send_command(CMD_VOLUME, "+") == "+":
            if self.volume is not None:
                self.volume += 1
            return True

        return False

    async def volume_down(self) -> bool:
        """Decrease volume."""
        if self.volume is None:
            await self.update_volume()
        if self.volume is None or self.volume <= 0:  # Can't go lower than 0
            return False

        if await self.send_command(CMD_VOLUME, "-") == "-":
            self.volume -= 1
            return True

        return False

    async def volume_level(self, level: int) -> bool:
        """Set volume to a given level."""
        if not 0 <= level <= 20:  # Volume ranges from 0 to 20
            logger.error("Invalid volume level %s, must be between 0 and 20", level)
            return False

        if self.volume == level:
            return True

        if not self._use_volume_increments:
            # Try to set the volume without increments, some projectors seem to support this
            try:
                if await self._send_command(BenQCommand(CMD_VOLUME, str(level))) == str(
                    level
                ):
                    logger.debug("Successfully set volume without increments")
                    self.volume = level
                    return True
            except BenQUnsupportedItemError:
                logger.debug("Need increments to set volume")
                self._use_volume_increments = True
            except BenQConnectionError, BenQProjectorError:
                logger.exception("Unable to set volume")
                return False

        if self.volume is None:
            await self.update_volume()
        if self.volume is None:
            logger.error("Unable to set volume, current volume is unknown")
            return False

        while self.volume < level:
            if not await self.volume_up():
                return False

        while self.volume > level:
            if not await self.volume_down():
                return False

        return True

    async def select_video_source(self, video_source: str) -> bool:
        """Select projector video source."""
        video_source = video_source.lower()

        if self.video_sources is None or video_source not in self.video_sources:
            return False

        if await self.send_command(CMD_SOURCE, video_source) == video_source:
            self.video_source = video_source
            return True

        return False


class BenQProjectorSerial(BenQProjector):
    """BenQ Projector class for controlling BenQ projectors over a serial connection."""

    has_prompt: bool | None = True

    def __init__(
        self,
        serial_port: str,
        baud_rate: int,
        model_hint: str | None = None,
        record: bool = False,
    ) -> None:
        """Initializes the BenQProjectorSerial object."""
        assert serial_port is not None
        assert baud_rate in BAUD_RATES, "Not a valid baud rate"

        self.unique_id = serial_port

        connection = BenQSerialConnection(serial_port, baud_rate, record)

        super().__init__(connection, model_hint)


class BenQProjectorTelnet(BenQProjectorSerial):
    """BenQ Projector class for controlling BenQ projectors over a Telnet connection."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        model_hint: str | None = None,
        has_prompt: bool | None = None,
        record: bool = False,
    ) -> None:
        """Initializes the BenQProjectorTelnet object."""
        assert host is not None
        assert port is not None

        self.has_prompt = has_prompt

        super().__init__(f"socket://{host}:{port}", BAUD_RATES[0], model_hint, record)

        self.unique_id = f"{host}:{port}"
