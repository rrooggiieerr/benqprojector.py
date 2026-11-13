"""Simulated connections and a simulated BenQ projector for the tests.

A simulated connection is reached with the real serialx: `serial_simulation()` creates a
pseudo-terminal, like a projector on a USB to serial adapter, and `tcp_simulation()` a TCP server
on 127.0.0.1, like a projector on the network. Both return the url to connect to. A
`SimulatedProjector` on that url answers the library the way a BenQ projector does:

    url = await serial_simulation()  # or tcp_simulation()
    projector_simulation = SimulatedProjector(url, "W1110", {"pow": "OFF"})
    projector = BenQProjectorSerial(url, 9600)
    await projector.connect()

Without a SimulatedProjector, a simulated connection never answers.

A projector on a serial connection has a command prompt. On a network connection it behaves like
a projector with an integrated network interface, without a prompt, unless `prompt=True` makes it
a projector behind a serial to network bridge.

The configuration file of the model is assumed to be correct: the projector supports exactly the
commands in it. A projector of a model without a configuration file supports the commands in
minimal.json, `pow` and `modelname`, and the commands in the given values.
"""

import asyncio
import contextlib
import json
import os
from pathlib import Path
import re
from typing import Any

import pytest

_CONFIGS = Path(__file__).resolve().parent.parent / "benqprojector" / "configs"

_COMMAND_RE = re.compile(
    r"\*(?P<command>[a-z0-9]+)(?:=(?P<action>[^#]*))?#", re.IGNORECASE
)

UNSUPPORTED_ITEM = "*Unsupported item#"
ILLEGAL_FORMAT = "*Illegal format#"
BLOCK_ITEM = "*Block item#"

# Run a test over a serial and over a network connection
both_transports = pytest.mark.parametrize("url", ["serial", "network"], indirect=True)


# Simulated connections


class _Endpoint:
    """The projector's end of a simulated connection."""

    network = False

    def __init__(self) -> None:
        self.projector: SimulatedProjector | None = None
        # When unplugged, the connection stays open, but nothing gets through
        self.plugged = True

    def receive(self, data: bytes) -> None:
        """Passes what the library sent to the projector, if there is one."""
        if self.projector is not None and self.plugged:
            self.projector.receive(data)

    def write(self, data: bytes) -> None:
        """Sends data to the library."""
        if self.plugged:
            self._write(data)

    def _write(self, data: bytes) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        """Drops the connection."""
        raise NotImplementedError

    async def async_stop(self) -> None:
        """Stops the simulated connection."""
        self.disconnect()


class _SerialEndpoint(_Endpoint):
    """The projector's end of a pseudo-terminal."""

    def __init__(self) -> None:
        super().__init__()
        import tty  # noqa: PLC0415  # Not available on Windows

        self._master_fd: int | None
        self._slave_fd: int | None
        self._master_fd, self._slave_fd = os.openpty()
        # Raw mode: no echo, and no translation of line endings
        tty.setraw(self._slave_fd)
        os.set_blocking(self._master_fd, False)
        asyncio.get_running_loop().add_reader(self._master_fd, self._on_data)
        self.url = os.ttyname(self._slave_fd)

    def _on_data(self) -> None:
        assert self._master_fd is not None
        try:
            data = os.read(self._master_fd, 4096)
        except BlockingIOError:
            return
        except OSError:
            # The library closed its end
            asyncio.get_running_loop().remove_reader(self._master_fd)
            return
        self.receive(data)

    def _write(self, data: bytes) -> None:
        if self._master_fd is not None:
            with contextlib.suppress(OSError):
                os.write(self._master_fd, data)

    def disconnect(self) -> None:
        """A removed USB to serial adapter: the pseudo-terminal is gone for good."""
        if self._master_fd is not None:
            asyncio.get_running_loop().remove_reader(self._master_fd)
        for fd in (self._master_fd, self._slave_fd):
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)
        self._master_fd = self._slave_fd = None


