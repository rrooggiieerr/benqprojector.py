"""
Implements the BenQ projector library for controlling BenQ projector over the serial interface.

Created on 27 Nov 2022

@author: Rogier van Staveren
"""

try:
    from ._version import __version__
except ModuleNotFoundError:
    pass
from .benqprojector import (
    BAUD_RATES,
    DEFAULT_PORT,
    BenQProjector,
    BenQProjectorSerial,
    BenQProjectorTelnet,
)
