"""
Shared pytest configuration and fixtures for the BenQ projector tests.

How to run the tests is described in __init__.py.

The ``--hardware`` and ``--baud-rate`` options select the real projector. The tests which work on
any projector use the ``connected_projector`` fixture: a simulated projector with and without a
command prompt, or the real projector once. The model tests use the ``url``, ``projector`` and
``projector_simulation`` fixtures, configured by the MODEL, VALUES, OPTIONS and PROJECTOR_CLASS
of their module. Model tests over both a serial and a network connection only run over the
connection of the --hardware url. ``_check_state`` skips a test when the real projector is not in
the state the test needs, ``restore_settings`` sets changed settings back.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
import types
from typing import Any

import pytest

from benqprojector import (
    BAUD_RATES,
    BenQCommand,
    BenQProjector,
    BenQProjectorError,
    BenQProjectorSerial,
    benqexamine,
)
from benqprojector.benqconnection import NETWORK_URL_SCHEMES
from benqprojector.benqexamine import IGNORE_COMMANDS, BenQProjectorExamine

from .simulation import (
    SimulatedProjector,
    async_stop_simulations,
    read_model_config,
    serial_simulation,
    tcp_simulation,
)

DEFAULT_BAUD_RATE = 115200


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line options for the hardware tests."""
    group = parser.getgroup("benqprojector", "BenQ projector hardware tests")
    group.addoption(
        "--hardware",
        metavar="URL",
        default=None,
        help="Run the tests against the real BenQ projector at URL, a serial port like "
        "/dev/tty.usbserial-10 or a network address like socket://host:8000.",
    )
    group.addoption(
        "--baud-rate",
        type=int,
        default=DEFAULT_BAUD_RATE,
        help=f"Baud rate of the serial port (default: {DEFAULT_BAUD_RATE}).",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Run the tests of any projector with and without a command prompt.

    Against a real projector they run once, the projector has a prompt or it doesn't.
    """
    if "connected_projector" in metafunc.fixturenames and not metafunc.config.getoption(
        "--hardware"
    ):
        metafunc.parametrize(
            "connected_projector", ["prompt", "no_prompt"], indirect=True
        )


@pytest.fixture
def baud_rate(request: pytest.FixtureRequest) -> int:
    """Baud rate of the serial port."""
    return request.config.getoption("--baud-rate")


# Simulated projectors


@pytest.fixture(autouse=True)
async def stop_simulations() -> AsyncIterator[None]:
    """Stops the simulations a test created when the test is finished."""
    yield
    await async_stop_simulations()


@pytest.fixture
async def url(request: pytest.FixtureRequest, hardware: bool) -> str:
    """The url of the connection, serial unless a test asks for "network".

    Without --hardware this is a simulated connection, with --hardware the url of the real
    projector. Use `@both_transports` from simulation.py to run a test
    over both.
    """
    transport = getattr(request, "param", "serial")
    if hardware:
        return _hardware_url(request, transport)
    if transport == "network":
        return await tcp_simulation()
    return await serial_simulation()


@pytest.fixture
def projector_simulation(
    request: pytest.FixtureRequest, url: str, hardware: bool
) -> SimulatedProjector:
    """A simulated projector on the url.

    The projector is of the test module's MODEL, with the module's VALUES and OPTIONS, the
    keyword arguments of SimulatedProjector, and PROJECTOR_CLASS, a subclass of it, if it has
    them. A test changes the projector with `@pytest.mark.simulated_projector(model=..., values=...,
    prompt=..., echo=..., blocked=...)`, or with the same keys in a dict through indirect
    parametrization of `projector_simulation`. Values are added to the module's VALUES, unless
    the test gives another model.
    """
    if hardware:
        pytest.skip("Needs the simulated projector")
    return _create_simulation(request, url, getattr(request, "param", {}))


def _create_simulation(
    request: pytest.FixtureRequest, url: str, params: dict[str, Any]
) -> SimulatedProjector:
    """Create the simulated projector of the test module on the url.

    params are the options from indirect parametrization of the fixture.
    """
    marker = request.node.get_closest_marker("simulated_projector")
    options = {
        **getattr(request.module, "OPTIONS", {}),
        **(marker.kwargs if marker else {}),
        **params,
    }

    module_model: str | None = getattr(request.module, "MODEL", None)
    model = options.pop("model", module_model)
    values: dict[str, str] = {}
    if model == module_model:
        values.update(getattr(request.module, "VALUES", {}))
    values.update(options.pop("values", {}))

    projector_class: type[SimulatedProjector] = getattr(
        request.module, "PROJECTOR_CLASS", SimulatedProjector
    )
    return projector_class(url, model, values, **options)


@pytest.fixture
async def projector(
    request: pytest.FixtureRequest, url: str, hardware: bool
) -> AsyncIterator[BenQProjectorSerial]:
    """A BenQ projector object of the test module's MODEL, disconnected at the end of the test.

    Without --hardware the projector is simulated, and not connected yet. With --hardware it is
    the real projector, already connected, and the test is skipped when the projector isn't in
    the state the test needs.
    """
    if not hardware:
        request.getfixturevalue("projector_simulation")
        simulated = BenQProjectorSerial(url, 9600)
        yield simulated
        await simulated.disconnect()
        return

    real = BenQProjectorSerial(url, _hardware_baud_rate(request, url))
    try:
        assert await real.connect(), f"Unable to connect to the projector on {url}"
        await _check_state(request, real)
    except BaseException:
        await real.disconnect()
        raise
    yield real
    await real.disconnect()


async def _check_state(
    request: pytest.FixtureRequest,
    projector: BenQProjectorSerial,
    default_power: str | None = "ON",
) -> None:
    """Skip the test when the real projector is not in the state the test needs.

    The power state comes from the test's simulated_projector marker or the module's VALUES, else
    default_power, any power state if that is None. Other values only come from the marker.
    """
    marker = request.node.get_closest_marker("simulated_projector")
    marker_values: dict[str, str] = (
        dict(marker.kwargs.get("values", {})) if marker else {}
    )
    module_values: dict[str, str] = getattr(request.module, "VALUES", {})

    power = marker_values.pop("pow", module_values.get("pow", default_power))
    power = power.lower() if power is not None else None
    if power == "on" and projector.power_status not in (
        BenQProjector.POWERSTATUS_ON,
        BenQProjector.POWERSTATUS_POWERINGON,
    ):
        pytest.skip("Needs the projector on")
    if power == "off" and projector.power_status not in (
        BenQProjector.POWERSTATUS_OFF,
        BenQProjector.POWERSTATUS_POWERINGOFF,
    ):
        pytest.skip("Needs the projector off")

    for command, value in marker_values.items():
        actual = await projector.send_command(command)
        if actual is None or actual.lower() != value.lower():
            pytest.skip(f"Needs {command} to be {value.lower()}, it is {actual}")


# Any projector, simulated or real


@pytest.fixture
def hardware(request: pytest.FixtureRequest) -> bool:
    """Whether the tests run against a real projector, with --hardware."""
    return request.config.getoption("--hardware") is not None


def _hardware_url(request: pytest.FixtureRequest, transport: str) -> str:
    """The url of the real projector, the test is skipped if it is of another transport."""
    url: str = request.config.getoption("--hardware")
    if (transport == "network") != url.startswith(NETWORK_URL_SCHEMES):
        pytest.skip(f"Runs over a {transport} connection, the --hardware url is not")
    return url


def _hardware_baud_rate(request: pytest.FixtureRequest, url: str) -> int:
    """The baud rate for the real projector, only used on a serial port."""
    if url.startswith(NETWORK_URL_SCHEMES):
        return BAUD_RATES[0]
    return int(request.config.getoption("--baud-rate"))


@pytest.fixture
async def connected_projector(
    request: pytest.FixtureRequest, hardware: bool
) -> AsyncIterator[BenQProjectorSerial]:
    """A connected BenQ projector, with and without a command prompt.

    Without --hardware the projector is simulated: of the test module's MODEL, with its VALUES
    and OPTIONS, like `projector_simulation`, once with and once without a prompt, see
    pytest_generate_tests. With --hardware it is the real projector at the --hardware url. The
    projector is disconnected at the end of the test.
    """
    if hardware:
        url = request.config.getoption("--hardware")
        projector = BenQProjectorSerial(url, _hardware_baud_rate(request, url))
        try:
            assert await projector.connect(), (
                f"Unable to connect to the projector on {url}"
            )
            # Only the power state the test asks for with its marker
            await _check_state(request, projector, default_power=None)
        except BaseException:
            await projector.disconnect()
            raise
    else:
        url = await serial_simulation()
        _create_simulation(request, url, {"prompt": request.param == "prompt"})
        projector = BenQProjectorSerial(url, 9600)

    assert await projector.connect()
    yield projector
    await projector.disconnect()


# Examining a projector

# The configuration key of the modes of a command, and the command
MODE_COMMANDS = {
    "video_sources": "sour",
    "audio_sources": "audiosour",
    "picture_modes": "appmod",
    "color_temperatures": "ct",
    "aspect_ratios": "asp",
    "projector_positions": "pp",
    "lamp_modes": "lampm",
    "3d_modes": "3d",
    "menu_positions": "menuposition",
}


def remove_examine_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let BenQProjectorExamine skip its pauses, a simulated projector doesn't need them."""
    sleep = asyncio.sleep

    async def no_wait(_delay: float) -> None:
        await sleep(0)

    monkeypatch.setattr(benqexamine, "asyncio", types.SimpleNamespace(sleep=no_wait))


@pytest.fixture
def examine(
    projector: BenQProjectorSerial, hardware: bool, monkeypatch: pytest.MonkeyPatch
) -> BenQProjectorExamine:
    """An examiner of the projector, without pauses if simulated. Connect the projector first."""
    if not hardware:
        remove_examine_pauses(monkeypatch)
    return BenQProjectorExamine(projector)


# Modes a projector refuses without a picture on its input
PICTURE_MODES = ("picture_modes", "color_temperatures", "aspect_ratios", "3d_modes")
NO_PICTURE = "is there a picture on the projector's input?"


async def assert_examine(
    projector: BenQProjectorSerial,
    examine: BenQProjectorExamine,
    expected: dict[str, set[str]],
) -> None:
    """Connect the projector, examine it and check the detected features, see expected_features."""
    assert await projector.connect()

    features = await examine.detect_projector_features()
    assert features is not None
    detected = {key: set(value) for key, value in features.items()}
    missing = [
        key for key in PICTURE_MODES if expected.get(key) and not detected.get(key)
    ]
    assert not missing, f"No {', '.join(missing)} detected, {NO_PICTURE}"
    assert detected == expected


def expected_features(
    model: str | None = None, commands: set[str] | None = None
) -> dict[str, set[str]]:
    """What BenQProjectorExamine detects on a simulated projector.

    For a model with a configuration file these are the commands and modes in it which examine
    tries, those in all.json, except for the commands it ignores. For a model without one, give
    the commands it supports, it supports no modes.
    """
    known = read_model_config("all")
    config = read_model_config(model)
    if commands is None:
        commands = set(config.get("commands", []))
    commands = commands & set(known["commands"]) - set(IGNORE_COMMANDS)

    features: dict[str, set[str]] = {"commands": commands}
    for key, command in MODE_COMMANDS.items():
        if command in commands:
            features[key] = set(config.get(key) or []) & set(known.get(key) or [])
        else:
            features[key] = set()
    return features


# Setting changed settings back

type RestoreSettings = Callable[..., Awaitable[None]]


@pytest.fixture
async def restore_settings() -> AsyncIterator[RestoreSettings]:
    """Remember settings of a projector, and set them back at the end of the test.

    `await restore_settings(projector, "vol", "mute")` reads the settings exactly as the
    projector reports them. After the test they are set back in reverse order, the volume with
    volume_level(). The test fails when a setting can't be set back. Request this fixture after
    the projector's fixture, so the settings are set back before the projector disconnects.
    """
    remembered: list[tuple[BenQProjectorSerial, str, str]] = []

    async def remember(projector: BenQProjectorSerial, *commands: str) -> None:
        for command in commands:
            try:
                value = await projector._send_command(
                    BenQCommand(command), lowercase_response=False
                )
            except BenQProjectorError:
                value = None
            if value is not None:
                remembered.append((projector, command, value))

    yield remember

    failed = [
        f"{command}={value}"
        for projector, command, value in reversed(remembered)
        if not await _restore_setting(projector, command, value)
    ]
    assert not failed, f"Unable to set back {', '.join(failed)}"


async def _restore_setting(
    projector: BenQProjectorSerial, command: str, value: str
) -> bool:
    """Set a setting back to the value the projector reported."""
    if command == "vol":
        # Some projectors only accept volume steps, volume_level() handles that
        await projector.update_volume()
        return await projector.volume_level(int(value))
    try:
        response = await projector._send_command(
            BenQCommand(command, value), lowercase_response=False
        )
    except BenQProjectorError:
        return False
    return response is not None and response.lower() == value.lower()
