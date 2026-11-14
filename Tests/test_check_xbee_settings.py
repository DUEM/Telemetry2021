import json

import pytest

import tools.check_xbee_settings as xs


class FakeXBee:
    """Answers like an XBee in transparent mode at one baud rate.

    Radio data from the car arrives before +++ is answered, as it would on the
    telemetry laptop. Commands not in `values` get ERROR, as on a real module.
    """

    def __init__(self, values, baud=115200, radio_noise=b"\x01\x02OK\x7e\x00", noise_before_reply=b""):
        self.values, self.baud, self.noise = values, baud, radio_noise
        self.noise_before_reply = noise_before_reply
        self.at_baud = None
        self.out = bytearray()
        self.sent = []
        self.in_command_mode = False
        self.closed = False
        self.timeout = None

    def __call__(self, port, baud):  # used as open_port
        self.at_baud = baud
        self.out = bytearray(self.noise)
        return self

    @property
    def in_waiting(self):
        return len(self.out)

    def read(self, size=1):
        data, self.out = bytes(self.out[:size]), self.out[size:]
        return data

    def read_until(self, expected=b"\r"):
        i = self.out.find(expected)
        if i < 0:
            data, self.out = bytes(self.out), bytearray()
            return data
        data, self.out = bytes(self.out[:i + 1]), self.out[i + 1:]
        return data

    def reset_input_buffer(self):
        pass  # keep the radio noise: the tool must cope with data before OK

    def flush(self):
        pass

    def close(self):
        self.closed = True

    def write(self, data):
        self.sent.append(bytes(data))
        if self.at_baud != self.baud:
            self.out += b"\xff\x00"  # garbage at the wrong baud rate
            return
        if data == b"+++":
            self.in_command_mode = True
            self.out += b"OK\r"
        elif self.in_command_mode and data.startswith(b"AT"):
            cmd = data[2:-1].decode()
            if cmd == "CN":
                self.in_command_mode = False
                self.out += b"OK\r"
            else:
                self.out = bytearray(self.noise_before_reply)  # radio data arriving after the reset
                self.out += (self.values.get(cmd, "ERROR") + "\r").encode()


VALUES = {"VR": "10EF", "SH": "13A200", "SL": "41B2C3D4", "NI": "CAR", "CH": "C", "ID": "3332",
          "BD": "7", "AP": "0", "D7": "1", "SM": "0", "RO": "3", "DB": "48", "%V": "CE4",
          "TP": "FFFE", "CC": "2B", "NB": "0", "GT": "3E8"}


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """No real waiting: sleep returns at once and the clock moves on 0.1 s per look."""
    clock = iter(x / 10 for x in range(10**6))
    monkeypatch.setattr(xs.time, "sleep", lambda s: None)
    monkeypatch.setattr(xs.time, "monotonic", lambda: next(clock))


def test_reports_settings_and_decodes_values(capsys):
    fake = FakeXBee(VALUES)

    assert xs.main(["-p", "/dev/fake"], open_port=fake) == 0

    out = capsys.readouterr().out
    assert "XBee on /dev/fake at 115200 baud" in out
    assert "10EF" in out and "CAR" in out
    assert "7  (115200 baud)" in out
    assert "0  (transparent)" in out
    assert "1  (CTS flow control)" in out
    assert "-72 dBm" in out  # DB 0x48
    assert "3.30 V" in out  # %V 0xCE4 mV
    assert "-2 °C" in out  # TP 0xFFFE
    assert "'+'" in out  # CC 0x2B
    assert "not supported" in out  # e.g. BR on this module
    assert "Worth checking" not in out  # settings match what the telemetry link needs


def test_radio_data_before_a_reply_is_ignored(capsys):
    """A telemetry frame (binary) arriving just before a reply does not corrupt it."""
    frame = bytes.fromhex("4e7e1400070108007800")  # part of a real frame, ends mid-frame
    fake = FakeXBee(VALUES, noise_before_reply=frame)

    assert xs.main(["-p", "/dev/fake", "--json"], open_port=fake) == 0

    rows = {r["command"]: r["raw"] for g in json.loads(capsys.readouterr().out)["settings"].values() for r in g}
    assert rows["VR"] == "10EF" and rows["NI"] == "CAR" and rows["BR"] is None


def test_only_reads_settings():
    """Never sends a command that changes or saves a setting."""
    fake = FakeXBee(VALUES)
    xs.main(["-p", "/dev/fake"], open_port=fake)

    commands = [s for s in fake.sent if s.startswith(b"AT")]
    assert commands[-1] == b"ATCN\r"  # leaves command mode
    assert all(len(c) <= len(b"ATxx\r") for c in commands)  # no parameter given to any command
    assert not {b"ATWR\r", b"ATRE\r", b"ATFR\r", b"ATAC\r"} & set(commands)
    assert not fake.in_command_mode and fake.closed


def test_hints_flag_settings_that_matter_for_the_link(capsys):
    fake = FakeXBee({**VALUES, "BD": "3", "D7": "0", "AP": "1", "SM": "1"})
    xs.main(["-p", "/dev/fake"], open_port=fake)

    out = capsys.readouterr().out
    assert "Worth checking" in out
    for setting in ("AP is not 0", "BD is not 115200", "D7 is not CTS", "SM is not 0"):
        assert setting in out


def test_scan_finds_the_baud_rate(capsys):
    fake = FakeXBee(VALUES, baud=9600)

    assert xs.main(["-p", "/dev/fake"], open_port=fake) == 1  # not at 115200 without --scan
    assert "No XBee answered" in capsys.readouterr().err

    assert xs.main(["-p", "/dev/fake", "--scan"], open_port=fake) == 0
    assert "at 9600 baud" in capsys.readouterr().out


def test_json_output(capsys):
    xs.main(["-p", "/dev/fake", "--json"], open_port=FakeXBee(VALUES))

    data = json.loads(capsys.readouterr().out)
    assert data["baud"] == 115200
    serial_row = {r["command"]: r for r in data["settings"]["Serial interface"]}
    assert serial_row["BD"] == {"command": "BD", "description": "Serial baud rate",
                                "raw": "7", "meaning": "115200 baud"}


def test_reports_when_the_xbee_stops_answering(capsys):
    fake = FakeXBee(VALUES)
    original = fake.write

    def write(data):
        original(data)
        if data == b"ATCH\r":
            fake.out = bytearray()  # no reply, as if command mode timed out

    fake.write = write
    assert xs.main(["-p", "/dev/fake"], open_port=fake) == 1
    assert "no reply to ATCH" in capsys.readouterr().err
