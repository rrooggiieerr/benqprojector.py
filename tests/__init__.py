"""
Tests for the BenQ projector library.

The tests run against a simulated projector on a simulated serial or network connection, see
simulation.py. With ``--hardware <url>`` they run against the real projector at that url
instead, a serial port or a network address like socket://host:port. The baud rate is only used
for a serial port:

    pytest --hardware /dev/tty.usbserial-10 --baud-rate 115200
    pytest --hardware socket://benqprojector-livingroom.local:8000

The tests in test_benq_projector*.py work on any projector. The tests of a specific model are in
test_<model>.py, with ``--hardware`` run only the file of the model of the real projector:

    pytest tests/test_w1110.py --hardware /dev/tty.usbserial-10

Against a real projector a test only runs when the projector is in the state the test needs,
e.g. on, and it sets the settings it changes back afterwards. Most tests need the projector on,
with a picture on its input: without a signal a projector refuses settings like the picture
mode, color temperature, aspect ratio and 3D mode, and examining it doesn't find their modes. Tests which look inside the
simulated projector only run against the simulated projector.

AGENTS.md describes how to write the tests, quirks.md how the models differ.
"""