class _NetworkEndpoint(_Endpoint):
    """The projector's end of a TCP connection."""

    network = True

    def __init__(self) -> None:
        super().__init__()
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self.url = ""

    async def async_start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"socket://127.0.0.1:{port}"

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writers.add(writer)
        try:
            while data := await reader.read(4096):
                self.receive(data)
        except ConnectionError:
            pass
        finally:
            self._writers.discard(writer)
            writer.close()

    def _write(self, data: bytes) -> None:
        for writer in self._writers:
            writer.write(data)

    def disconnect(self) -> None:
        """A lost network connection. The projector keeps listening, so the library can reconnect."""
        for writer in self._writers:
            writer.close()
        self._writers.clear()

    async def async_stop(self) -> None:
        """The projector is gone: the connection is dropped and nothing listens anymore."""
        self.disconnect()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


_endpoints: dict[str, _Endpoint] = {}


async def serial_simulation() -> str:
    """Creates a simulated serial connection, and returns its url, e.g. /dev/ttys012."""
    if not hasattr(os, "openpty"):
        pytest.skip("Pseudo-terminals are not supported on this platform")
    endpoint = _SerialEndpoint()
    _endpoints[endpoint.url] = endpoint
    return endpoint.url


async def tcp_simulation() -> str:
    """Creates a simulated network connection, and returns its url, socket://127.0.0.1:<port>."""
    endpoint = _NetworkEndpoint()
    await endpoint.async_start()
    _endpoints[endpoint.url] = endpoint
    return endpoint.url


async def async_stop_simulations() -> None:
    """Stops all simulated connections."""
    while _endpoints:
        _url, endpoint = _endpoints.popitem()
        await endpoint.async_stop()


# A simulated projector


def read_model_config(model: str | None) -> dict[str, Any]:
    """The configuration of a model, minimal.json when the model has no configuration file.

    Keys the configuration file of the model doesn't have come from minimal.json.
    """
    config: dict[str, Any] = json.loads((_CONFIGS / "minimal.json").read_text())
    if model:
        file_name = (
            "".join(c if c.isalnum() or c in "._-" else "_" for c in model.lower())
            + ".json"
        )
        path = _CONFIGS / file_name
        if path.is_file():
            config.update(json.loads(path.read_text()))
    return config


# The configuration lists the values of these commands
_ENUM_COMMANDS = {
    "3d": "3d_modes",
    "appmod": "picture_modes",
    "asp": "aspect_ratios",
    "audiosour": "audio_sources",
    "ct": "color_temperatures",
    "lampm": "lamp_modes",
    "menuposition": "menu_positions",
    "pp": "projector_positions",
    "sour": "video_sources",
}
_NUMBER_COMMANDS = {
    "bgain",
    "boffset",
    "bri",
    "color",
    "con",
    "ggain",
    "goffset",
    "hdrbri",
    "ltim",
    "ltim2",
    "rgain",
    "roffset",
    "sharp",
    "tint",
    "vkeystone",
    "vol",
}
_VOLUME_MAX = 20


def default_values(model: str | None, config: dict[str, Any]) -> dict[str, str]:
    """A plausible value for every command of a configuration, as the projector sends it.

    The projector is on, enums get their first value, numbers 0, and other commands OFF.
    """
    values: dict[str, str] = {}
    for command in config.get("commands", []):
        if command in _ENUM_COMMANDS:
            options = config.get(_ENUM_COMMANDS[command]) or ["OFF"]
            values[command] = options[0].upper()
        elif command in _NUMBER_COMMANDS:
            values[command] = "0"
        else:
            values[command] = "OFF"
    values["pow"] = "ON"
    if "modelname" in values:
        if model is None:
            # A projector which doesn't report its model
            del values["modelname"]
        else:
            values["modelname"] = model
    return values


