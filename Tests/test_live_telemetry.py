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
    rejoined = receive(port, store=stored.append, keep_running=lambda: not port.finished())

    # assert - the offline reader also returns the bytes after the last marker
    # (empty if the capture ends with one); the live receiver waits for its marker
    offline = read_frames(path)
    assert offline[-1] == data.split(END_OF_FRAME_MARKER)[-1]
    assert stored == offline[:-1]
    # complete pieces never contain the marker, so these are the re-joined frames
    assert rejoined == sum(END_OF_FRAME_MARKER in f for f in stored) > 0


def test_receive_flushes_a_held_piece_when_stopped():
    """A piece waiting for more data is still stored when the receiver stops."""
    from Receiver.LiveTelemetry import receive

    port = FakeSerial(b"\x01\x02\x03" + END_OF_FRAME_MARKER + b"\x04\x05", chunk=64)
    stored = []

    receive(port, store=stored.append, keep_running=lambda: not port.finished())

    # the bytes after the last marker are an unfinished frame and are not stored
    assert stored == [b"\x01\x02\x03"]
