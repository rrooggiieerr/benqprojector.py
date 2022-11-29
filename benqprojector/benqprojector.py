"""
Implements the BenQProjector class for controlling BenQ projectors.

Created on 27 Nov 2022

@author: Rogier van Staveren
"""
import logging
import re
import time

import serial

from benqprojector.config import (
    BAUD_RATES,
    LAMP_MODES,
    PICTURE_MODES,
    POSITIONS,
    PROJECTOR_CONFIGS,
)

logger = logging.getLogger(__name__)


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
    _unique_id = None

    _supported_commands = None
    sources = None

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

    position = None

    lamp_mode = None
    lamp_time = None
    lamp2_time = None

    volume = None
    muted = None

    source = None
    threed = None  # 3D

    picture_mode = None
    aspect_ratio = None
    brilliant_color = None
    blank = None
    brightness = None
    color_value = None
    contrast = None
    color_temperature = None
    high_altitude = None
    quick_auto_search = None
    sharpness = None

    # Compile regular expression to match the command response.
    _response_re = re.compile(r"^\*?([^=]*)=(.*)#$")

    def __init__(
        self,
        serial_port: str,  # The serial port where the RS-485 interface and
        # screen is connected to.
        baud_rate,
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
                timeout=0.05,
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

        model = self.send_command("modelname")
        assert model is not None, "Failed to retrieve projector model"
        # Is projector powering down?
        self.model = model

        self._supported_commands = PROJECTOR_CONFIGS.get(model, {}).get(
            "commands", PROJECTOR_CONFIGS.get("all").get("commands")
        )

        self.sources = PROJECTOR_CONFIGS.get(model, {}).get(
            "sources", PROJECTOR_CONFIGS.get("all").get("sources")
        )

        self._poweron_time = PROJECTOR_CONFIGS.get(model, {}).get(
            "on_time", PROJECTOR_CONFIGS.get("all").get("poweron_time")
        )
        self._poweroff_time = PROJECTOR_CONFIGS.get(model, {}).get(
            "off_time", PROJECTOR_CONFIGS.get("all").get("poweroff_time")
        )

        mac = None
        if self.supports_command("macaddr"):
            mac = self.send_command("macaddr=?")

        if mac is not None:
            self._mac = mac.lower()
            self._unique_id = self._mac
        else:
            self._unique_id = self._serial_port

        logger.info("Device %s available", self._serial_port)

        self.update()

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

    def send_command(self, command: str, action: str = "?") -> str:
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
            logger.info("to busy for %s=%s", command, action)
            time.sleep(0.1)
        self._busy = True

        response = None

        try:
            self._connection.reset_input_buffer()
            self._connection.reset_output_buffer()

            # Clean input buffer
            self._connection.write(b"\r")
            self._connection.flush()
            response = self._connection.read(1)
            if response != ">":
                logger.debug("Unexpected response: %s", response)
                # Try to clean the input buffer by reading everything
                response = self._connection.read(1)
                logger.debug("Unexpected response: %s", response)

            command = f"*{command}={action}#"
            logger.debug("command %s", command)
            self._connection.write(f"{command}\r".encode("ascii"))
            self._connection.flush()

            linecount = 0
            echo_received = None
            while True:
                if linecount > 5:
                    logger.error("More than 5 empty responses")
                    return None

                response = self._connection.readline()
                response = response.decode()
                # Cleanup response
                response = response.strip(" \n\r\x00")
                # Lowercase the response
                response = response.lower()
                logger.debug("Response: %s", response)

                if response == "":
                    # empty line
                    linecount += 1
                    continue

                if response == ">":
                    logger.debug("Response is command prompt >")
                    continue

                if not echo_received:
                    if response == command:
                        # Command echo.
                        logger.debug("Command successfully send")
                        echo_received = True
                        continue
                    logger.error("No command echo received")
                    logger.error("Response: %s", response)
                    # Try to clean the input buffer by reading everything
                    response = self._connection.readlines()
                    logger.debug("Unexpected response: %s", response)
                    return None

                if response == "*illegal format#":
                    logger.error("Command %s illegal format", command)
                    return None

                if response == "*unsupported item#":
                    logger.error("Command %s unsupported item", command)
                    return None

                if response == "*block item#":
                    logger.debug("Command %s blocked item", command)
                    return None

                logger.debug("Raw response: '%s'", response)
                matches = self._response_re.match(response)
                if not matches:
                    logger.error("Unexpected response format, response: %s", response)
                    return None
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
            response = self.send_command(command, "?")
            if response is not None:
                # A response is given, the command is supported.
                logger.info("Command %s supported", command)
                supported_commands.append(command)
        # Set the list of known commands.
        self._supported_commands = supported_commands

        return self._supported_commands

    def detect_sources(self):
        """
        Detect which sources are supported by the projector.

        This is done by trying out all know sources.
        """
        logger.info("Detecting supported sources")
        # Empty the current list of supported sources.
        supported_sources = []
        # Loop trough all known sources and test if a response is given.
        for source in PROJECTOR_CONFIGS["all"]["sources"]:
            response = self.send_command("sour", source)
            if response is not None:
                # A response is given, the source is supported.
                logger.info("Source %s supported", source)
                supported_sources.append(source)
        # Set the list of known sources.
        self.sources = supported_sources

        return self.sources

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
        elif response == "on":
            if (
                self.power_status == self.POWERSTATUS_POWERINGON
                and (time.time() - self._power_timestamp) <= self._poweron_time
            ):
                logger.debug("Projector still powering on")
            else:
                self.power_status = self.POWERSTATUS_ON
                self._power_timestamp = None
        else:
            logger.error("Unknown power status: %s", response)
            # self.power_status = self.POWERSTATUS_UNKNOWN
            return False

        return True

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

        return True

    def update_source(self) -> bool:
        """Update the current source state."""
        if self.supports_command("sour"):
            self.source = self.send_command("sour")
            logger.debug("Source: %s", self.source)

            return True

        return False

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
                response = self.send_command("pp")
                self.position = POSITIONS.get(response, response)

        if self.power_status in [self.POWERSTATUS_POWERINGOFF, self.POWERSTATUS_OFF]:
            self.threed = None
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

            self.source = None

            self.muted = None
            self.volume = None
        elif self.power_status in [self.POWERSTATUS_POWERINGON, self.POWERSTATUS_ON]:
            # Commands which only work when powered on
            if self.supports_command("3d"):
                self.threed = self.send_command("3d")
                logger.debug("3D: %s", self.threed)

            if self.supports_command("appmod"):
                response = self.send_command("appmod")
                self.picture_mode = PICTURE_MODES.get(response, response)
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
                response = self.send_command("lampm")
                self.lamp_mode = LAMP_MODES.get(response, response)
                logger.debug("Lamp mode: %s", self.lamp_mode)

            if self.supports_command("qas"):
                self.quick_auto_search = self.send_command("qas") == "on"
                logger.debug("Quick auto search: %s", self.quick_auto_search)

            if self.supports_command("sharp"):
                self.sharpness = self.send_command("sharp")
                logger.debug("Sharpness: %s", self.sharpness)

            self.update_source()
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

    def select_source(self, source: str):
        """Select projector input source."""
        source = source.lower()

        if source not in self.sources:
            return False

        # self.send_command("sour", source)
        # response = self._projector.send_command("sour")
        if self.send_command("sour", source) == source:
            self.source = source
            return True

        return False
