"""Unit tests for TelemetryParser core functionality."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest



class TestTelemetryParserTime:
    """Tests for time handling in TelemetryParser."""

    def test_get_time_basic(self, run_in_receiver, patch_receiver_config):
        """Test basic time calculation with no overflow."""
        from Receiver.telemetry_parser3 import TelemetryParser
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
        from Receiver.telemetry_parser3 import TelemetryParser
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
        from Receiver.telemetry_parser3 import TelemetryParser
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
        from Receiver.telemetry_parser3 import TelemetryParser

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
        from Receiver.telemetry_parser3 import TelemetryParser

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
        from Receiver.telemetry_parser3 import TelemetryParser
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
        from Receiver.telemetry_parser3 import TelemetryParser
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

