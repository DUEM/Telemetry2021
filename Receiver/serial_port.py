"""Serial port helpers for LiveTelemetry: list the ports, suggest one, and
remember the one used.

Nothing here asks the user anything: LiveTelemetry prints the list, asks
"Would you like to use <suggestion>?" and saves what was chosen.

The port and baud rate used are saved in serial.env next to this file, which
is not committed because the port name differs between laptops.
"""
import os
from pathlib import Path

from serial.tools import list_ports

DEFAULT_BAUD = 115200
SETTINGS_FILE = Path(__file__).parent / "serial.env"

# USB serial chips XBee boards and adapters use. FTDI (0x0403) is on the
# XBee Explorer / Digi XBIB boards.
FTDI_VID = 0x0403


def load_settings(path=None):
    """Read KEY=VALUE lines from the settings file. Missing file -> {}."""
    settings = {}
    try:
        text = Path(path or SETTINGS_FILE).read_text()
    except FileNotFoundError:
        return settings
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            settings[key.strip()] = value.strip().strip('"\'')
    return settings


def save_settings(port, baud, path=None):
    Path(path or SETTINGS_FILE).write_text(
        "# Saved by Receiver/LiveTelemetry.py: the port used last time.\n"
        "# Not committed (differs between laptops). Delete to reset.\n"
        f"SERIALPORT={port}\n"
        f"BAUD={baud}\n"
    )


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


def get_port_and_baud(ports, settings=None, environ=os.environ):
    """The suggested (port, reason, baud). port and reason are None if there is
    nothing to suggest.

    Port: the SERIALPORT environment variable if set, else suggest_port().
    Baud: the BAUD environment variable, else BAUD in serial.env, else 115200.
    """
    if settings is None:
        settings = load_settings()
    if environ.get("SERIALPORT"):
        port, reason = environ["SERIALPORT"], "set by SERIALPORT"
    else:
        port, reason = suggest_port(ports, settings.get("SERIALPORT"))
    baud = int(environ.get("BAUD") or settings.get("BAUD") or DEFAULT_BAUD)
    return port, reason, baud
