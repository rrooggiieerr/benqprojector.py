# Python library to control BenQ projectors

Python library to control BenQ projectors over the serial interface.

The same commands should work over a network connection, but I don't own such
projector and have not implemented any network functionality. Contact me if
you have a network connected BenQ projector and like this to work.

BenQ projectors and flat pannels with a serial port can support one of three
protocols. This plugin supports projectors which are of the P series but
probably also others.

## Protocol

This are the protocol details:

2400 baud 8N1

```
<CR>*<key>=<value>#<CR>
```

Where `<CR>` is a Cariage Return

Examples:  
Power on   : `<CR>*pow=on#<CR>`  
Power off  : `<CR>*pow=off#<CR>`  
Source HDMI: `<CR>*sour=hdmi#<CR>`  

## Supported projectors

Known to work:
W1110

Not tested but use te same protocol according to the documentation:  
Others in the P Series

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

Please let me know if your projectors is also supported by this plugin so I
can improve the overview of supported devices.

## Installation
You can install the Python BenQ projector library using the Python package
manager PIP:  
`pip3 install benqprojector`

## benqprojector CLI
You can use the Python BenQ projector library directly from the command line
to turn on and off your projector using the following syntax:

Status of the projector: `python3 -m benqprojector <serial port> status`  
Turn on the projector: `python3 -m benqprojector <serial port> on`  
Turn off the projector: `python3 -m benqprojector <serial port> off`