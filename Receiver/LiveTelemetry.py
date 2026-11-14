import serial
from Receiver.frame_reader import END_OF_FRAME_MARKER, FrameAssembler
from Receiver.telemetry_storer import store_data, end_session
import atexit
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
    its last piece arrives; a piece that cannot be completed is stored
    unchanged and reported as a CRC failure, as before.
    """
    assembler = FrameAssembler()
    frameBuffer = bytearray()
    while keep_running():
        if connection.in_waiting: #in_waiting returns number of bytes ready to be processed. If greater than 0, process data
            for byte in connection.read(connection.in_waiting):
                if byte == END_OF_FRAME_MARKER[0]:
                    for frame in assembler.push(frameBuffer):
                        store(frame)
                    frameBuffer = bytearray()  # reset buffer
                else:
                    frameBuffer.append(byte)
    for frame in assembler.flush():  # pieces held back when the loop stopped
        store(frame)
    return assembler.rejoined


if __name__ == "__main__":
    atexit.register(onProgramExit)
    signal.signal(signal.SIGINT, sigintHandler)

    serialConnection = serial.Serial(SERIALPORT, BAUD)
    rejoined = receive(serialConnection)

    end_session()
    serialConnection.close()
    print(f"Exiting live telemetry ({rejoined} frames split by an unescaped 0x7E were re-joined)")
