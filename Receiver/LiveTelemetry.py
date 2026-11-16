import serial
from Receiver.frame_reader import END_OF_FRAME_MARKER, FrameAssembler
from Receiver.serial_port import DEFAULT_BAUD, describe_port, get_port_and_baud, list_serial_ports, save_settings
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

# The serial port and baud rate are asked for at start up and saved in
# Receiver/serial.env. The baud rate must match the XBee's (115200).

def cannot_open_hint(port, e):
    """What to check when serial port `port` could not be opened (error `e`)."""
    if e.errno == errno.ENOENT:
        return (
            f"{port} does not exist. Check the XBee's USB adapter is plugged in "
            "and pick its port from the list above (Windows: Device Manager > "
            "Ports). For a software-in-the-loop replay, start socat first so "
            "that it creates the port."
        )
    if e.errno == errno.EACCES:
        return (
            f"No permission to open {port}. On Linux, add yourself to the group "
            "that owns it (usually dialout: sudo usermod -aG dialout $USER), then "
            "log out and back in."
        )
    return (
        f"Check that {port} is the XBee's port and that no other program "
        "(XCTU, a serial monitor, another receiver) has it open."
    )


def open_serial_port(suggested, reason, baud):
    """Ask for a serial port until one opens. Enter uses the suggested port.

    Returns (connection, port). Only opening the port is inside the try, so
    this catches a wrong port name or an unplugged radio, nothing else.
    """
    while True:
        if suggested:
            typed = input(f"Use {suggested} ({reason})? Press Enter to use it, or type another port: ")
        else:
            typed = input("Type the serial port to use: ")
        port = typed.strip() or suggested
        if not port:
            continue  # nothing suggested and nothing typed: ask again

        try:
            connection = serial.Serial(port, baud)
        except serial.SerialException as e:  # wrong name, unplugged, in use, no permission
            logging.warning(f"Cannot open serial port {port}: {e}\n{cannot_open_hint(port, e)}")
            continue  # ask again
        return connection, port


def ask_baud(suggested):
    """Ask for the baud rate. Enter uses the suggested rate."""
    while True:
        typed = input(f"Use a baud rate of {suggested}? Press Enter to use it, or type another: ").strip()
        if not typed:
            return suggested
        if typed.isdigit():
            return int(typed)
        logging.warning(f"'{typed}' is not a number")


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


if __name__ == "__main__":
    #list the serial ports and ask which one to use, before anything else
    ports = list_serial_ports()
    logging.info("Serial ports found:")
    for p in ports:
        logging.info(f"  {describe_port(p)}")
    if not ports:
        logging.info("no ports found")
    suggested, reason, baud = get_port_and_baud(ports)

    # asks again until the port opens; Ctrl-C here quits as normal
    serialConnection, port = open_serial_port(suggested, reason, baud)

    # the rate can be changed on an open port, so a port that fails to open
    # doesn't make you answer this again
    baud = ask_baud(baud)
    serialConnection.baudrate = baud
    if baud != DEFAULT_BAUD:
        # a wrong rate gives no error, only CRC FAIL frames
        logging.warning(f"{baud} is not {DEFAULT_BAUD}: it must match the XBee's baud rate (BD). "
                        "If every frame is CRC FAIL, check with tools/check_xbee_settings.py")
    logging.info(f"Opened {port} at {baud} baud")

    # save only once the port has opened, so a mistyped port is never suggested
    try:
        save_settings(port, baud)
    except OSError as e:  # e.g. read-only checkout: not worth stopping for
        logging.warning(f"Could not save the serial port to Receiver/serial.env: {e}")

    # take over Ctrl-C only now, so it stops the receive loop cleanly
    atexit.register(onProgramExit)
    signal.signal(signal.SIGINT, sigintHandler)

    assembler = receive(serialConnection)

    end_session()
    serialConnection.close()
    print(
        f"Exiting live telemetry ({assembler.rejoined} frames split by an unescaped 0x7E "
        f"were re-joined; {assembler.split} frames run together after radio losses were split apart)"
    )
