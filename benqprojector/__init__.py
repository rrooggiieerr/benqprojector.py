"""
Implements the BenQ projector library for controlling BenQ projector over the serial interface.

Created on 27 Nov 2022

@author: Rogier van Staveren
"""
__version__ = "0.0.13.4"

from benqprojector.benqprojector import (
    BAUD_RATES,
    BenQProjector,
    BenQProjectorSerial,
    BenQProjectorTelnet,
)
