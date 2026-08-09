from Receiver.frame_reader import END_OF_FRAME_MARKER, read_frames


def test_read_frames_splits_on_the_marker(tmp_path):
    # arrange
    capture = tmp_path / "capture.BIN"
    capture.write_bytes(
        b"\x01\x02" + END_OF_FRAME_MARKER + b"\x03\x04\x05" + END_OF_FRAME_MARKER
    )

    # act
    frames = read_frames(capture)

    # assert - trailing marker leaves an empty final frame
    assert frames == [b"\x01\x02", b"\x03\x04\x05", b""]


def test_read_frames_keeps_newlines_inside_a_frame(tmp_path):
    """Captures are read as bytes: 0x0A is data, not a line ending."""
    # arrange
    capture = tmp_path / "capture.BIN"
    capture.write_bytes(b"\x01\x0A\x02" + END_OF_FRAME_MARKER + b"\x03")

    # act
    frames = read_frames(capture)

    # assert
    assert frames == [b"\x01\x0A\x02", b"\x03"]


def test_read_frames_on_a_real_capture(mppt_bytes, request):
    # act
    frames = read_frames(request.config.rootdir + "/Tests/data/MPPT.BIN")

    # assert - matches what the fixture hands the rest of the suite
    assert frames == mppt_bytes
    assert not any(END_OF_FRAME_MARKER in frame for frame in frames)
