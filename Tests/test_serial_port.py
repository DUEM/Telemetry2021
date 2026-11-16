from types import SimpleNamespace

import pytest
import serial

from Receiver.serial_port import describe_port, get_port_and_baud, load_settings, save_settings, suggest_port


def port(device, vid=None, description="n/a", manufacturer=None):
    return SimpleNamespace(device=device, vid=vid, description=description, manufacturer=manufacturer)


BLUETOOTH = port("/dev/cu.Bluetooth-Incoming-Port")
FTDI = port("/dev/ttyUSB1", vid=0x0403, description="FT231X USB UART", manufacturer="FTDI")
OTHER_USB = port("/dev/ttyACM0", vid=0x2341, description="Arduino Uno")


def answers(*replies):
    """An `ask` function that gives `replies` in turn and records the prompts."""
    it = iter(replies)
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return next(it)
    ask.asked = asked
    return ask


def test_suggests_ftdi_over_other_usb_and_non_usb():
    assert suggest_port([BLUETOOTH, OTHER_USB, FTDI]) == ("/dev/ttyUSB1", "FTDI USB serial, probably the XBee")


def test_suggests_any_usb_when_no_ftdi():
    assert suggest_port([BLUETOOTH, OTHER_USB]) == ("/dev/ttyACM0", "USB serial")


def test_suggests_saved_port_when_plugged_in():
    assert suggest_port([OTHER_USB, FTDI], saved_port="/dev/ttyACM0") == ("/dev/ttyACM0", "last used")


def test_ignores_saved_port_when_not_plugged_in():
    assert suggest_port([FTDI], saved_port="/dev/ttyUSB0")[0] == "/dev/ttyUSB1"


def test_no_suggestion_without_usb():
    assert suggest_port([BLUETOOTH]) == (None, None)


def test_get_port_and_baud_suggests_without_asking():
    assert get_port_and_baud([BLUETOOTH, FTDI], settings={}, environ={}) == (
        "/dev/ttyUSB1", "FTDI USB serial, probably the XBee", 115200)


def test_get_port_and_baud_nothing_to_suggest():
    assert get_port_and_baud([BLUETOOTH], settings={}, environ={}) == (None, None, 115200)


def test_get_port_and_baud_uses_saved_settings():
    settings = {"SERIALPORT": "/dev/ttyACM0", "BAUD": "9600"}

    assert get_port_and_baud([OTHER_USB, FTDI], settings, environ={}) == ("/dev/ttyACM0", "last used", 9600)


def test_get_port_and_baud_environment_wins():
    environ = {"SERIALPORT": "/tmp/ttyV0", "BAUD": "57600"}

    assert get_port_and_baud([FTDI], {"BAUD": "9600"}, environ) == ("/tmp/ttyV0", "set by SERIALPORT", 57600)


def test_describe_port_shows_description_and_manufacturer():
    assert describe_port(FTDI) == "/dev/ttyUSB1  (FT231X USB UART, FTDI)"
    assert describe_port(BLUETOOTH) == "/dev/cu.Bluetooth-Incoming-Port"


@pytest.fixture
def fake_open(monkeypatch):
    """Patch serial.Serial in LiveTelemetry: only ports in `working` open.

    Returns a function that takes the user's replies and the working ports and
    gives back the `asked` prompts list.
    """
    from Receiver import LiveTelemetry

    def setup(replies, working):
        ask = answers(*replies)
        monkeypatch.setattr("builtins.input", ask)

        def fake_serial(port, baud):
            if port not in working:
                raise serial.SerialException(f"could not open port {port}")
            return ("connection", port, baud)
        monkeypatch.setattr(LiveTelemetry.serial, "Serial", fake_serial)
        return ask.asked
    return setup


def test_enter_opens_suggested_port(fake_open):
    from Receiver.LiveTelemetry import open_serial_port
    asked = fake_open([""], working=["/dev/ttyUSB0"])

    assert open_serial_port("/dev/ttyUSB0", "last used", 115200) == (("connection", "/dev/ttyUSB0", 115200), "/dev/ttyUSB0")
    assert asked[0].startswith("Use /dev/ttyUSB0 (last used)?")


def test_typed_port_replaces_suggested_port(fake_open):
    from Receiver.LiveTelemetry import open_serial_port
    fake_open(["  /tmp/ttyV0 "], working=["/dev/ttyUSB0", "/tmp/ttyV0"])

    assert open_serial_port("/dev/ttyUSB0", "USB serial", 115200)[1] == "/tmp/ttyV0"


def test_port_that_will_not_open_asks_again(fake_open, caplog):
    from Receiver.LiveTelemetry import open_serial_port
    # the suggested port is unplugged, then a typo, then the right port
    asked = fake_open(["", "/dev/ttyUSB9", "/dev/ttyUSB1"], working=["/dev/ttyUSB1"])

    assert open_serial_port("/dev/ttyUSB0", "last used", 115200)[1] == "/dev/ttyUSB1"
    assert len(asked) == 3
    assert "Cannot open serial port /dev/ttyUSB0" in caplog.text
    assert "Cannot open serial port /dev/ttyUSB9" in caplog.text


def test_without_suggestion_asks_until_a_port_is_typed(fake_open):
    from Receiver.LiveTelemetry import open_serial_port
    asked = fake_open(["", "COM8"], working=["COM8"])

    assert open_serial_port(None, None, 115200)[1] == "COM8"
    assert asked == ["Type the serial port to use: "] * 2


def test_ask_baud_enter_keeps_suggested_rate(monkeypatch):
    from Receiver.LiveTelemetry import ask_baud
    ask = answers("")
    monkeypatch.setattr("builtins.input", ask)

    assert ask_baud(115200) == 115200
    assert ask.asked[0].startswith("Use a baud rate of 115200?")


def test_ask_baud_typed_rate(monkeypatch):
    from Receiver.LiveTelemetry import ask_baud
    monkeypatch.setattr("builtins.input", answers(" 9600 "))

    assert ask_baud(115200) == 9600


def test_ask_baud_asks_again_after_non_number(monkeypatch, caplog):
    from Receiver.LiveTelemetry import ask_baud
    ask = answers("abc", "")
    monkeypatch.setattr("builtins.input", ask)

    assert ask_baud(115200) == 115200
    assert len(ask.asked) == 2
    assert "'abc' is not a number" in caplog.text


def test_settings_round_trip(tmp_path):
    path = tmp_path / "serial.env"

    save_settings("/dev/ttyUSB0", 115200, path)

    assert load_settings(path) == {"SERIALPORT": "/dev/ttyUSB0", "BAUD": "115200"}


def test_load_settings_ignores_comments_blanks_and_quotes(tmp_path):
    path = tmp_path / "serial.env"
    path.write_text('# comment\n\nSERIALPORT="COM8"\nnonsense\n')

    assert load_settings(path) == {"SERIALPORT": "COM8"}


def test_missing_settings_file_is_empty(tmp_path):
    assert load_settings(tmp_path / "nope.env") == {}
