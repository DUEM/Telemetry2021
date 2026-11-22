import serial
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError
from requests.exceptions import RequestException
from Receiver import receiver_config
from Receiver.frame_reader import END_OF_FRAME_MARKER, FrameAssembler
from Receiver.telemetry_storer import store_data, end_session
import atexit
import errno
import logging
import signal
import sys
from pathlib import Path

# print every decoded CAN message (logged at INFO by telemetry_storer) to stdout
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

#trying to exit gracefully
keepLooping = True
def onProgramExit():
    global keepLooping
    keepLooping = False
def sigintHandler(sig, frame):
    onProgramExit()


def receive(connection, store=store_data, keep_running=lambda: keepLooping):
    """Radio listen loop: split the byte stream on the end of frame marker and
    pass each frame to `store`.

    The marker is not escaped inside frames, so the pieces go through a
    FrameAssembler, which re-joins frames split by a 0x7E in their timestamp,
    data or CRC (see frame_reader.py). A re-joined frame is stored as soon as
    its last piece arrives. Complete frames at the start or end of a piece
    that cannot be completed (frames run together after radio losses) are
    split off and stored; the bytes left are stored and reported as a CRC
    failure, as before. Returns the FrameAssembler, for its counts.
    """
    assembler = FrameAssembler()
    frameBuffer = bytearray()
    while keep_running():
        try:
            waiting = connection.in_waiting  # number of bytes ready to be processed
            data = connection.read(waiting) if waiting else b""
        except OSError as e:  # port gone: USB unplugged, or the SIL replay ended (serial.SerialException is an OSError)
            logging.error("Serial port lost (%s): stopping the receiver", e)
            break
        for byte in data:
            if byte == END_OF_FRAME_MARKER[0]:
                for frame in assembler.push(frameBuffer):
                    store(frame)
                frameBuffer = bytearray()  # reset buffer
            else:
                frameBuffer.append(byte)
    for frame in assembler.flush():  # pieces held back when the loop stopped
        store(frame)
    return assembler  # its counts: rejoined, split


def open_serial_port(port=None, baud=None):
    """Open the XBee's serial port, or exit with an explanation if it cannot
    be opened (e.g. the XBee is not plugged in). The port and baud rate are
    serialPort and serialBaud in Receiver/config.yml unless given."""
    # read at call time so monkeypatching receiver_config takes effect
    port = receiver_config.serialPort if port is None else port
    baud = receiver_config.serialBaud if baud is None else baud
    try:
        return serial.Serial(port, baud)
    except serial.SerialException as e:
        if e.errno == errno.ENOENT:
            hint = (
                f"{port} does not exist. Check the XBee's USB adapter is plugged in "
                "and find its name (Linux: ls /dev/ttyUSB* /dev/ttyACM*; macOS: "
                "ls /dev/cu.*; Windows: Device Manager > Ports), then enter it at the "
                "Serial port prompt, or set serialPort in Receiver/config.yml. For a software-in-the-loop "
                "replay, start socat first so that it creates the port."
            )
        elif e.errno == errno.EACCES:
            hint = (
                f"No permission to open {port}. On Linux, add yourself to the group "
                "that owns it (usually dialout: sudo usermod -aG dialout $USER), then "
                "log out and back in."
            )
        else:
            hint = (
                f"Check that {port} is the XBee's port and that no other program "
                "(XCTU, a serial monitor, another receiver) has it open."
            )
        sys.exit(f"Cannot open serial port {port}: {e}\n{hint}")


_TRUE_WORDS = ("true", "t", "yes", "y", "on", "1")
_FALSE_WORDS = ("false", "f", "no", "n", "off", "0")


def _shown(value):
    return str(value).lower() if isinstance(value, bool) else value


def _ask(question, default, ask, check=None, last=None):
    """Ask `question`, showing `default` (and `last`, the value used last time,
    if there is one); return the answer, or `default` if the answer is blank
    (or there is no input, e.g. stdin is not a terminal). When `last` is
    shown, d also gives the default and l gives `last`.
    `check(text)` returns (value, None) or (None, reason to ask again)."""
    if last is None:
        brackets = f"[ default: {_shown(default)} ]"
    else:
        brackets = f"[ default: {_shown(default)}, last used: {_shown(last)} ]"
    while True:
        try:
            answer = ask(f"{question} {brackets}: ").strip()
        except EOFError:  # no input: use the default
            print()
            return default
        if not answer:
            return default
        if last is not None and answer.lower() == "d":
            return default
        if last is not None and answer.lower() == "l":
            return last
        if check is None:
            return answer
        value, problem = check(answer)
        if problem is None:
            return value
        print(f"  {problem}")


