# Instructions for AI agents: writing tests

These instructions are for an AI agent that writes tests for this library. Most tests are for
one projector model, in `tests/test_<model>.py`, e.g. `tests/test_w1100.py`. Read
[quirks.md](../quirks.md) first: it describes how models differ from BenQ's specification, and
those differences are what the model tests are about.

## 1. Where the tests go

| File | Tests |
| --- | --- |
| `test_<model>.py` | How one model behaves, especially where it doesn't follow the specification |
| `test_benq_projector.py` | Behaviour every projector shares: commands, source, volume, menu |
| `test_benq_projector_examine.py` | Detecting the commands and modes a projector supports |
| `test_benq_projector_prompt.py` | Detecting the command prompt |
| `test_benq_projector_parse_responses.py` | Parsing responses and errors, without a projector |
| `test_benq_serial_connection*.py` | The connection class |

Shared fixtures are in `conftest.py`, the simulated projector and connections in
`simulation.py`. Don't repeat generic behaviour in a model test.

## 2. Decide what to test for a model

A model test covers what the model does differently. Base it on what has been seen on a real
projector: an issue in [benqprojector.py](https://github.com/rrooggiieerr/benqprojector.py/issues)
or [homeassistant-benqprojector](https://github.com/rrooggiieerr/homeassistant-benqprojector/issues),
a pull request, a log or a capture. Don't invent quirks. Use the exact bytes from the source
where it has them, including line endings, prompts and null bytes.

| Seen on the projector | Simulate with |
| --- | --- |
| A prompt, or none | `prompt`, by default only on a serial connection |
| No prompt to an empty line in some power state | `empty_line_prompt={"on": False, "off": True}` |
| Something else than `>` as prompt, e.g. `>\x00` | `prompt_response`, and `echo_prefix` when the echo doesn't start with it |
| No echo, or an empty line instead | `echo=False`, `echo=b"\r\n"` |
| A response ending differently, e.g. `#\r` or `#` only | `line_ending` |
| A command refused, always or in a power state | `blocked={"modelname"}`, `blocked={"off": {"*pow=?#"}}` |
| A response that doesn't follow the format | `raw_responses={"*ltim=?#": b"..."}`, or per power state `{"on": ..., "off": ...}`. A raw response replaces the echo and the answer |
| The first byte dropped after a pause | `drop_first_byte`, `idle_time` |
| Slow answers | `delay` |
| Behaviour that depends on earlier commands or on time | A subclass of `SimulatedProjector` with its own `answer()`, set as `PROJECTOR_CLASS` |

A model with a configuration file in `benqprojector/configs` supports exactly the commands and
modes in it, and refuses other modes with `*Illegal format#`. A model without one only supports
`pow`, `modelname` and the commands in `VALUES`.

## 3. Write the test file

Start with a docstring that names the model, summarises what is particular about it and says
where it was seen, with the captured bytes. Then the module settings:

```python
"""Tests for the BenQ W4100i projector on a serial to network bridge.

The W4100i ends its answers with \\r only. ...

Captured in homeassistant-benqprojector issue #64:

    *pow=?#\\r  ->  >*pow=?#\\r\\r\\n*POW=ON#\\r
"""

MODEL = "W4100i"
VALUES = {"pow": "OFF"}
OPTIONS = {"prompt": True, "line_ending": b"\r"}
```

- `MODEL` is the model name as the projector reports it, with its configuration file if it has
  one.
- `VALUES` are the values the simulated projector starts with, as it sends them: `"ON"`,
  `"HDMI"`, `"1000"`. Other commands get a default: on, the first mode, `0` or `OFF`.
- `OPTIONS` are keyword arguments of `SimulatedProjector`, see section 2.
- A model on a network connection sets
  `pytestmark = pytest.mark.parametrize("url", ["network"], indirect=True)`. Use
  `@both_transports` from `simulation.py` when a test should run over both.

Change the simulated projector for one test with the marker, values are added to `VALUES`:

```python
@pytest.mark.simulated_projector(values={"pow": "ON"})
```

Every test has a docstring that says what the projector does, not how the test works.

## 4. Fixtures

| Fixture | For |
| --- | --- |
| `projector` | A `BenQProjectorSerial` of the module's model. Call `await projector.connect()` in the test |
| `projector_simulation` | The `SimulatedProjector`, to look inside it: `get()`, `unplug()`, `plug()`, `commands`, `received`, `power` |
| `examine` | A `BenQProjectorExamine` of the projector, without its pauses on a simulated projector |
| `hardware` | Whether the tests run against a real projector |
| `connected_projector` | A connected projector, simulated with and without a prompt, for `test_benq_projector*.py` |
| `restore_settings` | Sets settings a test changes back afterwards, see section 5 |

Helpers in `conftest.py`: `expected_features(MODEL)` gives what examine detects on a simulated
model with a configuration file, `expected_features(commands={...})` on one without.
`assert_examine()` connects the projector, examines it and compares the result.

Add a `test_examine` to every model test file:

```python
async def test_examine(projector: BenQProjectorSerial, examine: BenQProjectorExamine) -> None:
    """Examining finds the commands and modes of the configuration."""
    await assert_examine(projector, examine, expected_features(MODEL))
```

## 5. Real projectors

`pytest tests/test_<model>.py --hardware <url>` runs the model tests against a real projector
at a serial port or a network url, like `socket://host:8000`. The projector is expected to be on
with a picture on its input, as it refuses settings like the picture mode without a signal, so
results are compared exactly also on a real projector. Write the tests so they can:

- Test through the public API: `connect()`, `send_command()`, `turn_on()`,
  `select_video_source()` and so on. Use a private method only to check something the API
  hides, e.g. `_send_command()` for the exception of a refused command.
- Request `projector_simulation` only when the test looks inside the simulated projector. Those
  tests are skipped on a real projector. A test that turns the projector on or off must request
  it, so a real projector is never switched.
- Say the state a test needs with the marker: with `values={"pow": "OFF"}` the test is skipped
  when the real projector is on. Other marker values, e.g. `directpower`, are read from the
  projector the same way. The power state comes from `VALUES` when the marker doesn't give it.
- Assert values that come from `VALUES` only against the simulated projector:

  ```python
  lamp_time = await projector.send_command("ltim")
  assert lamp_time.isdigit()
  if not hardware:
      assert lamp_time == "1386"
  ```
- A generic test of a command that not every model has skips when the projector doesn't
  support it: `if not projector.supports_command("menu"): pytest.skip(...)`.
- Set back every setting a test changes, so a real projector is left as it was. Request
  `restore_settings` after the projector fixture and call it with the settings before changing
  them. It reads them as the projector reports them and sets them back after the test; the test
  fails when one can't be set back:

  ```python
  async def test_mute(
      connected_projector: BenQProjectorSerial, restore_settings: RestoreSettings
  ) -> None:
      """The projector is muted."""
      await restore_settings(connected_projector, "vol", "mute")
      ...
  ```

  Import the type with `from .conftest import RestoreSettings`. Close a menu the test opened
  yourself, it isn't a setting.

## 6. Known problems

When the library doesn't handle what the projector does, still write the test for the right
behaviour and mark it, with the issue or pull request:

```python
@pytest.mark.xfail(strict=True, reason="homeassistant-benqprojector#64: W4100i standby behaviour")
```

`strict=True` makes the test fail once the library is fixed, so the marker gets removed. Test
the behaviour the users need, not how a proposed fix works.

Don't change the library or a configuration file to make a test pass: report it to the user.

## 7. Validate

1. Run `pytest tests/test_<model>.py`, and `pytest` for all tests.
2. Run `pre-commit run --all-files` to format and check the files.
3. When a test fails unexpectedly, check whether the test, the simulation or the library is
   wrong. A strict xfail that passes means the problem is fixed.
4. When the model shows a kind of quirk [quirks.md](../quirks.md) doesn't have yet, add it with
   the model as example and a link to where it was seen. Don't list every model.

## 8. Report back

Summarise for the user:

- what you tested for the model, what you left out, and why;
- which tests are expected to fail, and what the library would need to make them pass;
- anything in the configuration file or `quirks.md` that looks wrong.
