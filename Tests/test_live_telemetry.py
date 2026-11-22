import pytest

from Receiver.frame_reader import END_OF_FRAME_MARKER, read_frames


class FakeSerial:
    """Hands out a capture `chunk` bytes at a time, like a serial port would."""

    def __init__(self, data: bytes, chunk: int):
        self.data, self.chunk, self.pos = data, chunk, 0

    @property
    def in_waiting(self):
        return min(self.chunk, len(self.data) - self.pos)

    def read(self, size):
        out = self.data[self.pos:self.pos + size]
        self.pos += len(out)
        return out

    def finished(self):
        return self.pos >= len(self.data)


@pytest.mark.parametrize("capture", ["NRT.BIN", "MPPT.BIN"])
@pytest.mark.parametrize("chunk", [1, 7, 4096])
def test_receive_stores_the_same_frames_as_read_frames(request, capture, chunk):
    """Live and offline paths must agree, including re-joined frames."""
    # arrange - importing the module must not open the serial port
    from Receiver.LiveTelemetry import receive

    path = f"{request.config.rootdir}/Tests/data/{capture}"
    data = open(path, "rb").read()
    port = FakeSerial(data, chunk)
    stored = []

    # act
    assembler = receive(port, store=stored.append, keep_running=lambda: not port.finished())

    # assert - the offline reader also returns the bytes after the last marker
    # (empty if the capture ends with one); the live receiver waits for its marker
    offline = read_frames(path)
    assert offline[-1] == data.split(END_OF_FRAME_MARKER)[-1]
    assert stored == offline[:-1]
    # complete pieces never contain the marker, so these are the re-joined frames
    assert assembler.rejoined == sum(END_OF_FRAME_MARKER in f for f in stored) > 0


def test_receive_flushes_a_held_piece_when_stopped():
    """A piece waiting for more data is still stored when the receiver stops."""
    from Receiver.LiveTelemetry import receive

    port = FakeSerial(b"\x01\x02\x03" + END_OF_FRAME_MARKER + b"\x04\x05", chunk=64)
    stored = []

    receive(port, store=stored.append, keep_running=lambda: not port.finished())

    # the bytes after the last marker are an unfinished frame and are not stored
    assert stored == [b"\x01\x02\x03"]


