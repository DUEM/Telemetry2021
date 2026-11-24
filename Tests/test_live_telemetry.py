import time

import pytest
import serial

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


class RealTimePort:
    """A serial port fed by a radio: bytes arrive at `rate` bytes/s whether or
    not anything reads them. Like the operating system's buffer for a real
    port (4096 bytes on Linux), it holds at most `size` bytes, and bytes that
    arrive while it is full are lost."""

    def __init__(self, data: bytes, rate: float, size: int = 4096):
        self.data, self.rate, self.size = data, rate, size
        self.start = time.monotonic()
        self.arrived = 0  # bytes that have arrived so far, kept or lost
        self.held = bytearray()
        self.lost = 0

    def _arrive(self):
        now = min(len(self.data), int((time.monotonic() - self.start) * self.rate))
        new = self.data[self.arrived:now]
        self.arrived = now
        room = self.size - len(self.held)
        self.held += new[:room]
        self.lost += max(0, len(new) - room)

    @property
    def in_waiting(self):
        self._arrive()
        return len(self.held)

    def read(self, size):
        out = bytes(self.held[:size])
        del self.held[:size]
        return out

    def finished(self):
        self._arrive()
        return self.arrived >= len(self.data) and not self.held


def test_slow_storing_does_not_lose_radio_data(request):
    """Storing can be slow (InfluxDB over the network, the Excel file being
    saved). When the receiver waited for it before reading the port again, the
    port's buffer filled and the radio data after that was lost: data arrived
    in bursts of about 4096 bytes with long gaps between, as in NRT.BIN. Reading
    must carry on while frames are stored."""
    from Receiver.LiveTelemetry import receive

    path = f"{request.config.rootdir}/Tests/data/NRT.BIN"
    data = open(path, "rb").read()
    # about 4 times the radio's 115200 baud, to keep the test short
    port = RealTimePort(data, rate=50_000)
    stored = []

    def slow_store(frame):
        # pauses long enough for over 4096 bytes to arrive, as a slow
        # InfluxDB write or an Excel save would
        if len(stored) % 400 == 0:
            time.sleep(0.2)
        stored.append(frame)

    receive(port, store=slow_store, keep_running=lambda: not port.finished())

    assert port.lost == 0
    assert stored == read_frames(path)[:-1]


def test_bandwidth_is_logged(request, monkeypatch, caplog):
    import logging
    from Receiver.LiveTelemetry import receive
    from Receiver.frame_reader import frame_is_complete

    monkeypatch.setattr("Receiver.LiveTelemetry.BANDWIDTH_REPORT_INTERVAL", 0)  # report after every read
    path = f"{request.config.rootdir}/Tests/data/MPPT.BIN"
    data = open(path, "rb").read()
    port = FakeSerial(data, chunk=len(data))  # the whole capture in one read
    caplog.set_level(logging.INFO)

    receive(port, store=lambda frame: None, keep_running=lambda: not port.finished())

    frames = read_frames(path)[:-1]
    crc_fails = sum(not frame_is_complete(f) for f in frames)
    report = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("Radio, last"))
    assert "of 115200 baud" in report  # FakeSerial has no baudrate: the default is used
    assert f"{crc_fails} CRC fails" in report
    assert len(frames) > 100


def test_a_frame_that_cannot_be_stored_does_not_stop_storing(caplog):
    from Receiver.LiveTelemetry import receive

    frames = [b"\x01\x02", b"\x03\x04", b"\x05\x06"]
    port = FakeSerial(END_OF_FRAME_MARKER.join(frames) + END_OF_FRAME_MARKER, chunk=64)
    stored = []

    def store(frame):
        if frame == b"\x03\x04":
            raise ValueError("cannot decode")
        stored.append(frame)

    receive(port, store=store, keep_running=lambda: not port.finished())

    assert stored == [b"\x01\x02", b"\x05\x06"]
    assert "Could not store a frame (0304)" in caplog.text


@pytest.mark.parametrize(
    "port, expected",
    [
        ("/dev/ttyNoSuchXBee", "does not exist"),  # XBee not plugged in
        ("/", "Check that / is the XBee's port"),  # any other open failure
    ],
)
def test_port_that_cannot_open_is_explained(port, expected, capsys):
    from Receiver.LiveTelemetry import try_open_serial_port

    assert try_open_serial_port(port, 115200) is None

    out = capsys.readouterr().out
    assert out.startswith(f"Cannot open serial port {port}:")
    assert expected in out


