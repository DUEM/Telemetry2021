"""Serial port helpers for LiveTelemetry: list the serial ports, and suggest
which one is most likely the XBee.

Nothing here asks the user anything: LiveTelemetry prints the list before its
Serial port question and, if the default port from config.yml is not plugged
in, suggests one.

From Ben Jennery's PERI-DEVELOPMENT-BBJ-1126 branch (commit aafbfee). Its
serial.env file of saved settings is not used: the receiver saves the serial
port with its other last used settings in .env (see LiveTelemetry.py), and
the baud rate is serialBaud in config.yml.
"""
from serial.tools import list_ports

# The baud rate of the XBee (BD=7) and the telemetry board's XBee serial link
DEFAULT_BAUD = 115200

# USB serial chips XBee boards and adapters use. FTDI (0x0403) is on the
# XBee Explorer / Digi XBIB boards.
FTDI_VID = 0x0403


def list_serial_ports():
    """The serial ports on this computer (list_ports ListPortInfo), by name."""
    return sorted(list_ports.comports(), key=lambda p: p.device)


def describe_port(p):
    extra = [x for x in (p.description, p.manufacturer) if x and x != "n/a"]
    return f"{p.device}  ({', '.join(extra)})" if extra else p.device


def suggest_port(ports, saved_port=None):
    """Return (port, reason) for the port most likely to be the XBee.

    The saved port if it is plugged in, then an FTDI device, then any USB
    serial device. (None, None) if there is none.
    """
    for p in ports:
        if p.device == saved_port:
            return p.device, "last used"
    for p in ports:
        if p.vid == FTDI_VID:
            return p.device, "FTDI USB serial, probably the XBee"
    for p in ports:
        if p.vid is not None or "usb" in p.device.lower():
            return p.device, "USB serial"
    return None, None
