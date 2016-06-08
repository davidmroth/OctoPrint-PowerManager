# OctoPrint-PowerManager

Power Management - This OctoPrint Plugin will automatically power down your 3D printer after a configurable amount of inactivity.

The plugin works in conjunction with an appliance control/relay that is controlled via the GPIO pins on a Raspberry Pi


## Setup

Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager)
or manually using this URL:

    https://github.com/davidmroth/OctoPrint-PowerManager/archive/master.zip


## Configuration

Idle Timeout (Minutes) - Amount of idle time before shutting down power to the AC Relay/3D Printer
3D Printer Power Commands - Commandline parameters to enable and disable AC relay using GPIO Pins (may need to be modified if using differnt GPIO pins)
