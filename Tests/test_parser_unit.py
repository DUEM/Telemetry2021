"""Unit tests for TelemetryParser core functionality."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest



class TestTelemetryParserTime:
    """Tests for time handling in TelemetryParser."""

    def test_get_time_basic(self, run_in_receiver, patch_receiver_config):
        """Test basic time calculation with no overflow."""
        from Receiver.telemetry_parser import TelemetryParser
        import numpy as np

        # Arrange
        parser = TelemetryParser()
        parser.last_gps_time = datetime(
            year=2024, month=1, day=15, hour=10, minute=0, second=0, tzinfo=timezone.utc
        )
        parser.time_fetched = np.uint32(0)

        # Act
        result_time = parser._TelemetryParser__get_time(np.uint32(1000))  # 1 second later

        # Assert
        expected_time = datetime(
            year=2024, month=1, day=15, hour=10, minute=0, second=1, tzinfo=timezone.utc
        )
        assert result_time == expected_time

    def test_get_time_with_milliseconds(self, run_in_receiver, patch_receiver_config):
        """Test time calculation with millisecond precision."""
        from Receiver.telemetry_parser import TelemetryParser
        import numpy as np

        # Arrange
        parser = TelemetryParser()
        parser.last_gps_time = datetime(
            year=2024, month=1, day=15, hour=10, minute=0, second=0, tzinfo=timezone.utc
        )
        parser.time_fetched = np.uint32(0)

        # Act
        result_time = parser._TelemetryParser__get_time(np.uint32(1500))  # 1.5 seconds

        # Assert
        expected_time = datetime(
            year=2024,
            month=1,
            day=15,
            hour=10,
            minute=0,
            second=1,
            microsecond=500000,
            tzinfo=timezone.utc,
        )
        assert result_time == expected_time

    def test_get_time_with_overflow(self, run_in_receiver, patch_receiver_config):
        """Test time calculation with uint32 overflow wraparound."""
        from Receiver.telemetry_parser import TelemetryParser
        import numpy as np

        # Arrange
        parser = TelemetryParser()
        parser.last_gps_time = datetime(
            year=2024, month=1, day=15, hour=10, minute=0, second=0, tzinfo=timezone.utc
        )
        # Set time_fetched to a value close to uint32 max
        parser.time_fetched = np.uint32(2**32 - 1000)

        # Act: Pass a value that wraps around (e.g., 100)
        # This simulates: received_millis (100) < time_fetched (close to max)
        result_time = parser._TelemetryParser__get_time(np.uint32(100))

        # Assert: Should handle overflow correctly
        # Delta should be 100 - (2^32 - 1000) + 2^32 = 1100 ms
        expected_time = datetime(
            year=2024,
            month=1,
            day=15,
            hour=10,
            minute=0,
            second=1,
            microsecond=100000,
            tzinfo=timezone.utc,
        )
        assert result_time == expected_time


class TestTelemetryParserCRC:
    """Tests for CRC validation in TelemetryParser."""

    def test_check_crc_valid(self, run_in_receiver, patch_receiver_config):
        """Test CRC check with valid CRC."""
        from Receiver.telemetry_parser import TelemetryParser

        # Arrange
        parser = TelemetryParser()
        # Valid message: time (4) + can_id (2) + dlc (1) + data (8) + crc (2)
        msg_bytes = bytearray(b'\x00\x00\x00\x00\x01\x05\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')

        # Recalculate expected CRC
        from crccheck.crc import Crc16Modbus

        data = msg_bytes[0:-2]
        crc = Crc16Modbus.calc(data)
        msg_bytes[-2:] = crc.to_bytes(2, 'big')

        # Act
        result = parser._TelemetryParser__check_crc(msg_bytes)

        # Assert
        assert result is True

    def test_check_crc_invalid(self, run_in_receiver, patch_receiver_config):
        """Test CRC check with corrupted data."""
        from Receiver.telemetry_parser import TelemetryParser

        # Arrange
        parser = TelemetryParser()
        # Create a message with intentionally wrong CRC
        msg_bytes = bytearray(b'\x00\x00\x00\x00\x01\x05\x08\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF')

        # Act
        result = parser._TelemetryParser__check_crc(msg_bytes)

        # Assert
        assert result is False


class TestTelemetryParserGPS:
    """Tests for GPS time update logic."""

    def test_update_last_gps_time_valid(self, run_in_receiver, patch_receiver_config):
        """Test GPS time update with valid GPS data."""
        from Receiver.telemetry_parser import TelemetryParser
        import numpy as np

        # Arrange
        parser = TelemetryParser()
        gps_message = {
            "GpsHour": 14,
            "GpsMinute": 30,
            "GpsSeconds": 45,
            "GpsDay": 15,
            "GpsMonth": 1,
            "GpsYear": 24,  # Year - 2000
        }

        # Act
        parser.update_last_gps_time(gps_message, np.uint32(5000))

        # Assert
        expected_time = datetime(
            year=2024, month=1, day=15, hour=14, minute=30, second=45, tzinfo=timezone.utc
        )
        assert parser.last_gps_time == expected_time
        assert parser.time_fetched == np.uint32(5000)

    def test_update_last_gps_time_invalid(self, run_in_receiver, patch_receiver_config):
        """Test GPS time update with invalid values (should not crash)."""
        from Receiver.telemetry_parser import TelemetryParser
        import numpy as np

        # Arrange
        parser = TelemetryParser()
        original_time = parser.last_gps_time
        gps_message = {
            "GpsHour": 25,  # Invalid hour
            "GpsMinute": 30,
            "GpsSeconds": 45,
            "GpsDay": 15,
            "GpsMonth": 1,
            "GpsYear": 24,
        }

        # Act & Assert - should log error but not crash
        parser.update_last_gps_time(gps_message, np.uint32(5000))
        # Time should not have been updated
        assert parser.last_gps_time == original_time


class TestDbcDecoderAsciiSignals:
    """Tests for signals the dbc marks with the "ascii" unit."""

    @pytest.mark.parametrize(
        "can_id, signal, char",
        [(248, "GpsLat", "N"), (249, "GpsLon", "W")],
    )
    def test_hemisphere_decodes_to_str(
        self, run_in_receiver, patch_receiver_config, can_id, signal, char
    ):
        """GPS hemisphere indicators decode to a str, not an int or bytes.

        The storers depend on this: a str is quoted by influx line protocol and
        written as text by openpyxl and the csv writers. An int would silently
        write 78 instead of N, and bytes would leak a b'N' repr into the csv.
        Fails if the dbc loses the "ascii" unit on these signals.
        """
        import struct
        from Receiver.can_dbc_decoder import DbcDecoder

        # Arrange - message is a 4 byte float coordinate plus a 1 byte char
        decoder = DbcDecoder()
        msg_bytes = struct.pack("<fc", 5427.34, char.encode())

        # Act
        _, _, decoded = decoder.decode_can_msg(can_id, msg_bytes)

        # Assert
        assert decoded[signal] == char
        assert isinstance(decoded[signal], str)



def make_frame(can_id, data, dlc=None, extra=b"", millis=1000):
    """A frame as the board sends it (without the end of frame marker), with a valid CRC.

    Format: millis (4 bytes, little-endian), CAN ID (2, big-endian), DLC (1),
    data, then `extra` bytes the DLC does not cover, then CRC16 (2, big-endian).
    """
    from crccheck.crc import Crc16Modbus

    body = (
        millis.to_bytes(4, "little")
        + can_id.to_bytes(2, "big")
        + bytes([len(data) if dlc is None else dlc])
        + bytes(data)
        + extra
    )
    return bytearray(body + Crc16Modbus.calc(body).to_bytes(2, "big"))


class TestTelemetryParserFrameLength:
    """The decoder gets exactly the DLC's data bytes: never the CRC after them."""

    def test_zero_length_message_does_not_decode_the_crc(self, run_in_receiver, patch_receiver_config):
        # MPPT poll requests (0x711) carry no data. The CRC bytes used to be
        # passed to the decoder and stored as a 'Blank' signal.
        from Receiver.telemetry_parser import TelemetryParser

        name, source, body, _, crc_ok = TelemetryParser().translate_msg(make_frame(0x711, b""))

        assert (name, source, body, crc_ok) == ("MpptPollJaved", "Telemetry", {}, True)

    def test_data_bytes_are_decoded_exactly(self, run_in_receiver, patch_receiver_config):
        from Receiver.telemetry_parser import TelemetryParser

        data = [0xFF, 0xFF, 0x00, 0x66, 0x01, 0x00, 0x00, 0x00]
        _, _, body, _, _ = TelemetryParser().translate_msg(make_frame(0x111, data))

        assert list(body.values()) == data

    def test_more_bytes_than_the_dlc_is_an_error(self, run_in_receiver, patch_receiver_config):
        # e.g. in ESC_2026_0638AM.BIN: a velocity frame that lost its end, run
        # together with a whole 0x300 frame, passed the CRC by chance. Decoding
        # its first DLC bytes would store a nonsense velocity.
        from Receiver.telemetry_parser import TelemetryParser

        frame = make_frame(0x303, [0x00, 0x7C, 0xAC, 0x86, 0x00, 0x03, 0x00, 0x08], extra=b"\x03\x40\x00\x00")
        name, source, body, _, crc_ok = TelemetryParser().translate_msg(frame)

        assert (name, source, crc_ok) == ("DLC MISMATCH", "ERROR", True)
        assert body == {"ID": 0x303, "DLC": 8, "Bytes": 12}

    def test_fewer_bytes_than_the_dlc_is_an_error(self, run_in_receiver, patch_receiver_config):
        from Receiver.telemetry_parser import TelemetryParser

        frame = make_frame(0x111, [1, 2, 3, 4, 5], dlc=8)
        name, source, body, _, crc_ok = TelemetryParser().translate_msg(frame)

        assert (name, source, crc_ok) == ("DLC MISMATCH", "ERROR", True)
        assert body == {"ID": 0x111, "DLC": 8, "Bytes": 5}

    def test_fewer_bytes_than_the_dbc_message_is_a_decode_error(self, run_in_receiver, patch_receiver_config):
        # MPPT status (0x771) is 7 bytes in the dbc; a consistent 2 byte frame
        # used to be padded out with the CRC bytes and decoded as garbage.
        from Receiver.telemetry_parser import TelemetryParser

        name, source, body, _, _ = TelemetryParser().translate_msg(make_frame(0x771, [1, 2]))

        assert (name, source, body) == ("DECODE ERROR", "ERROR", {"ID": 0x771, "DLC": 2})


