"""
Implements the BenQProjector class for controlling BenQ projectors.

Created on 27 Nov 2022

@author: Rogier van Staveren
"""
import asyncio
import logging
import re
import time

import serial

from benqprojector.config import BAUD_RATES, PROJECTOR_CONFIGS

logger = logging.getLogger(__name__)

_SERIAL_TIMEOUT = 0.05


class BenQProjectorError(Exception):
    """Generic BenQ Projector error."""

    def __init__(self, command=None, action=None):
        self.command = command
        self.action = action


class IllegalFormatError(BenQProjectorError):
    """Illegal command format error."""


class EmptyResponseError(BenQProjectorError):
    """Empty response error."""


class UnsupportedItemError(BenQProjectorError):
    """Unsupported item error."""


class BlockedItemError(BenQProjectorError):
    """Blocked item error."""


class InvallidResponseError(BenQProjectorError):
    """Empty response error."""

    def __init__(self, command=None, action=None, response=None):
        super().__init__(command, action)
        self.response = response


class BenQProjector:
    """
    BenQProjector class for controlling BenQ projectors.
    """

    # The serial port where the RS-485 interface and screen is connected to.
    _serial_port = None
    _connection = None
    _busy = False

    model = None
    _mac = None
    unique_id = None

    # Supported commands and modes
    _supported_commands = None
    video_sources = None
    audio_sources = None
    picture_modes = None
    color_temperatures = None
    aspect_ratios = None
    projector_positions = None
    lamp_modes = None
    threed_modes = None  # 3D modes

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
    _response_re = re.compile(r"^\*?([^=]*)=(.*)#$")

    # Some projectors do not echo the given command, the code tries to detect if this is the case
    _expect_command_echo = True

    def __init__(
        self,
        serial_port: str,  # The serial port where the RS-485 interface and
        # screen is connected to.
        baud_rate: int,
    ):
        """
        Initialises the BenQProjector object.
        """
        assert serial_port is not None
        assert baud_rate in BAUD_RATES, "Not a valid baud rate"

        self._serial_port = serial_port
        self._baud_rate = baud_rate

    def _connect(self) -> bool:
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

        if not self._connection.is_open:
            return False

        return True

    def connect(self) -> bool:
        """
        Connect to the BenQ projector.
        """
        if not self._connect():
            return False

        model = self._send_command("modelname")
        assert model is not None, "Failed to retrieve projector model"
        # Is projector powering down?
        self.model = model

        self._supported_commands = PROJECTOR_CONFIGS.get(model, {}).get(
            "commands", PROJECTOR_CONFIGS.get("all").get("commands")
        )

        self.video_sources = PROJECTOR_CONFIGS.get(model, {}).get(
            "sources", PROJECTOR_CONFIGS.get("all").get("sources")
        )
        self.audio_sources = PROJECTOR_CONFIGS.get(model, {}).get(
            "audio_sources", PROJECTOR_CONFIGS.get("all").get("audio_sources")
        )
        self.picture_modes = PROJECTOR_CONFIGS.get(model, {}).get(
            "picture_modes", PROJECTOR_CONFIGS.get("all").get("picture_modes")
        )
        self.color_temperatures = PROJECTOR_CONFIGS.get(model, {}).get(
            "color_temperatures", PROJECTOR_CONFIGS.get("all").get("color_temperatures")
        )
        self.aspect_ratios = PROJECTOR_CONFIGS.get(model, {}).get(
            "aspect_ratios", PROJECTOR_CONFIGS.get("all").get("aspect_ratios")
        )
        self.projector_positions = PROJECTOR_CONFIGS.get(model, {}).get(
            "projector_positions",
            PROJECTOR_CONFIGS.get("all").get("projector_positions"),
        )
        self.lamp_modes = PROJECTOR_CONFIGS.get(model, {}).get(
            "lamp_modes", PROJECTOR_CONFIGS.get("all").get("lamp_modes")
        )
        self.threed_modes = PROJECTOR_CONFIGS.get(model, {}).get(
            "3d_modes", PROJECTOR_CONFIGS.get("all").get("3d_modes")
        )

        self._poweron_time = PROJECTOR_CONFIGS.get(model, {}).get(
            "poweron_time", PROJECTOR_CONFIGS.get("all").get("poweron_time")
        )
        self._poweroff_time = PROJECTOR_CONFIGS.get(model, {}).get(
            "poweroff_time", PROJECTOR_CONFIGS.get("all").get("poweroff_time")
        )

        mac = None
        if self.supports_command("macaddr"):
            mac = self.send_command("macaddr=?")

        if mac is not None:
            self._mac = mac.lower()
            self.unique_id = self._mac
        else:
            self.unique_id = self._serial_port

        logger.info("Device %s available", self._serial_port)

        self.update_power()

        return True

    def disconnect(self):
        """Disconnect from the BenQ projector."""
        if self._connection is not None:
            self._connection.close()

    def supports_command(self, command) -> bool:
        """
        Test if a command is supported by the projector.

        If the list of supported commands is not (yet) set it is assumed the command is supported.
        """
        return self._supported_commands is None or command in self._supported_commands

    def _sleep(self, seconds):
        try:
            asyncio.get_running_loop()
            # async def __sleep():
            #     await asyncio.sleep(seconds)
            # asyncio.run(__sleep())
            # asyncio.run(asyncio.sleep(seconds))
        except RuntimeError:
            # No running event loop, time.sleep() is safe to use.
            time.sleep(seconds)

    def _send_command(self, command: str, action: str = "?") -> str:
        """
        Send a command to the BenQ projector.
        """
        command = command.lower()

        if not self.supports_command(command):
            logger.error("Command %s not supported", command)
            return None

        if self._connect() is False:
            logger.error("Connection not available")
            return None

        while self._busy is True:
            logger.info("Too busy for %s=%s", command, action)
            self._sleep(0.1)
        self._busy = True

        response = None

        try:
            self._connection.reset_input_buffer()
            self._connection.reset_output_buffer()

            # Clean input buffer
            self._connection.write(b"\r")
            self._connection.flush()
            response = self._connection.read(1)
            if response != b">":
                logger.error("Unexpected response: %s", response)
                # Try to clean the input buffer by reading everything
                response = self._connection.read(1)
                logger.error("Unexpected response: %s", response)

            _command = f"*{command}={action}#"
            logger.debug("command %s", _command)
            self._connection.write(f"{_command}\r".encode("ascii"))
            self._connection.flush()

            empty_line_count = 0
            echo_received = None
            previous_response = None
            while True:
                if empty_line_count > 5:
                    logger.error("More than 5 empty responses")
                    if echo_received and previous_response:
                        # It's possible that the previous response is
                        # misinterpreted as being the command echo while it
                        # actually was the command response.
                        # In that case we continue the response processing
                        # using the previous response.
                        response = previous_response
                    else:
                        raise EmptyResponseError(command, action)
                else:
                    response = self._connection.readline()
                    response = response.decode()
                    # Cleanup response
                    response = response.strip(" \n\r\x00")
                    # Lowercase the response
                    logger.debug("Response: %s", response)

                    if response == "":
                        logger.debug("Empty line")
                        # Empty line
                        empty_line_count += 1
                        # Some projectors (X3000i) seem to return an empty line
                        # instead of a command echo in some cases.
                        # For that reason only give the projector some more time
                        # to respond after more than 1 empty line.
                        if empty_line_count > 1:
                            # Give the projector some more time to response
                            self._sleep(_SERIAL_TIMEOUT)
                        continue

                if response == ">":
                    logger.debug("Response is command prompt >")
                    continue

                if action == "?" and not echo_received and response == _command:
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

                response = response.lower()
                logger.debug("LC Response: %s", response)

                if response == "*illegal format#":
                    logger.error("Command %s illegal format", _command)
                    raise IllegalFormatError(command, action)

                if response == "*unsupported item#":
                    logger.error("Command %s unsupported item", _command)
                    raise UnsupportedItemError(command, action)

                if response == "*block item#":
                    logger.info("Command %s blocked item", _command)
                    raise BlockedItemError(command, action)

                logger.debug("Raw response: '%s'", response)
                matches = self._response_re.match(response)
                if not matches:
                    logger.error("Unexpected response format, response: %s", response)
                    raise InvallidResponseError(command, action, response)
                response = matches.group(2)
                logger.debug("Processed response: %s", response)

                return response
        except serial.SerialException as ex:
            logger.exception(
                "Problem communicating with %s, reason: %s", self._serial_port, ex
            )
            return None
        finally:
            self._busy = False

    def send_command(self, command: str, action: str = "?") -> str:
        """
        Send a command to the BenQ projector.
        """
        response = None

        try:
            response = self._send_command(command, action)
        except BenQProjectorError:
            pass

        return response

    def detect_commands(self):
        """
        Detects which command are supported by the projector.

        This is done by trying out all know commands.
        """
        logger.info("Detecting supported commands")
        # Empty the current list of supported commands.
        self._supported_commands = None
        supported_commands = []
        # Loop trough all known commands and test if a response is given.
        for command in PROJECTOR_CONFIGS["all"]["commands"]:
            try:
                response = self._send_command(command)
                if response is not None:
                    # A response is given, the command is supported.
                    logger.info("Command %s supported", command)
                    supported_commands.append(command)
            except BlockedItemError:
                supported_commands.append(command)
            except BenQProjectorError:
                pass
            finally:
                # Give the projector some time to process command
                self._sleep(0.2)
        # Set the list of known commands.
        self._supported_commands = supported_commands

        return self._supported_commands

    def _detect_modes(self, command, all_modes):
        """
        Detect which modes are supported by the projector.

        This is done by trying out all know modes.
        """
        if not self.supports_command(command):
            return []

        logger.debug("Detecting supported modes for %s", command)
        # Store current mode
        current_mode = self.send_command(command)
        logger.info("Current mode for %s: %s", command, current_mode)
        if current_mode is None:
            return []

        supported_modes = []
        # Loop trough all known modes and test if a response is given.
        for mode in all_modes:
            try:
                response = self._send_command(command, mode)
                if response is not None:
                    # A response is given, the mode is supported.
                    logger.debug("Mode %s supported", mode)
                    supported_modes.append(mode)
            except BlockedItemError:
                supported_modes.append(mode)
            except BenQProjectorError:
                pass
            finally:
                # Give the projector some time to process command
                self._sleep(0.2)

        # Revert mode back to current mode
        self.send_command(command, current_mode)

        return supported_modes

    def detect_video_sources(self):
        """
        Detect which video sources are supported by the projector.
        """
        logger.info("Detecting supported video sources")
        self.video_sources = self._detect_modes(
            "sour", PROJECTOR_CONFIGS["all"]["sources"]
        )
        return self.video_sources

    def detect_audio_sources(self):
        """
        Detect which audio sources are supported by the projector.
        """
        logger.info("Detecting supported audio sources")
        self.audio_sources = self._detect_modes(
            "audiosour", PROJECTOR_CONFIGS["all"]["audio_sources"]
        )
        return self.audio_sources

    def detect_picture_modes(self):
        """
        Detect which picture modes are supported by the projector.
        """
        logger.info("Detecting supported picture modes")
        self.picture_modes = self._detect_modes(
            "appmod", PROJECTOR_CONFIGS["all"]["picture_modes"]
        )
        return self.picture_modes

    def detect_color_temperatures(self):
        """
        Detect which color temperatures are supported by the projector.
        """
        logger.info("Detecting supported color temperatures")
        self.color_temperatures = self._detect_modes(
            "ct", PROJECTOR_CONFIGS["all"]["color_temperatures"]
        )
        return self.color_temperatures

    def detect_aspect_ratios(self):
        """
        Detect which aspect ratios are supported by the projector.
        """
        logger.info("Detecting supported aspec ratios")
        self.aspect_ratios = self._detect_modes(
            "asp", PROJECTOR_CONFIGS["all"]["aspect_ratios"]
        )
        return self.aspect_ratios

    def detect_projector_positions(self):
        """
        Detect which projector positions are supported by the projector.
        """
        logger.info("Detecting supported projector positions")
        self.projector_positions = self._detect_modes(
            "pp", PROJECTOR_CONFIGS["all"]["projector_positions"]
        )
        return self.projector_positions

    def detect_lamp_modes(self):
        """
        Detect which lamp modes are supported by the projector.
        """
        logger.info("Detecting supported lamp modes")
        self.lamp_modes = self._detect_modes(
            "lampm", PROJECTOR_CONFIGS["all"]["lamp_modes"]
        )
        return self.lamp_modes

    def detect_3d_modes(self):
        """
        Detect which 3d modes are supported by the projector.
        """
        logger.info("Detecting supported 3d modes")
        self.threed_modes = self._detect_modes(
            "3d", PROJECTOR_CONFIGS["all"]["3d_modes"]
        )
        return self.threed_modes

    def update_power(self) -> bool:
        """Update the current power state."""
        response = self.send_command("pow")
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

    def update_volume(self) -> bool:
        """Update the current volume state."""
        if self.supports_command("mute"):
            self.muted = self.send_command("mute") == "on"
            logger.debug("Muted: %s", self.muted)

        if self.supports_command("vol"):
            volume = self.send_command("vol")
            if volume is not None:
                try:
                    volume = int(volume)
                except ValueError:
                    volume = None
            logger.debug("Volume: %s", volume)

            self.volume = volume

    def update_video_source(self) -> bool:
        """Update the current video source state."""
        if self.supports_command("sour"):
            self.video_source = self.send_command("sour")
            logger.debug("Video source: %s", self.video_source)

    def update(self) -> bool:
        """
        Update all known states.

        This takes quite a lot of time.
        """
        if not self.update_power():
            return False

        if self.supports_command("directpower"):
            self.direct_power_on = self.send_command("directpower") == "on"
            logger.debug("Direct power on: %s", self.direct_power_on)

        if self.supports_command("ltim"):
            response = self.send_command("ltim")
            if response is not None:
                self.lamp_time = int(response)

        if self.supports_command("ltim2"):
            response = self.send_command("ltim2")
            if response is not None:
                self.lamp2_time = int(response)

        if self.power_status in [self.POWERSTATUS_OFF, self.POWERSTATUS_ON]:
            # Commands which only work when powered on or off, not when
            # powering on or off
            if self.supports_command("pp"):
                self.projector_position = self.send_command("pp")

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
                self.threed_mode = self.send_command("3d")
                logger.debug("3D: %s", self.threed_mode)

            if self.supports_command("appmod"):
                self.picture_mode = self.send_command("appmod")
                logger.debug("Picture mode: %s", self.picture_mode)

            if self.supports_command("asp"):
                self.aspect_ratio = self.send_command("asp")
                logger.debug("Aspect ratio: %s", self.aspect_ratio)

            if self.supports_command("bc"):
                self.brilliant_color = self.send_command("bc") == "on"
                logger.debug("Brilliant color: %s", self.brilliant_color)

            if self.supports_command("blank"):
                self.blank = self.send_command("blank") == "on"
                logger.debug("Blank: %s", self.blank)

            if self.supports_command("bri"):
                response = self.send_command("bri")
                if response is not None:
                    self.brightness = int(response)
                    logger.debug("Brightness: %s", self.brightness)

            if self.supports_command("color"):
                response = self.send_command("color")
                if response is not None:
                    self.color_value = int(response)
                    logger.debug("Color value: %s", self.color_value)

            if self.supports_command("con"):
                response = self.send_command("con")
                if response is not None:
                    self.contrast = int(response)
                    logger.debug("Contrast: %s", self.contrast)

            if self.supports_command("ct"):
                self.color_temperature = self.send_command("ct")
                logger.debug("Color temperature: %s", self.color_temperature)

            if self.supports_command("highaltitude"):
                self.high_altitude = self.send_command("highaltitude") == "on"
                logger.debug("High altitude: %s", self.high_altitude)

            if self.supports_command("lampm"):
                self.lamp_mode = self.send_command("lampm")
                logger.debug("Lamp mode: %s", self.lamp_mode)

            if self.supports_command("qas"):
                self.quick_auto_search = self.send_command("qas") == "on"
                logger.debug("Quick auto search: %s", self.quick_auto_search)

            if self.supports_command("sharp"):
                self.sharpness = self.send_command("sharp")
                logger.debug("Sharpness: %s", self.sharpness)

            self.update_video_source()
            self.update_volume()

        return True

    def turn_on(self):
        """
        Turn the projector on.

        First it tests if the projector is in a state that powering on is possible.
        """
        # Check the actual power state of the projector.
        response = self.send_command("pow")
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
                logger.error("Projector still powering off")
                return False
            self.power_status = self.POWERSTATUS_OFF
            self._power_timestamp = None

            # Continue powering on the projector.
            logger.info("Turning on projector")
            response = self.send_command("pow", "on")
            if response == "on":
                self.power_status = self.POWERSTATUS_POWERINGON
                self._power_timestamp = time.time()

                return True

            logger.error("Failed to turn on projector, response: %s", response)

        return False

    def turn_off(self):
        """
        Turn the projector off.

        First it tests if the projector is in a state that powering off is possible.
        """
        # Check the actual power state of the projector.
        response = self.send_command("pow")
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
                logger.error("Projector still powering on")
                return False
            self.power_status = self.POWERSTATUS_ON
            self._power_timestamp = None

            # Continue powering off the projector.
            logger.info("Turning off projector")
            response = self.send_command("pow", "off")
            if response == "off":
                self.power_status = self.POWERSTATUS_POWERINGOFF
                self._power_timestamp = time.time()

                return True

            logger.error("Failed to turn off projector, response: %s", response)

        return False

    def mute(self):
        """Mutes the volume."""
        response = self.send_command("mute", "on")
        if response == "on":
            self.muted = True
            return True

        return False

    def unmute(self):
        """Unmutes the volume."""
        response = self.send_command("mute", "off")
        if response == "off":
            self.muted = False
            return True

        return False

    def volume_up(self) -> None:
        """Increase volume."""
        if self.volume is None:
            self.update_volume()
        elif self.volume >= 20:  # Can't go higher than 20
            return False

        if self.send_command("vol", "+") == "+":
            self.volume += 1
            return True

        return False

    def volume_down(self) -> None:
        """Decrease volume."""
        if self.volume is None:
            self.update_volume()
        elif self.volume <= 0:  # Can't go lower than 0
            return False

        if self.send_command("vol", "-") == "-":
            self.volume -= 1
            return True

        return False

    def volume_level(self, level) -> None:
        """Set volume to a given level."""
        if self.volume == level:
            return True

        while self.volume < level:
            if not self.volume_up():
                return False

        while self.volume > level:
            if not self.volume_down():
                return False

        return True

    def select_video_source(self, video_source: str):
        """Select projector video source."""
        video_source = video_source.lower()

        if video_source not in self.video_sources:
            return False

        if self.send_command("sour", video_source) == video_source:
            self.video_source = video_source
            return True

        return False
