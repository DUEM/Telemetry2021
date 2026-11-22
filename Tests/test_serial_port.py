"""Port listing and suggestion (Receiver/serial_port.py), from Ben Jennery's
PERI-DEVELOPMENT-BBJ-1126 branch. How LiveTelemetry uses them is tested in
test_live_telemetry.py."""
from types import SimpleNamespace

from Receiver.serial_port import describe_port, suggest_port


def port(device, vid=None, description="n/a", manufacturer=None):
    return SimpleNamespace(device=device, vid=vid, description=description,
                           manufacturer=manufacturer)


BLUETOOTH = port("/dev/cu.Bluetooth-Incoming-Port")
FTDI = port("/dev/ttyUSB1", vid=0x0403, description="FT231X USB UART",
            manufacturer="FTDI")
FTDI_REASON = "FTDI USB serial, probably the XBee"
OTHER_USB = port("/dev/ttyACM0", vid=0x2341, description="Arduino Uno")


def test_suggests_ftdi_over_other_usb_and_non_usb():
    assert suggest_port([BLUETOOTH, OTHER_USB, FTDI]) == (
        "/dev/ttyUSB1", FTDI_REASON)


def test_suggests_any_usb_when_no_ftdi():
    assert suggest_port([BLUETOOTH, OTHER_USB]) == (
        "/dev/ttyACM0", "USB serial")


def test_suggests_saved_port_when_plugged_in():
    assert suggest_port([OTHER_USB, FTDI], saved_port="/dev/ttyACM0") == (
        "/dev/ttyACM0", "last used")


def test_ignores_saved_port_when_not_plugged_in():
    assert suggest_port([FTDI], saved_port="/dev/ttyUSB0")[0] == "/dev/ttyUSB1"


def test_no_suggestion_without_usb():
    assert suggest_port([BLUETOOTH]) == (None, None)


def test_describe_port_shows_description_and_manufacturer():
    assert describe_port(FTDI) == "/dev/ttyUSB1  (FT231X USB UART, FTDI)"
    assert describe_port(BLUETOOTH) == "/dev/cu.Bluetooth-Incoming-Port"
