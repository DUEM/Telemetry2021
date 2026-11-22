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


def _ask(question, default, ask, check=None):
    """Ask `question`, showing `default`; return the answer, or `default` if
    the answer is blank (or there is no input, e.g. stdin is not a terminal).
    `check(text)` returns (value, None) or (None, reason to ask again)."""
    shown = str(default).lower() if isinstance(default, bool) else default
    while True:
        try:
            answer = ask(f"{question} [ default: {shown} ]: ").strip()
        except EOFError:  # no input: use the default
            print()
            return default
        if not answer:
            return default
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
    return None, "Please answer create or default, or press Enter for the default"


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


def prompt_settings(ask=input):
    """Ask for this session's settings, with the values in Receiver/config.yml
    as the defaults (press Enter to keep one), and use the answers for this run
    of the receiver. config.yml itself is not changed. Only these settings are
    asked for; the others are always taken from config.yml. The InfluxDB
    database name and credentials are only asked for if InfluxDB is on, and
    the database is then checked (see check_influx_database)."""
    cfg = receiver_config
    influx = cfg.ifCredentials
    print("Receiver settings for this session (press Enter to use the default from Receiver/config.yml)")
    cfg.serialPort = _ask("Serial port", cfg.serialPort, ask)
    cfg.sessionLogName = _ask("Telemetry Session Name (no spaces)", cfg.sessionLogName, ask, _file_name)
    cfg.xlsxEnabled = _ask("Excel logging (true/false)", cfg.xlsxEnabled, ask, _true_or_false)
    cfg.binEnabled = _ask("BIN logging (true/false)", cfg.binEnabled, ask, _true_or_false)
    cfg.csvEnabled = _ask("CSV logging (true/false)", cfg.csvEnabled, ask, _true_or_false)
    enabled = _ask("InfluxDB logging (true/false)", influx.enabled, ask, _true_or_false)
    if enabled:  # the database and credentials are only needed with InfluxDB on
        influx = influx._replace(
            db=_ask("InfluxDB database name", influx.db, ask),
            username=_ask("InfluxDB username", influx.username, ask),
            password=_ask("InfluxDB password", influx.password, ask),
        )
        influx = check_influx_database(influx, cfg.ifCredentials.db, ask)
    cfg.ifCredentials = influx._replace(enabled=enabled)


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