def port_info(device, vid=None, description="n/a", manufacturer=None):
    """Like an entry of serial.tools.list_ports.comports()."""
    from types import SimpleNamespace

    return SimpleNamespace(device=device, vid=vid, description=description, manufacturer=manufacturer)


FTDI_XBEE = port_info("/dev/ttyUSB1", vid=0x0403, description="FT231X USB UART", manufacturer="FTDI")
ONBOARD = port_info("/dev/ttyS0")


@pytest.fixture
def serial_ports(monkeypatch):
    """The serial ports the receiver sees: `listed` (what list_serial_ports
    returns) and which open (all except those in `wont_open`). `opened` records
    the ports and baud rates opened."""
    from types import SimpleNamespace

    ports = SimpleNamespace(listed=[], wont_open=set(), opened=[])

    def fake_serial(port, baud):
        if port in ports.wont_open:
            raise serial.SerialException(2, "could not open port", port)
        ports.opened.append((port, baud))
        return ("connection", port)

    monkeypatch.setattr("Receiver.LiveTelemetry.serial.Serial", fake_serial)
    monkeypatch.setattr("Receiver.LiveTelemetry.list_serial_ports", lambda: list(ports.listed))
    return ports


def start_receiver(ask):
    """Answer the questions and open the serial port, as the receiver does at start up."""
    from Receiver.LiveTelemetry import open_serial_port, prompt_settings

    return open_serial_port(prompt_settings(ask), ask)


class FakeInflux:
    """Stands in for InfluxDBClient: a server with the databases in `databases`."""

    databases = ["_internal", "DUSCiESC"]
    created = []
    error = None  # raised by get_list_database, e.g. InfluxDB not running
    create_error = None

    def __init__(self, **connection):
        self.connection = connection

    def get_list_database(self):
        if self.error:
            raise self.error
        return [{"name": name} for name in self.databases]

    def create_database(self, name):
        if self.create_error:
            raise self.create_error
        self.created.append(name)
        self.databases.append(name)


@pytest.fixture
def fake_influx(monkeypatch):
    class Server(FakeInflux):
        databases = list(FakeInflux.databases)
        created = []

    monkeypatch.setattr("Receiver.LiveTelemetry.InfluxDBClient", Server)
    return Server