def _true_or_false(answer):
    word = answer.lower()
    if word in _TRUE_WORDS:
        return True, None
    if word in _FALSE_WORDS:
        return False, None
    return None, "Please answer true or false (or yes / no), or press Enter for the default"


def _file_name(answer):
    if any(c.isspace() for c in answer):
        return None, "The session name cannot contain spaces: use - or _ instead (e.g. race-day1)"
    if any(c in answer for c in '/\\:*?"<>|'):
        return None, 'The session name is used in file names: it cannot contain / \\ : * ? " < > |'
    return answer, None


def _create_or_default(answer):
    word = answer.lower()
    if word in ("create", "c"):
        return "create", None
    if word in ("default", "d"):
        return "default", None
    return None, "Please answer create (c) or default (d), or press Enter for the default"


def _continue_or_quit(ask):
    """Pause after a warning until Return (carry on) or q / Q (quit without
    starting). Any other answer asks again."""
    while True:
        try:
            answer = ask("Press Return to continue, or q to quit: ").strip()
        except EOFError:  # no input (not run from a terminal): carry on
            print()
            return
        if answer == "":
            return
        if answer.lower() == "q":
            sys.exit("Quit: the receiver was not started")
        print("  Please press Return on its own to continue, or q then Return to quit")


def check_influx_database(credentials, default_db, ask=input):
    """Check that the InfluxDB database in `credentials` exists. If it does
    not, ask whether to create it or use `default_db` (the one in
    config.yml). Returns the credentials to use."""
    db = credentials.db
    try:
        client = InfluxDBClient(
            host=credentials.host, port=credentials.port,
            username=credentials.username, password=credentials.password, timeout=5,
        )
        existing = {d["name"] for d in client.get_list_database()}
    except (RequestException, InfluxDBClientError, InfluxDBServerError, OSError) as e:
        # a connection error's text is very long: just say there was no answer
        reason = "no response" if isinstance(e, RequestException) else e
        print(
            f"  Cannot check the InfluxDB databases at {credentials.host}:{credentials.port} ({reason}). "
            "Is InfluxDB running (systemctl status influxd.service)? If you continue, data is "
            "only stored in InfluxDB once it can be reached and the database exists."
        )
        _continue_or_quit(ask)
        return credentials
    if db in existing:
        print(f"  InfluxDB database '{db}' found.")
        return credentials

    if db != default_db:
        choice = _ask(
            f"InfluxDB database '{db}' does not exist. Create it, or use the default "
            f"'{default_db}'? (create/default)",
            "default", ask, _create_or_default,
        )
        if choice == "default":
            credentials = credentials._replace(db=default_db)
            db = default_db
            if db in existing:
                print(f"  Using InfluxDB database '{db}'.")
                return credentials
            # the default does not exist either: offer to create it below
        else:
            return _create_database(client, credentials, default_db, ask)

    if _ask(f"InfluxDB database '{db}' does not exist. Create it? (true/false)", True, ask, _true_or_false):
        return _create_database(client, credentials, default_db, ask)
    print(f"  Not created: nothing will be stored in InfluxDB until database '{db}' exists.")
    return credentials


def _create_database(client, credentials, default_db, ask):
    db = credentials.db
    print(f"  Creating InfluxDB database '{db}'.")
    try:
        client.create_database(db)
    except (RequestException, InfluxDBClientError, InfluxDBServerError, OSError) as e:
        print(f"  Could not create database '{db}' ({e}).")
        if db != default_db:
            print(f"  Using the default database '{default_db}' instead.")
            return credentials._replace(db=default_db)
        return credentials
    if db != default_db:
        print(
            f"  Reminder: Grafana reads from the database set in its InfluxDB data source "
            f"(normally '{default_db}'). To see this session's data in Grafana, change the "
            f"data source's Database to '{db}' (Connections > Data sources > InfluxDB), "
            f"or add a second data source for '{db}'."
        )
        _continue_or_quit(ask)
    return credentials


# The prompted settings, as stored in the .env file of last used settings
LAST_USED_FILE_NAME = ".env"
_LAST_USED_KEYS = {
    "serialPort": "SERIAL_PORT",
    "sessionLogName": "SESSION_NAME",
    "xlsxEnabled": "EXCEL_LOGGING",
    "binEnabled": "BIN_LOGGING",
    "csvEnabled": "CSV_LOGGING",
    "influxEnabled": "INFLUX_LOGGING",
    "influxDb": "INFLUX_DATABASE",
    "influxUsername": "INFLUX_USERNAME",
    "influxPassword": "INFLUX_PASSWORD",
}


