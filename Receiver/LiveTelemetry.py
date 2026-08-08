import serial
from Receiver.telemetry_storer import store_data, end_session
import atexit
import signal

SERIALPORT = '/dev/ttyUSB0' # Raspberry Pi
#SERIALPORT = '/dev/cu.usbmodem14101' # macOS
#SERIALPORT = 'COM8' #Windows
BAUD = 115200

serialConnection = serial.Serial(SERIALPORT, BAUD)
EndOfFrameMarker = b'\x7E'
#StartOfFrameMarker
#frameReadInProgress: bool = False
frameBuffer: bytearray = bytearray()

#trying to exit gracefully
keepLooping = True
def onProgramExit():
    global keepLooping
    keepLooping = False
def sigintHandler(sig, frame):
    onProgramExit()
atexit.register(onProgramExit)
signal.signal(signal.SIGINT, sigintHandler)

#Radio listen loop
while keepLooping:
    if serialConnection.in_waiting: #in_waiting returns number of bytes ready to be processed. If greater than 0, process data
        inputByte = serialConnection.read(size = 1)  # Read byte
        #print("reading byte: " + str(inputByte))

        if inputByte == EndOfFrameMarker:
            store_data(frameBuffer)
            frameBuffer = bytearray()  # reset buffer
        else:
            frameBuffer.extend(inputByte)

end_session()
serialConnection.close()
print("Exiting live telemetry")
