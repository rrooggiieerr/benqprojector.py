"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import asyncio

import pytest

from benqprojector import BenQProjectorSerial

pytestmark = pytest.mark.hardware

DELAY = 0.2


@pytest.fixture
async def projector(serial_port, baud_rate):
    projector = BenQProjectorSerial(serial_port, baud_rate)
    await projector.connect()
    await projector.send_command("menu", "off")
    await asyncio.sleep(DELAY)
    yield projector
    await asyncio.sleep(DELAY)
    await projector.send_command("menu", "off")
    await asyncio.sleep(DELAY)
    await projector.disconnect()


async def test_menu_off_status(projector):
    # Fails on w1110 but should work on other projectors
    response = await projector.send_command("menu", "?")
    await asyncio.sleep(DELAY)
    assert response == "off"


async def test_menu_on_status(projector):
    # Fails on w1110 but should work on other projectors
    await projector.send_command("menu", "on")
    await asyncio.sleep(DELAY)
    response = await projector.send_command("menu", "?")
    await asyncio.sleep(DELAY)
    assert response == "on"


async def test_menu_on(projector):
    response = await projector.send_command("menu", "on")
    assert response == "on"


async def test_menu_off(projector):
    await projector.send_command("menu", "on")
    await asyncio.sleep(DELAY)
    response = await projector.send_command("menu", "off")
    assert response == "off"


@pytest.mark.parametrize(
    ("setup_command", "command"),
    [
        ("*down#", "*up#"),
        (None, "*down#"),
        ("*right#", "*left#"),
        (None, "*right#"),
    ],
    ids=["up", "down", "left", "right"],
)
async def test_menu_navigation(projector, setup_command, command):
    await projector.send_command("menu", "on")
    await asyncio.sleep(DELAY)
    if setup_command:
        await projector.send_raw_command(setup_command)
        await asyncio.sleep(DELAY)
    response = await projector.send_raw_command(command)
    assert response is not None
    assert response.lower() == command
