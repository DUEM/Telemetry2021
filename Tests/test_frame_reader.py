import struct

from crccheck.crc import Crc16Modbus

from Receiver.frame_reader import (
    END_OF_FRAME_MARKER,
    FrameAssembler,
    frame_is_complete,
    read_frames,
)

EOF = END_OF_FRAME_MARKER


def make_frame(millis: int, can_id: int, data: bytes) -> bytes:
    """A frame as the board writes it, without the end of frame marker."""
    body = struct.pack("<I", millis) + struct.pack(">H", can_id) + bytes([len(data)]) + data
    return body + struct.pack(">H", Crc16Modbus.calc(body))


def frame_with_marker_in_crc() -> bytes:
    for millis in range(1000, 100000):
        frame = make_frame(millis, 0x111, bytes(8))
        if EOF in frame[-2:] and EOF not in frame[:-2]:
            return frame
    raise AssertionError("no such frame in range")


def capture(*frames: bytes) -> bytes:
    """What the board writes for these frames: each followed by the marker."""
    return b"".join(f + EOF for f in frames)


def test_read_frames_splits_on_the_marker(tmp_path):
    # arrange
    capture_file = tmp_path / "capture.BIN"
    capture_file.write_bytes(
        b"\x01\x02" + END_OF_FRAME_MARKER + b"\x03\x04\x05" + END_OF_FRAME_MARKER
    )

    # act
    frames = read_frames(capture_file)

    # assert - pieces that are not frames come back unchanged; the trailing
    # marker leaves an empty final piece
    assert frames == [b"\x01\x02", b"\x03\x04\x05", b""]


def test_read_frames_keeps_newlines_inside_a_frame(tmp_path):
    """Captures are read as bytes: 0x0A is data, not a line ending."""
    # arrange
    capture_file = tmp_path / "capture.BIN"
    capture_file.write_bytes(b"\x01\x0A\x02" + END_OF_FRAME_MARKER + b"\x03")

    # act
    frames = read_frames(capture_file)

    # assert
    assert frames == [b"\x01\x0A\x02", b"\x03"]


def test_frame_is_complete():
    frame = make_frame(1234, 0x700, bytes(range(8)))
    assert frame_is_complete(frame)
    assert frame_is_complete(make_frame(1234, 0x711, b""))  # MPPT poll, DLC 0
    assert not frame_is_complete(frame[:-1])  # shorter than its DLC says
    assert not frame_is_complete(frame + b"\x00")  # longer than its DLC says
    assert not frame_is_complete(frame[:-1] + bytes([frame[-1] ^ 1]))  # bad CRC
    assert not frame_is_complete(b"")


def test_complete_frames_pass_through_unchanged(tmp_path):
    # arrange
    frames = [make_frame(1000 + i, 0x303, bytes([i] * 8)) for i in range(5)]
    capture_file = tmp_path / "capture.BIN"
    capture_file.write_bytes(capture(*frames))

    # act / assert
    assert read_frames(capture_file) == frames + [b""]


def test_marker_in_timestamp_is_rejoined(tmp_path):
    # arrange - millis 0x00147E4E is written 4e 7e 14 00
    split = make_frame(0x00147E4E, 0x701, bytes(range(8)))
    assert EOF in split[:4]
    before, after = make_frame(0x00147E00, 0x700, bytes(8)), make_frame(0x00147F00, 0x111, bytes(8))
    capture_file = tmp_path / "capture.BIN"
    capture_file.write_bytes(capture(before, split, after))

    # act / assert
    assert read_frames(capture_file) == [before, split, after, b""]


def test_marker_in_data_is_rejoined():
    frame = make_frame(5000, 0x303, b"\x00\x7e\x01\x02\x03\x04\x05\x06")
    assert frame_is_complete(frame)
    assert read_pieces(capture(frame)) == [frame, b""]


def test_marker_in_crc_is_rejoined():
    frame = frame_with_marker_in_crc()
    assert read_pieces(capture(frame)) == [frame, b""]


def test_two_markers_in_one_frame_are_rejoined():
    # adjacent (an empty piece between them) and apart
    adjacent = make_frame(6000, 0x301, b"\x01\x7e\x7e\x02\x03\x04\x05\x06")
    apart = make_frame(7000, 0x301, b"\x7e\x01\x02\x7e\x03\x04\x05\x06")
    assert read_pieces(capture(adjacent, apart)) == [adjacent, apart, b""]


def test_complete_frame_is_never_absorbed_into_a_join():
    """A damaged piece is returned unchanged, then the next frame as it was."""
    damaged = b"\x01\x02\x03\x04\x05"
    good = make_frame(8000, 0x111, bytes(8))
    assert read_pieces(damaged + EOF + capture(good)) == [damaged, good, b""]


def test_damaged_piece_does_not_stop_a_later_split_frame_being_rejoined():
    damaged = b"\xaa\xbb"
    split = make_frame(9000, 0x303, b"\x7e\x01\x02\x03\x04\x05\x06\x07")
    assert read_pieces(damaged + EOF + capture(split)) == [damaged, split, b""]


def test_assembler_streams_pieces_as_they_arrive():
    # arrange
    split = make_frame(0x00147E4E, 0x701, bytes(range(8)))
    good = make_frame(0x00148000, 0x111, bytes(8))
    first, second = split.split(EOF)
    assembler = FrameAssembler()

    # act / assert - an incomplete piece is held until it can be decided
    assert assembler.push(good) == [good]
    assert assembler.push(first) == []
    assert assembler.push(second) == [split]
    assert assembler.rejoined == 1
    assert assembler.flush() == []


def test_assembler_gives_up_once_a_join_would_be_too_long():
    """Pieces longer than any frame are not held back waiting for more."""
    assembler = FrameAssembler()
    garbage = bytes(range(20))
    assert assembler.push(garbage) == [garbage]


def test_assembler_flush_returns_held_pieces_in_order():
    assembler = FrameAssembler()
    assert assembler.push(b"\x01") == []
    assert assembler.push(b"\x02") == []
    assert assembler.flush() == [b"\x01", b"\x02"]


def test_read_frames_on_a_real_capture(mppt_bytes, request):
    # act
    path = request.config.rootdir + "/Tests/data/MPPT.BIN"
    frames = read_frames(path)
    pieces = open(path, "rb").read().split(END_OF_FRAME_MARKER)

    # assert - matches what the fixture hands the rest of the suite
    assert frames == mppt_bytes
    # MPPT.BIN has three frames split by a 0x7E; each comes back whole, so
    # every frame is now complete apart from the empty piece after the last marker
    assert len(pieces) - len(frames) == 3
    assert [f for f in frames if not frame_is_complete(f)] == [b""]
    assert sum(EOF in f for f in frames) == 3


def read_pieces(data: bytes) -> list:
    assembler = FrameAssembler()
    out = []
    for piece in data.split(EOF):
        out.extend(assembler.push(piece))
    return out + assembler.flush()
