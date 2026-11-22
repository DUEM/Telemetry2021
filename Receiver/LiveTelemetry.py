import serial
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


def prompt_settings(ask=input):
    """Ask for this session's settings, with the values in Receiver/config.yml
    as the defaults (press Enter to keep one), and use the answers for this run
    of the receiver. config.yml itself is not changed. Only these settings are
    asked for; the others are always taken from config.yml. The InfluxDB
    database name and credentials are only asked for if InfluxDB is on."""
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