@pytest.fixture
def session_settings(monkeypatch, fake_influx, serial_ports, tmp_path):
    """Known defaults for the prompted settings; all restored after the test.
    Runs in tmp_path, so the .env file of last used settings is written there.
    No serial ports are listed, and every port opens (see serial_ports)."""
    from Receiver.receiver_config import InfluxCredentials

    monkeypatch.chdir(tmp_path)

    for name, value in {
        "serialPort": "/dev/ttyUSB0",
        "serialBaud": 115200,
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
        "create",  # OldSession is not in the fake InfluxDB
        "",  # Return after the Grafana reminder
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


def influx_settings(db, answers_after_db=()):
    """Answers: defaults for everything, InfluxDB on, database `db`, then `answers_after_db`."""
    return answering("", "", "", "", "", "", db, "", "", *answers_after_db)


def test_existing_database_is_used(session_settings, fake_influx, capsys):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    ask = influx_settings("DUSCiESC")
    prompt_settings(ask)

    assert len(ask.prompts) == 9  # no question about creating it
    assert receiver_config.ifCredentials.db == "DUSCiESC"
    assert fake_influx.created == []
    assert "InfluxDB database 'DUSCiESC' found" in capsys.readouterr().out


def test_new_database_is_created_if_asked(session_settings, fake_influx, capsys):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    ask = influx_settings("Race2027", ["create", ""])
    prompt_settings(ask)

    assert ask.prompts[-1] == "Press Return to continue, or q to quit: "
    assert ask.prompts[-2] == (
        "InfluxDB database 'Race2027' does not exist. Create it, or use the default "
        "'DUSCiESC'? (create/default) [ default: default ]: "
    )
    assert fake_influx.created == ["Race2027"]
    assert receiver_config.ifCredentials.db == "Race2027"
    out = capsys.readouterr().out
    assert "Creating InfluxDB database 'Race2027'" in out
    assert "Reminder: Grafana" in out and "change the data source's Database to 'Race2027'" in out


def test_missing_database_falls_back_to_the_default(session_settings, fake_influx, capsys):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    prompt_settings(influx_settings("Typo", ["maybe", ""]))  # asked again, then the default

    assert fake_influx.created == []
    assert receiver_config.ifCredentials.db == "DUSCiESC"
    out = capsys.readouterr().out
    assert "Please answer create (c) or default (d)" in out
    assert "Using InfluxDB database 'DUSCiESC'" in out


def test_missing_default_database_is_created_without_the_grafana_reminder(session_settings, fake_influx, capsys):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    fake_influx.databases = ["_internal"]  # e.g. a new laptop
    ask = influx_settings("", [""])
    prompt_settings(ask)

    assert ask.prompts[-1] == "InfluxDB database 'DUSCiESC' does not exist. Create it? (true/false) [ default: true ]: "
    assert fake_influx.created == ["DUSCiESC"]
    assert receiver_config.ifCredentials.db == "DUSCiESC"
    assert "Reminder: Grafana" not in capsys.readouterr().out


def test_default_database_not_created_if_declined(session_settings, fake_influx, capsys):
    from Receiver.LiveTelemetry import prompt_settings

    fake_influx.databases = ["_internal"]
    prompt_settings(influx_settings("", ["no"]))

    assert fake_influx.created == []
    assert "nothing will be stored in InfluxDB until database 'DUSCiESC' exists" in capsys.readouterr().out


def test_influx_not_running_is_reported_and_the_receiver_carries_on(session_settings, fake_influx, capsys):
    from requests.exceptions import ConnectionError
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    fake_influx.error = ConnectionError("Connection refused")
    ask = influx_settings("Race2027", [""])
    prompt_settings(ask)

    assert len(ask.prompts) == 10
    assert ask.prompts[-1] == "Press Return to continue, or q to quit: "
    assert receiver_config.ifCredentials.db == "Race2027"
    assert "Cannot check the InfluxDB databases at localhost:8086" in capsys.readouterr().out


def test_failed_create_uses_the_default(session_settings, fake_influx, capsys):
    from influxdb.exceptions import InfluxDBClientError
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    fake_influx.create_error = InfluxDBClientError("forbidden", 403)
    prompt_settings(influx_settings("Race2027", ["c"]))

    assert receiver_config.ifCredentials.db == "DUSCiESC"
    out = capsys.readouterr().out
    assert "Could not create database 'Race2027'" in out
    assert "Using the default database 'DUSCiESC' instead" in out
    assert "Reminder: Grafana" not in out


def test_database_check_uses_the_credentials_given(session_settings, fake_influx, monkeypatch):
    from Receiver.LiveTelemetry import prompt_settings

    seen = {}

    class Recording(fake_influx):
        def __init__(self, **connection):
            seen.update(connection)

    monkeypatch.setattr("Receiver.LiveTelemetry.InfluxDBClient", Recording)
    prompt_settings(answering("", "", "", "", "", "", "", "dusc", "secret"))

    assert (seen["host"], seen["port"], seen["username"], seen["password"]) == ("localhost", 8086, "dusc", "secret")


@pytest.mark.parametrize("quit_answer", ["q", "Q", " q "])
def test_q_after_the_grafana_reminder_quits(session_settings, fake_influx, quit_answer):
    from Receiver.LiveTelemetry import prompt_settings

    with pytest.raises(SystemExit) as exited:
        prompt_settings(influx_settings("Race2027", ["create", quit_answer]))

    assert exited.value.code == "Quit: the receiver was not started"
    assert fake_influx.created == ["Race2027"]  # already created before the reminder


def test_q_after_influx_cannot_be_reached_quits(session_settings, fake_influx):
    from requests.exceptions import ConnectionError
    from Receiver.LiveTelemetry import prompt_settings

    fake_influx.error = ConnectionError("Connection refused")
    with pytest.raises(SystemExit) as exited:
        prompt_settings(influx_settings("DUSCiESC", ["q"]))

    assert exited.value.code == "Quit: the receiver was not started"


def test_no_pause_without_a_warning(session_settings, fake_influx):
    from Receiver.LiveTelemetry import prompt_settings

    ask = influx_settings("DUSCiESC")
    prompt_settings(ask)

    assert "Press Return to continue, or q to quit: " not in ask.prompts


def test_pause_waits_for_return_or_q(session_settings, fake_influx, capsys):
    """Anything else at the pause asks again, rather than carrying on."""
    from requests.exceptions import ConnectionError
    from Receiver.LiveTelemetry import prompt_settings

    fake_influx.error = ConnectionError("Connection refused")
    ask = influx_settings("DUSCiESC", ["x", "yes", "continue"])
    with pytest.raises(StopIteration):  # still waiting after three other answers
        prompt_settings(ask)
    assert ask.prompts[-3:] == ["Press Return to continue, or q to quit: "] * 3
    assert "Please press Return on its own to continue, or q then Return to quit" in capsys.readouterr().out

    ask = influx_settings("DUSCiESC", ["x", "Q"])
    with pytest.raises(SystemExit):
        prompt_settings(ask)

    ask = influx_settings("DUSCiESC", ["x", ""])
    prompt_settings(ask)  # Return carries on
    assert ask.prompts[-2:] == ["Press Return to continue, or q to quit: "] * 2


# --- last used settings, in .env in the directory the receiver is run from ---

ALL_DEFAULTS = [""] * 9  # Enter at every question (InfluxDB on, database found)


def first_run_then_defaults_back(monkeypatch):
    """Answer a first run (saving .env), then put the config defaults back, as
    a new start of the receiver would."""
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    before = {n: getattr(receiver_config, n) for n in
              ("serialPort", "sessionLogName", "xlsxEnabled", "binEnabled", "csvEnabled", "ifCredentials")}
    start_receiver(answering("/dev/ttyUSB1", "race-day1", "yes", "no", "no", "", "", "dusc", "secret"))
    for name, value in before.items():
        monkeypatch.setattr(f"Receiver.receiver_config.{name}", value)


def test_settings_are_saved_in_env_in_the_run_directory(session_settings, tmp_path):
    from Receiver.LiveTelemetry import prompt_settings

    start_receiver(answering("/dev/ttyUSB1", "race-day1", "yes", "", "no", "", "", "dusc", "secret"))

    lines = [l for l in (tmp_path / ".env").read_text().splitlines() if not l.startswith("#")]
    assert lines == [
        "SERIAL_PORT=/dev/ttyUSB1",
        "SESSION_NAME=race-day1",
        "EXCEL_LOGGING=true",
        "BIN_LOGGING=true",
        "CSV_LOGGING=false",
        "INFLUX_LOGGING=true",
        "INFLUX_DATABASE=DUSCiESC",
        "INFLUX_USERNAME=dusc",
        "INFLUX_PASSWORD=secret",
    ]


def test_without_env_the_prompts_show_only_the_default(session_settings, tmp_path):
    from Receiver.LiveTelemetry import prompt_settings

    ask = answering(*ALL_DEFAULTS)
    start_receiver(ask)

    assert ask.prompts[0] == "Serial port [ default: /dev/ttyUSB0 ]: "
    assert all("last used" not in p for p in ask.prompts)
    assert (tmp_path / ".env").exists()  # but next time they will


def test_with_env_the_prompts_show_the_last_used_values(session_settings, monkeypatch):
    from Receiver.LiveTelemetry import prompt_settings

    first_run_then_defaults_back(monkeypatch)
    ask = answering(*ALL_DEFAULTS)
    prompt_settings(ask)

    assert ask.prompts == [
        "Serial port [ default: /dev/ttyUSB0, last used: /dev/ttyUSB1 ]: ",
        "Telemetry Session Name (no spaces) [ default: telem-received, last used: race-day1 ]: ",
        "Excel logging (true/false) [ default: false, last used: true ]: ",
        "BIN logging (true/false) [ default: true, last used: false ]: ",
        "CSV logging (true/false) [ default: true, last used: false ]: ",
        "InfluxDB logging (true/false) [ default: true, last used: true ]: ",
        "InfluxDB database name [ default: DUSCiESC, last used: DUSCiESC ]: ",
        "InfluxDB username [ default: admin, last used: dusc ]: ",
        "InfluxDB password [ default: password, last used: secret ]: ",
    ]


def test_l_uses_the_last_used_value_and_d_or_enter_the_default(session_settings, monkeypatch):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    first_run_then_defaults_back(monkeypatch)
    prompt_settings(answering("l", "L", "l", "d", "", "l", "d", "l", "D"))

    assert receiver_config.serialPort == "/dev/ttyUSB1"
    assert receiver_config.sessionLogName == "race-day1"
    assert receiver_config.xlsxEnabled is True
    assert receiver_config.binEnabled is True  # d: default
    assert receiver_config.csvEnabled is True  # Enter: default
    credentials = receiver_config.ifCredentials
    assert (credentials.enabled, credentials.db, credentials.username, credentials.password) == (
        True, "DUSCiESC", "dusc", "password")


def test_d_and_l_are_ordinary_answers_without_a_last_used_value(session_settings):
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import prompt_settings

    prompt_settings(answering("l", "d", *[""] * 7))  # no .env yet

    assert receiver_config.serialPort == "l"
    assert receiver_config.sessionLogName == "d"


def test_influx_settings_are_kept_when_influx_is_off(session_settings, tmp_path):
    from Receiver.LiveTelemetry import prompt_settings, read_last_used

    start_receiver(answering("", "", "", "", "", "", "", "dusc", "secret"))
    start_receiver(answering("", "", "", "", "", "false"))  # not asked this time

    saved = read_last_used(tmp_path / ".env")
    assert saved["influxEnabled"] == "false"
    assert (saved["influxUsername"], saved["influxPassword"]) == ("dusc", "secret")


def test_bad_or_missing_last_used_values_are_not_offered(session_settings, tmp_path):
    from Receiver.LiveTelemetry import prompt_settings

    (tmp_path / ".env").write_text(
        "# edited by hand\n"
        "SERIAL_PORT = /dev/ttyACM0\n"
        "SESSION_NAME=race day\n"  # space: not a valid session name
        "EXCEL_LOGGING=maybe\n"
        "UNKNOWN=1\n"
        "INFLUX_PASSWORD=pa=ss word\n"
    )
    ask = answering(*ALL_DEFAULTS)
    prompt_settings(ask)

    assert ask.prompts[0] == "Serial port [ default: /dev/ttyUSB0, last used: /dev/ttyACM0 ]: "
    assert ask.prompts[1] == "Telemetry Session Name (no spaces) [ default: telem-received ]: "
    assert ask.prompts[2] == "Excel logging (true/false) [ default: false ]: "
    assert ask.prompts[3] == "BIN logging (true/false) [ default: true ]: "
    assert ask.prompts[8] == "InfluxDB password [ default: password, last used: pa=ss word ]: "


def test_quitting_at_a_warning_does_not_save_the_settings(session_settings, fake_influx, tmp_path):
    from requests.exceptions import ConnectionError
    from Receiver.LiveTelemetry import prompt_settings

    fake_influx.error = ConnectionError("Connection refused")
    with pytest.raises(SystemExit):
        prompt_settings(influx_settings("DUSCiESC", ["q"]))

    assert not (tmp_path / ".env").exists()



# --- serial port: list, suggestion, asking again (from the BBJ-1126 branch) ---

def test_serial_ports_are_listed_before_the_question(session_settings, serial_ports, capsys):
    from Receiver.LiveTelemetry import prompt_settings

    serial_ports.listed = [ONBOARD, port_info("/dev/ttyUSB0", vid=0x0403, description="FT231X USB UART")]
    prompt_settings(answering(*ALL_DEFAULTS))

    out = capsys.readouterr().out
    assert ("Serial ports found:\n  /dev/ttyUSB0  (FT231X USB UART)\n"
            "  (and 1 other serial port, not USB so not the XBee: /dev/ttyS0)\n") in out
    assert "Suggested" not in out  # the default, /dev/ttyUSB0, is plugged in


def test_many_non_usb_ports_are_summarised_in_number_order(session_settings, serial_ports, capsys):
    from Receiver.LiveTelemetry import prompt_settings

    serial_ports.listed = [port_info(f"/dev/ttyS{n}") for n in range(32)] + [
        port_info("/dev/ttyUSB10", vid=0x0403), port_info("/dev/ttyUSB2", vid=0x0403)]
    prompt_settings(answering(*ALL_DEFAULTS))

    out = capsys.readouterr().out
    assert ("Serial ports found:\n  /dev/ttyUSB2\n  /dev/ttyUSB10\n"
            "  (and 32 other serial ports, not USB so not the XBee: /dev/ttyS0 to /dev/ttyS31)\n") in out


def test_only_non_usb_ports(session_settings, serial_ports, capsys):
    from Receiver.LiveTelemetry import prompt_settings

    serial_ports.listed = [ONBOARD]
    prompt_settings(answering(*ALL_DEFAULTS))

    out = capsys.readouterr().out
    assert "Serial ports found: no USB serial ports\n  (and 1 other serial port" in out
    assert "Suggested" not in out


def test_no_serial_ports(session_settings, capsys):
    from Receiver.LiveTelemetry import prompt_settings

    prompt_settings(answering(*ALL_DEFAULTS))

    out = capsys.readouterr().out
    assert "Serial ports found: none" in out
    assert "Suggested" not in out


def test_a_port_is_suggested_when_the_default_is_not_plugged_in(session_settings, serial_ports, capsys):
    from Receiver.LiveTelemetry import prompt_settings

    serial_ports.listed = [ONBOARD, FTDI_XBEE]
    ask = answering(*ALL_DEFAULTS)
    prompt_settings(ask)

    assert "Suggested: /dev/ttyUSB1 (FTDI USB serial, probably the XBee): type it to use it" in capsys.readouterr().out
    assert ask.prompts[0] == "Serial port [ default: /dev/ttyUSB0 ]: "  # the question is unchanged


def test_last_used_port_is_suggested_with_l(session_settings, serial_ports, tmp_path, capsys):
    from Receiver.LiveTelemetry import prompt_settings

    (tmp_path / ".env").write_text("SERIAL_PORT=/dev/ttyACM0\n")
    serial_ports.listed = [FTDI_XBEE, port_info("/dev/ttyACM0", vid=0x2341)]
    prompt_settings(answering(*ALL_DEFAULTS))

    assert "Suggested: /dev/ttyACM0 (last used): type l to use it" in capsys.readouterr().out


def test_port_that_will_not_open_is_asked_for_again(session_settings, serial_ports, tmp_path, capsys):
    from Receiver import receiver_config

    serial_ports.wont_open = {"/dev/ttyUSB0", "/dev/ttyUSB9"}
    # the default is unplugged; then a typo; then the right port
    ask = answering(*ALL_DEFAULTS, "/dev/ttyUSB9", "/dev/ttyUSB1")
    connection = start_receiver(ask)

    assert connection == ("connection", "/dev/ttyUSB1")
    assert receiver_config.serialPort == "/dev/ttyUSB1"
    assert ask.prompts[-2:] == ["Serial port [ default: /dev/ttyUSB0 ]: "] * 2
    out = capsys.readouterr().out
    assert "Cannot open serial port /dev/ttyUSB0" in out and "Cannot open serial port /dev/ttyUSB9" in out
    assert "Opened /dev/ttyUSB1 at 115200 baud" in out
    # only the port that opened is saved
    assert "SERIAL_PORT=/dev/ttyUSB1" in (tmp_path / ".env").read_text()


def test_enter_tries_the_default_port_again(session_settings, serial_ports):
    """e.g. the XBee was plugged in after the first try."""
    from Receiver.LiveTelemetry import open_serial_port, prompt_settings

    answers = prompt_settings(answering(*ALL_DEFAULTS))
    serial_ports.wont_open = {"/dev/ttyUSB0"}

    def plug_in_then_enter(prompt):
        serial_ports.wont_open.clear()
        return ""

    assert open_serial_port(answers, plug_in_then_enter) == ("connection", "/dev/ttyUSB0")


def test_settings_are_not_saved_until_the_port_opens(session_settings, serial_ports, tmp_path):
    serial_ports.wont_open = {"/dev/ttyUSB0"}
    with pytest.raises(StopIteration):  # still asking for a port that opens
        start_receiver(answering(*ALL_DEFAULTS))

    assert not (tmp_path / ".env").exists()


def test_port_that_will_not_open_without_keyboard_input_exits(session_settings, serial_ports):
    from Receiver.LiveTelemetry import open_serial_port, prompt_settings

    answers = prompt_settings(answering(*ALL_DEFAULTS))
    serial_ports.wont_open = {"/dev/ttyUSB0"}

    def no_input(prompt):
        raise EOFError

    with pytest.raises(SystemExit) as exited:
        open_serial_port(answers, no_input)
    assert "there is no keyboard input" in exited.value.code


def test_baud_rate_other_than_115200_gives_a_warning(session_settings, serial_ports, monkeypatch, capsys):
    monkeypatch.setattr("Receiver.receiver_config.serialBaud", 9600)
    start_receiver(answering(*ALL_DEFAULTS))

    assert serial_ports.opened == [("/dev/ttyUSB0", 9600)]
    out = capsys.readouterr().out
    assert "Warning: serialBaud in Receiver/config.yml is 9600, not 115200" in out
    assert "tools/check_xbee_settings.py" in out


def test_no_baud_rate_warning_at_115200(session_settings, capsys):
    start_receiver(answering(*ALL_DEFAULTS))

    assert "Warning: serialBaud" not in capsys.readouterr().out
