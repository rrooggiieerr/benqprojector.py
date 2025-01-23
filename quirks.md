# BenQ projector quirks

During the development of this Python library for BenQ projectors I learned that the folks at BenQ are not very strict with following their own interface specifications. This document documents the findings made while developing and using the library.

## Command prompt

Connections using the serial port use a command prompt `>` while connections using the integrated network interface don't use a command prompt.

## Command echo

Some models don't echo the command, like the **X3000i** which returns an empty line.

The **W1100** echos the `*bri=?#` command twice while echoing the other commands once, as it should.

## Invalid command response

Some models don't follow the `*<key>=<value>#` response format for all commands or the format differs if the projector is on versus off. For instance the **W1110** returns `DIRECTPOWER=OFF#` instead of `*DIRECTPOWER=OFF#` when the projector is off but the expected `*DIRECTPOWER=OFF#` if the projector is on.

## Model name

Some projectors do not support the modelname command, the **W1000** for instance returns `*Illegal format#` instead.

Not all projector models return the modelname when the projector is turned off. The **W1070/W1250** returns `*Block item#`.

The **W2000** returns a different modelname when the projector is turned off then when the projector is turned on. I returns `W1110` when turned off and `W2000` when turned on.

Some projectors only return the model name withouth the modelname command prefixed. **W700** returns `#W700` instead of the expected `#MODELNAME=W700*`.

## Miscellaneous 

The **W1100** `ltim`, `bri`, `con`, `color` and `sharp` command response does include spaces and does not end with `#`. `*LTIM= 1383` returns instead of the expected `*LTIM=1383#`. Similar for the other commands.