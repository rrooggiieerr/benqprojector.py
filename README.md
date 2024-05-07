# Python library to control BenQ projectors

![Python][python-shield]
[![GitHub Release][releases-shield]][releases]
[![Licence][license-shield]][license]
[![Maintainer][maintainer-shield]][maintainer]  
[![Github Sponsors][github-shield]][github]
[![PayPal][paypal-shield]][paypal]
[![BuyMeCoffee][buymecoffee-shield]][buymecoffee]
[![Patreon][patreon-shield]][patreon]

## Introduction

Python library to control BenQ projectors over the serial interface or serial to network bridges
like [esp-link](https://github.com/jeelabs/esp-link).

BenQ projectors and flat panels with a serial port can support one of three protocols. This plugin
supports projectors which are of the L, P, T, W and X series but probably also others.

## Features

## Hardware

## Protocol

This Python library works if your projector supports the following command structure: 

`<CR>*<key>=<value>#<CR>`

Where `<CR>` is a Carriage Return

Examples:  
Power on   : `<CR>*pow=on#<CR>`  
Power off  : `<CR>*pow=off#<CR>`  
Change source to HDMI: `<CR>*sour=hdmi#<CR>`  

### Serial port

You can lookup and change the baud rate in the menu of your BenQ projector.

### Network connected projectors

The commands as described above should also work over a network connection, however I don't own
such projector and have implemented the network functionality using a serial to network bridge. The
network support for native networked BenQ projectors is thus experimental. Let me know if your
network connected BenQ projector works.

Example of a serial to network bridge using a serial to TTL converter and a Wemos C3 Mini:

<img src="https://raw.githubusercontent.com/rrooggiieerr/benqprojector.py/main/serial%20to%20network%20bridge.png">

It has to be said that a direct serial connection to the projector is much more responsive than
using a network connection, at least when using a serial to network bridge. Maybe this is different
on a native networked BenQ projector or using ethernet instead of WiFi.

### PJLink

This library does **not** implement the PJLink protocol, but a proparitary BenQ protocol instead.
The PJLink protocol is covered by other libraries.

## Supported projectors

The following projectors are known to work:

* MW519
* TH585
* W1070
* W1100
* W1110
* X3000i

The following projectors are not tested but use the same protocol according to the documentation:

Others in the L, P, T, W and X Series

Not supported:

* RP552
* RP552H
* RP840G
* RP653
* RP703
* RP750
* RP750K
* RP652
* RP702
* RP790S
* RP705H

Some projectors need to be **on** to be able to detect the model and the library to work.

Please let me know if your projector is also supported by this Python library so I can improve the
overview of supported projectors.

## Installation

To install the Python BenQ projector library use the Python package manager PIP:

`pip3 install benqprojector`

## `benqprojector` CLI

You can use the Python BenQ projector library directly from the command line to turn on and off
your projector using the following syntax:

Status of the projector: `python3 -m benqprojector serial <serial port> <baud> status`  
Turn on the projector: `python3 -m benqprojector serial <serial port> <baud> on`  
Turn off the projector: `python3 -m benqprojector serial <serial port> <baud> off`

Or if your projector is connected using a serial to network bridge:

Status of the projector: `python3 -m benqprojector telnet <host> <port> status`  
Turn on the projector: `python3 -m benqprojector telnet <host> <port> on`  
Turn off the projector: `python3 -m benqprojector telnet <host> <port> off`

### Detecting your projector capabilities

The benqprojector CLI can detect the commands, sources and modes your projector supports. If you
like to have your projector fully supported by this Python library please run this command and
create an issue on Github with the output attached.

To examine your projector capabilities:

`python3 -m benqprojector serial <serial port> <baud> examine`

Your projector needs to be **on** and on an **active source** to be able to detect all your
projector capabilities.

### Troubleshooting

You can add the `--debug` flag to any CLI command to get a more details on what's going on. Like so:

`python3 -m benqprojector serial <serial port> <baud> status --debug`

## Support my work

Do you enjoy using this Python library? Then consider supporting my work using one of the following
platforms, your donation is greatly appreciated and keeps me motivated:

[![Github Sponsors][github-shield]][github]
[![PayPal][paypal-shield]][paypal]
[![BuyMeCoffee][buymecoffee-shield]][buymecoffee]
[![Patreon][patreon-shield]][patreon]

## Hire me

If you're in need for a freelance Python developer for your project please contact me, you can find
my email address on [my GitHub profile](https://github.com/rrooggiieerr).

---

[python-shield]: https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54
[releases]: https://github.com/rrooggiieerr/benqprojector.py/releases
[releases-shield]: https://img.shields.io/github/v/release/rrooggiieerr/benqprojector.py?style=for-the-badge
[license]: ./LICENSE
[license-shield]: https://img.shields.io/github/license/rrooggiieerr/benqprojector.py?style=for-the-badge
[maintainer]: https://github.com/rrooggiieerr
[maintainer-shield]: https://img.shields.io/badge/MAINTAINER-%40rrooggiieerr-41BDF5?style=for-the-badge
[paypal]: https://paypal.me/seekingtheedge
[paypal-shield]: https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white
[buymecoffee]: https://www.buymeacoffee.com/rrooggiieerr
[buymecoffee-shield]: https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black
[github]: https://github.com/sponsors/rrooggiieerr
[github-shield]: https://img.shields.io/badge/sponsor-30363D?style=for-the-badge&logo=GitHub-Sponsors&logoColor=ea4aaa
[patreon]: https://www.patreon.com/seekingtheedge/creators
[patreon-shield]: https://img.shields.io/badge/Patreon-F96854?style=for-the-badge&logo=patreon&logoColor=white
