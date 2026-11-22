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