def test_hex2influx_skips_messages_without_fields():
    from tools.hex2influx import to_point

    assert to_point("MpptPollJaved", "Telemetry", {}, datetime(2026, 1, 1, tzinfo=timezone.utc), True) == ""


class TestTelemetryParserGpsDate:
    """GPS time messages (0x0F6) set the clock only when their date is plausible.

    Frames from /run/media/toby/TOBYKEY/DUSC/data/BIN/Test12092006.BIN (12 September 2026).
    """

    # GPS module's default date before it has the date from the satellites: 2080-01-06, no fix
    DEFAULT_2080 = "9f 24 01 00 00 f6 08 0f 0b 06 0c 01 50 00 00 64 d0"
    # correct date and time (2026-09-12 15:12:18) before a position fix
    NO_FIX_2026 = "04 3e 02 00 00 f6 08 0f 0c 12 0c 09 1a 00 00 74 43"
    # correct date and time (2026-09-12 15:15:00) with a position fix
    FIX_2026 = "40 b7 04 00 00 f6 08 0f 0f 00 0c 09 1a 01 01 ea 76"

    @staticmethod
    def frame(hex_string):
        return bytearray.fromhex(hex_string)

    def test_default_2080_date_does_not_set_the_clock(self, run_in_receiver, patch_receiver_config):
        from Receiver.telemetry_parser import TelemetryParser

        parser = TelemetryParser()
        before = parser.last_gps_time

        name, _, body, _, _ = parser.translate_msg(self.frame(self.DEFAULT_2080))

        assert name == "TimeAndFix" and body["GpsYear"] == 80 and body["GpsFix"] == 0
        assert parser.last_gps_time == before
        assert parser.time_fetched == 0

    def test_date_without_a_position_fix_sets_the_clock(self, run_in_receiver, patch_receiver_config):
        from Receiver.telemetry_parser import TelemetryParser

        parser = TelemetryParser()
        parser.translate_msg(self.frame(self.NO_FIX_2026))

        assert parser.last_gps_time == datetime(2026, 9, 12, 15, 12, 18, tzinfo=timezone.utc)

    def test_default_date_after_a_valid_one_keeps_the_valid_clock(self, run_in_receiver, patch_receiver_config):
        from Receiver.telemetry_parser import TelemetryParser

        parser = TelemetryParser()
        parser.translate_msg(self.frame(self.FIX_2026))      # board millis 0x04b740
        parser.translate_msg(self.frame(self.DEFAULT_2080))

        assert parser.last_gps_time == datetime(2026, 9, 12, 15, 15, 0, tzinfo=timezone.utc)
        # a later message (board status, 1 s after the valid date) is timestamped from it, not from 2080
        _, _, _, msg_time, _ = parser.translate_msg(
            make_frame(0x111, [1, 255, 255, 103, 0, 0, 0, 0], millis=0x04B740 + 1000)
        )
        assert msg_time == datetime(2026, 9, 12, 15, 15, 1, tzinfo=timezone.utc)

    def test_rejected_dates_are_logged_once_per_run(self, run_in_receiver, patch_receiver_config, caplog):
        from Receiver.telemetry_parser import TelemetryParser

        parser = TelemetryParser()
        for hex_string in (self.DEFAULT_2080, self.DEFAULT_2080, self.FIX_2026, self.DEFAULT_2080):
            parser.translate_msg(self.frame(hex_string))

        assert caplog.text.count("Ignoring implausible GPS date") == 2
