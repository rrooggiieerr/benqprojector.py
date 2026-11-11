"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import logging

import pytest

from benqprojector.benqconnection import BenQTelnetConnection

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.hardware


@pytest.fixture
async def connection(telnet_host):
    connection = BenQTelnetConnection(telnet_host)
    yield connection
    await connection.close()


async def test_open(connection):
    result = await connection.open()
    assert result
    assert connection.is_open()


async def test_close(connection):
    await connection.open()
    result = await connection.close()
    assert result
    assert not connection.is_open()


async def test_read(connection):
    await connection.open()
    await connection.write(b"\r")
    result = await connection.read(1)
    logger.debug(result)
    assert result is not None


async def test_readline(connection):
    await connection.open()
    await connection.write(b"\r")
    result = await connection.readline()
    logger.debug(result)
    assert result is not None


async def test_write(connection):
    await connection.open()
    await connection.write(b"\r*pow=?#\r")
    await connection.readline()
    result = await connection.readline()
    assert result.startswith(b"*POW=")