class SimulatedProjector:
    """A simulated BenQ projector of a given model, on a simulated connection.

    The defaults follow traffic captured from real projectors (homeassistant-benqprojector
    issues #64 and #67). A projector with a prompt sends the prompt in front of the echo of a
    command line, ends the echo with \\r\\r\\n and the answer with \\r\\n, and doesn't send a
    prompt after the answer:

        >*pow=?#\\r\\r\\n*POW=ON#\\r\\n

    It answers an empty line with the prompt, unless `empty_line_prompt` says otherwise for its
    power state. Commands the projector doesn't support are answered with `*Unsupported item#`,
    and commands in `blocked` with `*Block item#`.

    Values are kept as the projector sends them, e.g. "ON" or "HDMI". The projector also sends
    a value it is set to in capitals, except for the model name.

    Models which don't follow the protocol, see quirks.md, are simulated with the options, most
    of which can differ for the projector being on and off, given as {"on": ..., "off": ...}. A
    raw response replaces everything the projector sends for a command line, the echo included:

        raw_responses={
            "*modelname=?#": {"off": b">*modelname=?#W700\\r\\n", "on": b"*modelname=?#\\r\\nW700\\r\\n"}
        }

    For behaviour the options don't cover, subclass and override `answer()`, and set
    PROJECTOR_CLASS in the test module.
    """

    def __init__(
        self,
        url: str,
        model: str | None = None,
        values: dict[str, str] | None = None,
        *,
        prompt: bool | None = None,
        empty_line_prompt: bool | dict[str, bool] = True,
        echo: bool | bytes = True,
        echo_prefix: bytes | None = None,
        line_ending: bytes = b"\r\n",
        prompt_response: bytes = b">",
        no_prompt_response: bytes = b"",
        blocked: set[str] | dict[str, set[str]] | None = None,
        drop_first_byte: bool | dict[str, bool] = False,
        idle_time: float = 1.0,
        delay: float = 0.0,
        raw_responses: dict[str, bytes | dict[str, bytes]] | None = None,
    ) -> None:
        """Initializes a simulated projector on the simulated connection with the url.

        prompt: Whether the projector has a command prompt, by default only on a serial
            connection.
        empty_line_prompt: Whether a projector with a prompt answers an empty line with it. The
            W2700 doesn't while its lamp is on.
        echo: Whether the projector echoes a command line, or what it sends instead, e.g.
            b"\\r\\n" for an empty line.
        echo_prefix: What precedes the echo, by default the prompt for a projector with a
            prompt.
        line_ending: What ends the answer, the W4100i ends it with \\r only.
        prompt_response: What the projector sends as its prompt.
        no_prompt_response: What a projector without a prompt sends on an empty line, by
            default nothing.
        blocked: Commands, like "modelname", or command lines, like "*pow=?#", the projector
            refuses.
        drop_first_byte: Whether the projector drops the first byte it receives after
            `idle_time` seconds without receiving anything, to wake up. The W4100i does in
            standby.
        delay: Seconds the projector waits before it answers.
        raw_responses: What the projector sends for a command line, like "*modelname=?#",
            instead of the echo and the answer.
        """
        if (endpoint := _endpoints.get(url)) is None:
            raise ValueError(f"No simulated connection {url}")
        if endpoint.projector is not None:
            raise ValueError(f"There already is a simulated projector on {url}")
        endpoint.projector = self
        self._endpoint = endpoint

        self.url = url
        self.model = model
        self.prompt = not endpoint.network if prompt is None else prompt
        self.empty_line_prompt = empty_line_prompt
        self.echo = echo
        self.echo_prefix = echo_prefix
        self.line_ending = line_ending
        self.prompt_response = prompt_response
        self.no_prompt_response = no_prompt_response
        self.blocked = blocked if isinstance(blocked, dict) else set(blocked or ())
        self.drop_first_byte = drop_first_byte
        self.idle_time = idle_time
        self.delay = delay
        self.raw_responses = {
            line.lower(): raw for line, raw in (raw_responses or {}).items()
        }

        config = read_model_config(model)
        self._config = config
        self._values = default_values(model, config)
        self._values.update(
            {key.lower(): value for key, value in (values or {}).items()}
        )

        self._buffer = b""
        self._last_received: float | None = None
        # Whether the prompt was just sent for an empty line, the echo then follows it
        self._prompted = False
        # Everything the library sent, and every command line, for assertions
        self.received = bytearray()
        self.commands: list[str] = []

    # Test API

    def get(self, command: str) -> str | None:
        """The value of a command on the projector, as it sends it."""
        return self._values.get(command.lower())

    def unplug(self) -> None:
        """Pulls the cable: the connection stays open, but nothing gets through."""
        self._endpoint.plugged = False

    def plug(self) -> None:
        """Plugs the cable back in."""
        self._endpoint.plugged = True

    @property
    def power(self) -> str:
        """The power state of the projector, "on" or "off"."""
        return "on" if self._values.get("pow", "").upper() == "ON" else "off"

    # Projector behaviour

    def _for_power(self, option: Any, default: Any) -> Any:
        """The value of an option for the current power state."""
        if isinstance(option, dict):
            return option.get(self.power, default)
        return option

    def receive(self, data: bytes) -> None:
        """Handles what the library sent. Called by the simulated connection."""
        self.received += data

        now = asyncio.get_running_loop().time()
        idle = self._last_received is None or now - self._last_received > self.idle_time
        self._last_received = now
        if data and idle and self._for_power(self.drop_first_byte, False):
            data = data[1:]

        *lines, self._buffer = (self._buffer + data).split(b"\r")
        for line in lines:
            self._handle_line(line.decode("ascii", errors="replace").strip("\n"))

    def _handle_line(self, line: str) -> None:
        if line:
            self.commands.append(line)

        if not line.startswith("*"):
            # An empty line, or a command without its first byte: only the prompt
            if self.prompt and self._for_power(self.empty_line_prompt, True):
                self._write(self.prompt_response)
                self._prompted = True
            elif not self.prompt:
                self._write(self.no_prompt_response)
            return

        prompted, self._prompted = self._prompted, False

        answer = self.answer(line)
        if (raw := self._raw_response(line)) is not None:
            data = raw
        else:
            if self.echo is True:
                if prompted:
                    # The prompt of the empty line in front of the command
                    data = b""
                elif self.echo_prefix is not None:
                    data = self.echo_prefix
                else:
                    data = self.prompt_response if self.prompt else b""
                data += f"{line}\r\r\n".encode("ascii")
            elif self.echo is False:
                data = b""
            else:
                data = self.echo
            data += answer.encode("ascii") + self.line_ending
        self._write(data)

    def _write(self, data: bytes) -> None:
        """Sends data to the library, after the delay."""
        if not data:
            return
        if self.delay:
            asyncio.get_running_loop().call_later(
                self.delay, self._endpoint.write, data
            )
        else:
            self._endpoint.write(data)

    def _raw_response(self, line: str) -> bytes | None:
        """The raw response to a command line, None to answer as usual."""
        raw = self.raw_responses.get(line.strip().lower())
        if isinstance(raw, dict):
            return raw.get(self.power)
        return raw

    def answer(self, line: str) -> str:
        """The projector's answer to a command line, like "*POW=ON#"."""
        if not (match := _COMMAND_RE.fullmatch(line.strip())):
            return ILLEGAL_FORMAT

        command = match["command"].lower()
        action = match["action"]
        if command not in self._values:
            return UNSUPPORTED_ITEM
        blocked = self._for_power(self.blocked, set())
        if command in blocked or line.strip().lower() in blocked:
            return BLOCK_ITEM

        name = command.upper()
        if action is None:
            return f"*{name}#"
        if action == "?":
            return f"*{name}={self._values[command]}#"
        if action in ("+", "-"):
            if command in _NUMBER_COMMANDS:
                self._step(command, 1 if action == "+" else -1)
            return f"*{name}={action}#"
        if command == "modelname":
            return ILLEGAL_FORMAT
        # The modes of a command in the configuration, a command only in the values has no limits
        modes = (
            self._config.get(_ENUM_COMMANDS.get(command, ""))
            if command in self._config["commands"]
            else None
        )
        if modes is not None and action.lower() not in modes:
            # A mode the model doesn't support
            return ILLEGAL_FORMAT

        self._values[command] = action.upper()
        return f"*{name}={action.upper()}#"

    def _step(self, command: str, direction: int) -> None:
        try:
            number = int(self._values[command]) + direction
        except ValueError:
            return
        if command == "vol":
            number = max(0, min(number, _VOLUME_MAX))
        self._values[command] = str(number)