@pytest.mark.parametrize("error", [OSError(5, "Input/output error"), "SerialException"])
def test_receive_stops_cleanly_when_the_port_is_lost(request, tmp_path, caplog, error):
    """USB unplugged or the SIL replay ended: frames received so far are kept,
    and receive() returns normally so the outputs can be saved and closed."""
    import serial
    from Receiver.LiveTelemetry import receive

    if error == "SerialException":  # what read() raises when the device has gone
        error = serial.SerialException("device reports readiness to read but returned no data")
    data = open(f"{request.config.rootdir}/Tests/data/MPPT.BIN", "rb").read()
    half = data[: len(data) // 2]

    class LostPort(FakeSerial):
        @property
        def in_waiting(self):
            if self.finished():
                raise error
            return super().in_waiting

    port = LostPort(half, chunk=64)
    stored = []

    receive(port, store=stored.append, keep_running=lambda: True)  # only the error stops it

    # everything received before the disconnection is stored, as the offline
    # reader would; only the piece cut off after the last marker is lost
    received = tmp_path / "received.BIN"
    received.write_bytes(half)
    assert stored == read_frames(received)[:-1]
    assert len(stored) > 100
    assert "Serial port lost" in caplog.text


@pytest.mark.parametrize(
    "port, expected",
    [
        ("/dev/ttyNoSuchXBee", "does not exist"),  # XBee not plugged in
        ("/", "Check that / is the XBee's port"),  # any other open failure
    ],
)
def test_open_serial_port_exits_with_a_message_when_it_cannot_open(port, expected):
    from Receiver.LiveTelemetry import open_serial_port

    with pytest.raises(SystemExit) as exited:
        open_serial_port(port)

    message = str(exited.value.code)  # sys.exit(message) prints it and exits with 1
    assert message.startswith(f"Cannot open serial port {port}:")
    assert expected in message


def test_open_serial_port_uses_the_port_in_config_yml(monkeypatch):
    from Receiver.LiveTelemetry import open_serial_port

    monkeypatch.setattr("Receiver.receiver_config.serialPort", "/dev/ttyNoSuchXBee")
    with pytest.raises(SystemExit) as exited:
        open_serial_port()

    message = str(exited.value.code)
    assert message.startswith("Cannot open serial port /dev/ttyNoSuchXBee:")
    assert "set serialPort in Receiver/config.yml" in message


@pytest.fixture
def session_settings(monkeypatch):
    """Known defaults for the prompted settings; all restored after the test."""
    from Receiver.receiver_config import InfluxCredentials

    for name, value in {
        "serialPort": "/dev/ttyUSB0",
        "sessionLogName": "telem-received",
        "xlsxEnabled": False,
        "binEnabled": True,
        "csvEnabled": True,
    }.items():
        monkeypatch.setattr(f"Receiver.receiver_config.{name}", value)
    monkeypatch.setattr(
        "Receiver.receiver_config.ifCredentials",
        InfluxCredentials("admin", "password", "DUSCiESC", "localhost", 8086, True),
    )


def answering(*answers):
    """A stand-in for input() that records the prompts and gives `answers` in turn."""
    prompts, replies = [], iter(answers)

    def ask(prompt):
        prompts.append(prompt)
        return next(replies)

    ask.prompts = prompts
    return ask


def test_prompts_show_the_config_defaults(session_settings):
    from Receiver.LiveTelemetry import prompt_settings

    ask = answering(*[""] * 9)
    prompt_settings(ask)

    assert ask.prompts == [
        "Serial port [ default: /dev/ttyUSB0 ]: ",
        "Telemetry Session Name (no spaces) [ default: telem-received ]: ",
        "Excel logging (true/false) [ default: false ]: ",
        "BIN logging (true/false) [ default: true ]: ",
        "CSV logging (true/false) [ default: true ]: ",
        "InfluxDB logging (true/false) [ default: true ]: ",
        "InfluxDB database name [ default: DUSCiESC ]: ",
        "InfluxDB username [ default: admin ]: ",
        "InfluxDB password [ default: password ]: ",
    ]


def test_blank_answers_keep_the_defaults(session_settings):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    before = {n: getattr(receiver_config, n) for n in
              ("serialPort", "sessionLogName", "xlsxEnabled", "binEnabled", "csvEnabled", "ifCredentials")}
    prompt_settings(answering(*["", "  "] * 4, ""))

    assert {n: getattr(receiver_config, n) for n in before} == before


def test_answers_are_used_for_this_session(session_settings):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    prompt_settings(answering(
        "/tmp/ttyV0", "qualifying-day1", "yes", "n", "FALSE", "y", "OldSession", "dusc", "secret",
    ))

    assert receiver_config.serialPort == "/tmp/ttyV0"
    assert receiver_config.sessionLogName == "qualifying-day1"
    assert (receiver_config.xlsxEnabled, receiver_config.binEnabled, receiver_config.csvEnabled) == (True, False, False)
    credentials = receiver_config.ifCredentials
    assert (credentials.enabled, credentials.db, credentials.username, credentials.password) == (
        True, "OldSession", "dusc", "secret")
    # not prompted for: unchanged
    assert (credentials.host, credentials.port) == ("localhost", 8086)


def test_bad_answers_are_asked_again(session_settings, capsys):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    ask = answering("", "race day1", "race/day1", "race-day1", "maybe", "true", *[""] * 6)
    prompt_settings(ask)

    assert receiver_config.sessionLogName == "race-day1"
    assert receiver_config.xlsxEnabled is True
    assert len(ask.prompts) == 12  # session name asked three times, Excel twice
    out = capsys.readouterr().out
    assert "cannot contain spaces" in out
    assert "cannot contain / \\" in out
    assert "Please answer true or false" in out


def test_influx_database_and_credentials_only_asked_if_influx_is_on(session_settings):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    ask = answering("", "", "", "", "", "false")
    prompt_settings(ask)

    assert ask.prompts[-1] == "InfluxDB logging (true/false) [ default: true ]: "
    assert len(ask.prompts) == 6
    credentials = receiver_config.ifCredentials
    assert credentials.enabled is False
    # left as in config.yml
    assert (credentials.db, credentials.username, credentials.password) == ("DUSCiESC", "admin", "password")


def test_no_input_uses_the_defaults(session_settings):
    """e.g. the receiver started as a service, with no terminal."""
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    def no_input(prompt):
        raise EOFError

    prompt_settings(no_input)

    assert receiver_config.serialPort == "/dev/ttyUSB0"
    assert receiver_config.ifCredentials.db == "DUSCiESC"
