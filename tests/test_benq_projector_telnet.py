"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import pytest

from benqprojector import BenQCommand, BenQProjectorTelnet

pytestmark = pytest.mark.hardware


@pytest.fixture
async def projector(telnet_host):
    projector = BenQProjectorTelnet(telnet_host, has_prompt=True)
    yield projector
    await projector.disconnect()


async def test__connect(projector):
    result = await projector._connect()
    assert result


async def test__detect_prompt(projector):
    await projector._connect()
    result = await projector._detect_prompt()
    assert result


async def test__wait_for_prompt(projector):
    await projector._connect()
    result = await projector._wait_for_prompt()
    assert result


async def test__send_command(projector):
    projector.has_prompt = True
    await projector._connect()
    result = await projector._send_command(BenQCommand("pow"))
    assert result


async def test_send_command(projector):
    projector.has_prompt = True
    await projector._connect()
    result = await projector.send_command("pow")
    assert result == "off"


async def test_send_raw_command(projector):
    projector.has_prompt = True
    await projector._connect()
    result = await projector.send_raw_command("*pow=?#")
    assert result == "*POW=OFF#"
