import serial
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

SERIALPORT = '/dev/ttyUSB0' # Raspberry Pi
#SERIALPORT = '/dev/cu.usbmodem14101' # macOS
#SERIALPORT = 'COM8' #Windows
BAUD = 115200

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


def open_serial_port(port=SERIALPORT, baud=BAUD):
    """Open the XBee's serial port, or exit with an explanation if it cannot
    be opened (e.g. the XBee is not plugged in)."""
    try:
        return serial.Serial(port, baud)
    except serial.SerialException as e:
        if e.errno == errno.ENOENT:
            hint = (
                f"{port} does not exist. Check the XBee's USB adapter is plugged in "
                "and find its name (Linux: ls /dev/ttyUSB* /dev/ttyACM*; macOS: "
                "ls /dev/cu.*; Windows: Device Manager > Ports), then set SERIALPORT "
                "at the top of Receiver/LiveTelemetry.py. For a software-in-the-loop "
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


if __name__ == "__main__":
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
