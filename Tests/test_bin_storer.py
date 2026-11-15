import re

import pytest

from Receiver.frame_reader import END_OF_FRAME_MARKER, read_frames


def test_bin_storer_writes_each_frame_with_its_marker(tmp_path):
    """Frames are written as received, each followed by 0x7E, whatever their CRC."""
    from Receiver.storer_extension import BinStorer

    path = tmp_path / "raw.BIN"
    storer = BinStorer(path)

    storer.store_raw(b"\x01\x02\x03")
    storer.store_raw(bytearray(b"\x04\x7e\x05"))  # a re-joined frame keeps its 0x7E
    storer.store_data("Item", "Source", {}, None, False)  # decoded data is ignored
    storer.close()

    assert path.read_bytes() == b"\x01\x02\x03\x7e\x04\x7e\x05\x7e"


def test_bin_storer_appends_to_an_existing_file(tmp_path):
    from Receiver.storer_extension import BinStorer

    path = tmp_path / "raw.BIN"
    path.write_bytes(b"\xaa\x7e")
    storer = BinStorer(path)
    storer.store_raw(b"\xbb")
    storer.close()

    assert path.read_bytes() == b"\xaa\x7e\xbb\x7e"


@pytest.mark.parametrize("capture", ["NRT.BIN", "MPPT.BIN"])
def test_live_bin_log_matches_what_was_received(request, monkeypatch, capture):
    """Replaying a capture through the live receiver with BIN output on gives
    back the same bytes, up to the last end of frame marker, in
    session-logs/BIN/telem-received-<date>-<time>.BIN (in tmp_path for the tests)."""
    from Receiver import receiver_config
    from Receiver.LiveTelemetry import receive
    from Receiver.telemetry_storer import store_data, end_session
    from test_live_telemetry import FakeSerial

    monkeypatch.setattr("Receiver.receiver_config.binEnabled", True)
    data = open(f"{request.config.rootdir}/Tests/data/{capture}", "rb").read()
    port = FakeSerial(data, chunk=64)

    receive(port, store=store_data, keep_running=lambda: not port.finished())
    end_session()

    (bin_path,) = receiver_config.binOutputFolder.iterdir()
    assert re.fullmatch(r"telem-received-\d{4}-\d{2}-\d{2}-\d{6}\.BIN", bin_path.name)
    # bytes after the last marker are an unfinished frame, never stored
    last_marker = data.rfind(END_OF_FRAME_MARKER)
    assert bin_path.read_bytes() == data[: last_marker + 1]
    # and the log decodes to the same frames as the original
    assert read_frames(bin_path)[:-1] == read_frames(
        f"{request.config.rootdir}/Tests/data/{capture}"
    )[:-1]


def test_bin_output_off_by_default(nrt_bytes):
    from Receiver import receiver_config
    from Receiver.telemetry_storer import store_data, end_session

    store_data(nrt_bytes[26])
    end_session()

    assert not receiver_config.binOutputFolder.exists()