def read_last_used(path):
    """The settings in a .env file of last used settings, as {setting: text},
    or None if there is no such file. Lines are KEY=value; blank lines and
    lines starting with # are ignored, as are unknown keys."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        print(f"  Cannot read the last used settings in {path} ({e}): ignoring them")
        return None
    names = {key: name for name, key in _LAST_USED_KEYS.items()}
    found = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and not key.startswith("#") and key in names and value.strip():
            found[names[key]] = value.strip()
    return found


def write_last_used(path, values):
    """Write {setting: value} to the .env file of last used settings."""
    lines = [
        "# Telemetry receiver: the settings used the last time it was started from",
        "# this folder, offered as 'last used' at its questions. Written by",
        "# Receiver/LiveTelemetry.py. It holds the InfluxDB password: do not commit",
        "# or share it.",
    ]
    lines += [f"{key}={_shown(values[name])}" for name, key in _LAST_USED_KEYS.items() if name in values]
    try:
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"  Cannot save these settings as the last used ones in {path} ({e})")


def prompt_settings(ask=input, last_used_file=None):
    """Ask for this session's settings, with the values in Receiver/config.yml
    as the defaults (press Enter to keep one), and use the answers for this run
    of the receiver. config.yml itself is not changed. Only these settings are
    asked for; the others are always taken from config.yml. The InfluxDB
    database name and credentials are only asked for if InfluxDB is on, and
    the database is then checked (see check_influx_database).

    The answers are saved in `last_used_file` (.env in the current working
    directory, i.e. the directory the receiver was started from). If that
    file exists, each question also shows the value used last time, which l
    selects (d, like Enter, selects the default)."""
    path = Path.cwd() / LAST_USED_FILE_NAME if last_used_file is None else Path(last_used_file)
    saved = read_last_used(path)

    def last(name, check=None):
        """The last used value of a setting, or None if there is none (or it is
        not a valid answer, e.g. the file was edited by hand)."""
        if saved is None or name not in saved:
            return None
        if check is None:
            return saved[name]
        value, problem = check(saved[name])
        return None if problem else value

    cfg = receiver_config
    influx = cfg.ifCredentials
    print("Receiver settings for this session (press Enter to use the default from Receiver/config.yml)")
    if saved is not None:
        print(f"Last used settings from {path}: type l to use the last used value, d (or Enter) for the default")
    cfg.serialPort = _ask("Serial port", cfg.serialPort, ask, last=last("serialPort"))
    cfg.sessionLogName = _ask("Telemetry Session Name (no spaces)", cfg.sessionLogName, ask, _file_name,
                              last("sessionLogName", _file_name))
    cfg.xlsxEnabled = _ask("Excel logging (true/false)", cfg.xlsxEnabled, ask, _true_or_false,
                           last("xlsxEnabled", _true_or_false))
    cfg.binEnabled = _ask("BIN logging (true/false)", cfg.binEnabled, ask, _true_or_false,
                          last("binEnabled", _true_or_false))
    cfg.csvEnabled = _ask("CSV logging (true/false)", cfg.csvEnabled, ask, _true_or_false,
                          last("csvEnabled", _true_or_false))
    enabled = _ask("InfluxDB logging (true/false)", influx.enabled, ask, _true_or_false,
                   last("influxEnabled", _true_or_false))
    if enabled:  # the database and credentials are only needed with InfluxDB on
        influx = influx._replace(
            db=_ask("InfluxDB database name", influx.db, ask, last=last("influxDb")),
            username=_ask("InfluxDB username", influx.username, ask, last=last("influxUsername")),
            password=_ask("InfluxDB password", influx.password, ask, last=last("influxPassword")),
        )
        influx = check_influx_database(influx, cfg.ifCredentials.db, ask)
    cfg.ifCredentials = influx._replace(enabled=enabled)

    used = dict(saved or {})  # keeps the InfluxDB ones if not asked this time
    used.update(serialPort=cfg.serialPort, sessionLogName=cfg.sessionLogName, xlsxEnabled=cfg.xlsxEnabled,
                binEnabled=cfg.binEnabled, csvEnabled=cfg.csvEnabled, influxEnabled=enabled)
    if enabled:
        used.update(influxDb=influx.db, influxUsername=influx.username, influxPassword=influx.password)
    write_last_used(path, used)


if __name__ == "__main__":
    # before the Ctrl-C handler is installed, so Ctrl-C at a prompt still quits
    try:
        prompt_settings()
    except KeyboardInterrupt:
        sys.exit("\nCancelled: the receiver was not started")

    atexit.register(onProgramExit)
    signal.signal(signal.SIGINT, sigintHandler)

    serialConnection = open_serial_port()
    assembler = receive(serialConnection)

    end_session()
    serialConnection.close()
    print(
        f"Exiting live telemetry ({assembler.rejoined} frames split by an unescaped 0x7E "
        f"were re-joined; {assembler.split} frames run together after radio losses were split apart)"
    )
