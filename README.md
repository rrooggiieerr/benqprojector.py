# Python library to control BenQ projectors

Python library to control BenQ projectors over the serial interface or serial
to network bridges like esp-link.

BenQ projectors and flat pannels with a serial port can support one of three
protocols. This plugin supports projectors which are of the L, P, T, W and X
series but probably also others.

## Protocol

This are the protocol details:

2400 baud 8N1

```
<CR>*<key>=<value>#<CR>
```

Where `<CR>` is a Carriage Return

Examples:  
Power on   : `<CR>*pow=on#<CR>`  
Power off  : `<CR>*pow=off#<CR>`  
Source HDMI: `<CR>*sour=hdmi#<CR>`  

## Network connected projectors

The commands as descrived above should also work over a network connection,
however I don't own such projector and have implemented the network
functionality using a serial to network bridge. The network support for native
networked BenQ projectors is thus experimental. Let me know if your network
connected BenQ projector works.

Example of a serial to network bridge using a serial to TTL converter and a
Wemos C3 Mini  
<img src="https://raw.githubusercontent.com/rrooggiieerr/benqprojector.py/main/serial%20to%20network%20bridge.png"/>

It has to be said that a direct serial conection to the projector is much more
responsive than using a network connection, at least when using a serial to
network bridge. Maybe this is different on a native networked BenQ projector or
using ethernet instead of WiFi.

### PJLink

This library does **not** implement the PJLink protocol, but a proparitary
BenQ protocol instead. The PJLink protocol is covered by other libraries.

## Supported projectors

Known to work:
* W1070
* W1100
* W1110
* X3000i

Not tested but use te same protocol according to the documentation:
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

Please let me know if your projector is also supported by this plugin so I
can improve the overview of supported devices.

## Installation
You can install the Python BenQ projector library using the Python package
manager PIP:
`pip3 install benqprojector`

## benqprojector CLI
You can use the Python BenQ projector library directly from the command line
to turn on and off your projector using the following syntax:

Status of the projector: `python3 -m benqprojector serial <serial port> <baud> status`  
Turn on the projector: `python3 -m benqprojector serial <serial port> <baud> on`  
Turn off the projector: `python3 -m benqprojector serial <serial port> <baud> off`

Or if your projector is connected using a serial to network bridge:

Status of the projector: `python3 -m benqprojector telnet <host> <port> status`  
Turn on the projector: `python3 -m benqprojector telnet <host> <port> on`  
Turn off the projector: `python3 -m benqprojector telnet <host> <port> off`

### Detecting your projector capabilities
The benqprojector CLI can detect the commands, sources and modes your
projector supports. If you like to have your projector fully supported by this
Python library please run this command and create an issue on Github with the
output attached.

To examine your projector capabilities: `python3 -m benqprojector serial <serial port> <baud> examine`

Your projector needs to be on to be able to detact all your projector
capabilities.

Do you enjoy using this Python library? Then consider supporting my work:  
[<img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" >](https://www.buymeacoffee.com/rrooggiieerr)
