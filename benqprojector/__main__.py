"""
Created on 27 Nov 2022

@author: Rogier van Staveren
"""

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from serial.serialutil import SerialException

from benqprojector import BenQProjector, BenQProjectorSerial, BenQProjectorTelnet

_LOGGER = logging.getLogger(__name__)


def _listener(command: str, data: Any):
    _LOGGER.info("%s %s", command, data)


async def main(projector: BenQProjector, action: str):
    if not await projector.connect():
        _LOGGER.error("Failed to connect to BenQ projector")
        sys.exit(1)

    try:
        if action == "status":
            await projector.update()

            _LOGGER.info("Model: %s", projector.model)
            _LOGGER.info("Position: %s", projector.projector_position)
            if projector.power_status == projector.POWERSTATUS_OFF:
                _LOGGER.info("Power off")
            else:
                _LOGGER.info("Power on")

            _LOGGER.info("Direct power on  : %s", projector.direct_power_on)

            if projector.lamp2_time is not None:
                _LOGGER.info("Lamp 1 time      : %s hours", projector.lamp_time)
                _LOGGER.info("Lamp 2 time      : %s hours", projector.lamp2_time)
            else:
                _LOGGER.info("Lamp time        : %s hours", projector.lamp_time)

            if projector.power_status == projector.POWERSTATUS_ON:
                _LOGGER.info("3D               : %s", projector.threed_mode)
                _LOGGER.info("Picture mode     : %s", projector.picture_mode)
                _LOGGER.info("Aspect ratio     : %s", projector.aspect_ratio)
                _LOGGER.info("Brilliant color  : %s", projector.brilliant_color)
                _LOGGER.info("Blank            : %s", projector.blank)
                _LOGGER.info("Brightness       : %s", projector.brightness)
                _LOGGER.info("Color value      : %s", projector.color_value)
                _LOGGER.info("Contrast         : %s", projector.contrast)
                _LOGGER.info("Color temperature: %s", projector.color_temperature)
                _LOGGER.info("High altitude    : %s", projector.high_altitude)
                _LOGGER.info("Lamp mode        : %s", projector.lamp_mode)
                _LOGGER.info("Quick auto search: %s", projector.quick_auto_search)
                _LOGGER.info("Sharpness        : %s", projector.sharpness)
                _LOGGER.info("Video Source     : %s", projector.video_source)
                _LOGGER.info("Volume           : %s", projector.volume)
                _LOGGER.info("Muted            : %s", projector.muted)

            _LOGGER.info("Supported video sources: %s", projector.video_sources)
        elif action == "on":
            if await projector.turn_on():
                pass
        elif action == "off":
            if await projector.turn_off():
                pass
        elif action == "monitor":
            projector.add_listener(_listener)

            while True:
                await asyncio.sleep(1)
        elif action == "examine":
            _LOGGER.info("Model: %s", projector.model)
            if projector.power_status == projector.POWERSTATUS_OFF:
                _LOGGER.error("Projector needs to be on to examine it's features.")
                sys.exit(1)

            config = await projector.detect_projector_features()

            _LOGGER.info("Projector configuration JSON:")
            _LOGGER.info(json.dumps(config, indent="\t"))
    except SerialException as e:
        _LOGGER.error("Failed to connect to BenQ projector, reason: %s", e)
        sys.exit(1)
    finally:
        _LOGGER.info("Disconnecting from BenQ projector")
        await projector.disconnect()


if __name__ == "__main__":
    # Read command line arguments
    argparser = argparse.ArgumentParser()

    subparsers = argparser.add_subparsers()

    serial_parser = subparsers.add_parser("serial")
    serial_parser.add_argument("serial_port")
    serial_parser.add_argument("baud", type=int)

    telnet_parser = subparsers.add_parser("telnet")
    telnet_parser.add_argument("host")
    telnet_parser.add_argument("port", type=int)

    argparser.add_argument(
        "action", choices=["status", "on", "off", "monitor", "examine"]
    )
    argparser.add_argument("--wait", dest="wait", action="store_true")
    argparser.add_argument("--debug", dest="debugLogging", action="store_true")

    args = argparser.parse_args()

    if args.debugLogging:
        logging.basicConfig(
            format="%(asctime)s %(levelname)-8s %(filename)s:%(lineno)d %(message)s",
            level=logging.DEBUG,
        )
    else:
        logging.basicConfig(format="%(message)s", level=logging.INFO)

    if "serial_port" in args:
        projector = BenQProjectorSerial(args.serial_port, args.baud)
    elif "host" in args:
        projector = BenQProjectorTelnet(args.host, args.port)

    loop = asyncio.new_event_loop()

    try:
        asyncio.run(main(projector, args.action))
    except KeyboardInterrupt:
        # Handle keyboard interrupt
        pass
    finally:
        loop.close()

    sys.exit(0)
