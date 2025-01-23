"""
Implements the BenQProjector error classes.

Created on 23 Jan 2025

@author: Rogier van Staveren
"""

import asyncio


class BenQRawCommand:
    """
    BenQ Raw Command.
    """

    def __init__(self, raw_command: str):
        assert raw_command is not None

        self._command = None
        self._action = None
        self._raw_command = raw_command

    @property
    def command(self) -> str | None:
        """
        The command.
        """
        return self._command

    @property
    def action(self) -> str | None:
        """
        The command action.
        """
        return self._action

    @property
    def raw_command(self) -> str:
        """
        The raw command.
        """
        return self._raw_command


class BenQCommand(BenQRawCommand):
    """
    BenQ Command.
    """

    def __init__(self, command: str, action: str | None = "?"):
        assert command is not None

        command = command.lower()
        if action is None:
            raw_command = f"*{command}#"
        else:
            raw_command = f"*{command}={action}#"
        super().__init__(raw_command)

        self._command = command.lower()
        self._action = action


class BenQProjectorError(Exception):
    """
    Generic BenQ Projector error.
    """

    def __init__(self, command: BenQRawCommand | None = None):
        self.command = command


class BenQIllegalFormatError(BenQProjectorError):
    """
    Illegal command format error.

    If a command format is illegal, it will echo Illegal format.
    """

    def __str__(self):
        # pylint: disable=line-too-long
        return f"Illegal format for command '{self.command.command}' and action '{self.command.action}'"


class BenQEmptyResponseError(BenQProjectorError):
    """
    Empty response error.

    If the response is empty.
    """

    def __str__(self):
        # pylint: disable=line-too-long
        return f"Empty response for command '{self.command.command}' and action '{self.command.action}'"


class BenQUnsupportedItemError(BenQProjectorError):
    """
    Unsupported item error.

    If a command with correct format is not valid for the projector model it will echo
    `Unsupported item`.
    """

    def __str__(self):
        # pylint: disable=line-too-long
        return f"Unsupported item for command '{self.command.command}' and action '{self.command.action}'"


class BenQBlockedItemError(BenQProjectorError):
    """
    Blocked item error.

    If a command with correct format cannot be executed under certain condition it will echo
    `Block item`.
    """

    def __str__(self):
        # pylint: disable=line-too-long
        return f"Block item for command '{self.command.command}' and action '{self.command.action}'"


class BenQInvallidResponseError(BenQProjectorError):
    """
    Invalid response error.

    If the response format does not match the expected format.
    """

    def __init__(self, command=None, response=None):
        super().__init__(command)
        self.response = response

    def __str__(self):
        # pylint: disable=line-too-long
        return f"Invalid response for command '{self.command.command}' and action '{self.command.action}'. response: {self.response}"


class BenQResponseTimeoutError(BenQProjectorError, asyncio.exceptions.TimeoutError):
    """
    Response timeout error.

    If the response takes to long to receive.
    """

    def __str__(self):
        # pylint: disable=line-too-long
        return f"Response timeout for command '{self.command.command}' and action '{self.command.action}'"


class BenQPromptTimeoutError(BenQResponseTimeoutError):
    """
    Prompt timeout error.

    If the command prompt takes to long to receive.
    """

    def __str__(self):
        # pylint: disable=line-too-long
        return f"Prompt timeout for command '{self.command.command}' and action '{self.command.action}'"


class BenQTooBusyError(BenQProjectorError):
    """
    Too busy error.

    If the connection is to busy with processing other commands.
    """

    def __str__(self):
        return f"Too busy to send '{self.command.command}' and action '{self.command.action}'"
