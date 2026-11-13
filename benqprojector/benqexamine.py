"""Implements the BenQProjector examine class.

Created on 23 Jan 2025

@author: Rogier van Staveren
"""

import asyncio
import logging
from typing import Any

from . import BenQProjector
from .benqclasses import (
    BenQBlockedItemError,
    BenQCommand,
    BenQProjectorError,
    BenQResponseTimeoutError,
)

logger = logging.getLogger(__name__)

# Attempts to restore a mode after detecting the modes, and the delay between them
RESTORE_ATTEMPTS = 3
RESTORE_DELAY = 1.0

# Commands which are not detected, as they change what the projector shows
IGNORE_COMMANDS = (
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
)


class BenQProjectorExamine:
    """BenQProjectorExamine class for detecting BenQ projector features."""

    _projector: BenQProjector

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

    def __init__(
        self,
        projector: BenQProjector,
    ):
        """Initialise the examine object for the given projector."""
        assert projector is not None

        self._projector = projector

    async def detect_commands(self) -> list[str]:
        """Detects which command are supported by the projector.

        This is done by trying out all know commands.
        """
        if self._projector._interactive:  # noqa: SLF001
            print("Supported commands:", end="", flush=True)
        else:
            logger.info("Detecting supported commands")

        # Empty the projector's list of supported commands, else only the commands already
        # known to be supported are tried.
        self._projector._supported_commands = None  # noqa: SLF001
        supported_commands = []
        # Loop through all known commands and test if a response is given.
        for command in self._projector.projector_config_all.get("commands", []):
            if command in IGNORE_COMMANDS:
                continue

            retries = 0
            while True:
                try:
                    try:
                        response = await self._projector._send_command(  # noqa: SLF001
                            BenQCommand(command)
                        )
                        if response is not None:
                            supported_commands.append(command)
                        else:
                            command = None  # noqa: PLW2901
                    except BenQBlockedItemError:
                        supported_commands.append(command)
                        command = f"{command}?"  # noqa: PLW2901
                    except BenQResponseTimeoutError:
                        if retries < 2:
                            retries += 1
                            continue

                        supported_commands.append(command)
                        command = f"{command}¿"  # noqa: PLW2901

                    if command:
                        # A response is given, the command is supported.
                        if self._projector._interactive:  # noqa: SLF001
                            print(f" {command}", end="", flush=True)
                        else:
                            logger.info("Command %s supported", command)
                except BenQProjectorError:
                    pass
                finally:
                    # Give the projector some time to process command
                    await asyncio.sleep(0.2)
                break
        # Set the list of known commands, the modes are only detected for these commands.
        self._supported_commands = supported_commands
        self._projector._supported_commands = supported_commands  # noqa: SLF001

        if self._projector._interactive:  # noqa: SLF001
            print()

        return self._supported_commands

    async def _detect_modes(
        self, description: str, command: str, all_modes: list[str] | None
    ) -> list[str]:
        """Detect which modes are supported by the projector.

        This is done by trying out all know modes.
        """
        if not all_modes or not self._projector.supports_command(command):
            return []

        if self._projector._interactive:  # noqa: SLF001
            print(f"Supported {description}:", end="", flush=True)
        else:
            logger.info("Detecting supported video sources")

        # Store the current mode exactly as the projector reports it, to restore it later
        current_mode = await self._read_mode(command)
        if not self._projector._interactive:  # noqa: SLF001
            logger.info("Current %s: %s", description, current_mode)
        if current_mode is None:
            return []

        supported_modes: list[str] = []
        try:
            # Loop through all known modes and test if a response is given.
            for mode in all_modes:
                label: str | None = mode
                try:
                    try:
                        response = await self._projector._send_command(  # noqa: SLF001
                            BenQCommand(command, mode)
                        )
                        if response is not None:
                            supported_modes.append(mode)
                        else:
                            label = None
                    except BenQBlockedItemError:
                        supported_modes.append(mode)
                        label = f"{mode}?"
                    except BenQResponseTimeoutError:
                        supported_modes.append(mode)
                        label = f"{mode}¿"

                    if label:
                        # A response is given, the mode is supported.
                        if self._projector._interactive:  # noqa: SLF001
                            print(f" {label}", end="", flush=True)
                        else:
                            logger.debug("Mode %s supported", label)
                except BenQProjectorError:
                    pass
                finally:
                    # Give the projector some time to process command
                    await asyncio.sleep(0.2)
        finally:
            # Always restore the original mode, also when the detection is interrupted
            await self._restore_mode(command, current_mode)

        if self._projector._interactive:  # noqa: SLF001
            print()

        return supported_modes

    async def _read_mode(self, command: str) -> str | None:
        """Read the current mode of a command, exactly as the projector reports it."""
        try:
            return await self._projector._send_command(  # noqa: SLF001
                BenQCommand(command), lowercase_response=False
            )
        except BenQProjectorError:
            return None

    async def _restore_mode(self, command: str, mode: str) -> bool:
        """Set a command back to the given mode, retrying when the projector refuses."""
        for attempt in range(1, RESTORE_ATTEMPTS + 1):
            try:
                response = await self._projector._send_command(  # noqa: SLF001
                    BenQCommand(command, mode), lowercase_response=False
                )
                if response is not None and response.lower() == mode.lower():
                    return True
            except BenQProjectorError:
                pass
            if attempt < RESTORE_ATTEMPTS:
                # The projector may still be busy, e.g. switching sources
                await asyncio.sleep(RESTORE_DELAY * attempt)

        logger.warning("Unable to restore %s to %s", command, mode)
        return False

    async def detect_video_sources(self) -> list[str]:
        """Detect which video sources are supported by the projector."""
        self.video_sources = await self._detect_modes(
            "video sources",
            "sour",
            self._projector.projector_config_all.get("video_sources"),
        )
        return self.video_sources

    async def detect_audio_sources(self) -> list[str]:
        """Detect which audio sources are supported by the projector."""
        self.audio_sources = await self._detect_modes(
            "audio sources",
            "audiosour",
            self._projector.projector_config_all.get("audio_sources"),
        )
        return self.audio_sources

    async def detect_picture_modes(self) -> list[str]:
        """Detect which picture modes are supported by the projector."""
        self.picture_modes = await self._detect_modes(
            "picture modes",
            "appmod",
            self._projector.projector_config_all.get("picture_modes"),
        )
        return self.picture_modes

    async def detect_color_temperatures(self) -> list[str]:
        """Detect which color temperatures are supported by the projector."""
        self.color_temperatures = await self._detect_modes(
            "color temperatures",
            "ct",
            self._projector.projector_config_all.get("color_temperatures"),
        )
        return self.color_temperatures

    async def detect_aspect_ratios(self) -> list[str]:
        """Detect which aspect ratios are supported by the projector."""
        self.aspect_ratios = await self._detect_modes(
            "aspect ratios",
            "asp",
            self._projector.projector_config_all.get("aspect_ratios"),
        )
        return self.aspect_ratios

    async def detect_projector_positions(self) -> list[str]:
        """Detect which projector positions are supported by the projector."""
        self.projector_positions = await self._detect_modes(
            "projector positions",
            "pp",
            self._projector.projector_config_all.get("projector_positions"),
        )
        return self.projector_positions

    async def detect_lamp_modes(self) -> list[str]:
        """Detect which lamp modes are supported by the projector."""
        self.lamp_modes = await self._detect_modes(
            "lamp modes",
            "lampm",
            self._projector.projector_config_all.get("lamp_modes"),
        )
        return self.lamp_modes

    async def detect_3d_modes(self) -> list[str]:
        """Detect which 3d modes are supported by the projector."""
        self.threed_modes = await self._detect_modes(
            "3d modes", "3d", self._projector.projector_config_all.get("3d_modes")
        )
        return self.threed_modes

    async def detect_menu_positions(self) -> list[str]:
        """Detect which menu positions are supported by the projector."""
        self.menu_positions = await self._detect_modes(
            "menu positions",
            "menuposition",
            self._projector.projector_config_all.get("menu_positions"),
        )
        return self.menu_positions

    async def detect_projector_features(self) -> dict[str, Any] | None:
        """Detect which features are supported by the projector."""
        if self._projector.power_status == BenQProjector.POWERSTATUS_OFF:
            logger.error("Projector needs to be on to examine it's features.")
            return None

        config: dict[str, Any] = {}

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
