import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fixtures import nrt_bytes, patch_receiver_config, run_in_receiver


def test_csv_storer_creates_file(tmp_path, run_in_receiver, patch_receiver_config):
    """Test that CSVStorer creates a new CSV file with headers."""
    from Receiver.storer_extension import CSVStorer

    csv_path = tmp_path / "test_output.csv"

    # Act
    storer = CSVStorer(csv_path)
    storer.close()

    # Assert
    assert csv_path.exists()
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        headers = next(reader)
        assert headers == ["Timestamp", "Source", "Item", "Message Body", "CRC"]


def test_csv_storer_writes_data(tmp_path, run_in_receiver, patch_receiver_config):
    """Test that CSVStorer writes message data correctly."""
    from Receiver.storer_extension import CSVStorer

    csv_path = tmp_path / "test_output.csv"

    # Arrange
    storer = CSVStorer(csv_path)
    msg_time = datetime(2024, 1, 15, 12, 30, 45, 123000, tzinfo=timezone.utc)
    msg_body = {
        "PackCurrent": 0,
        "PackInstVoltage": 1305,
        "PackSoc": 159,
    }

    # Act
    storer.store_data("PackParameters", "Orion", msg_body, msg_time, True)
    storer.close()

    # Assert
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        headers = next(reader)
        data_row = next(reader)

        assert data_row[0] == "2024-01-15T12:30:45.123000+00:00"
        assert data_row[1] == "Orion"
        assert data_row[2] == "PackParameters"
        assert "PackCurrent=0" in data_row[3]
        assert "PackInstVoltage=1305" in data_row[3]
        assert data_row[4] == "True"


def test_csv_storer_appends_to_existing_file(
    tmp_path, run_in_receiver, patch_receiver_config
):
    """Test that CSVStorer appends to existing CSV files without duplicating headers."""
    from Receiver.storer_extension import CSVStorer

    csv_path = tmp_path / "test_output.csv"

    # Arrange - First write
    msg_time_1 = datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
    msg_body_1 = {"field1": "value1"}

    storer = CSVStorer(csv_path)
    storer.store_data("Message1", "Source1", msg_body_1, msg_time_1, True)
    storer.close()

    # Act - Second write (append)
    msg_time_2 = datetime(2024, 1, 15, 12, 31, 45, tzinfo=timezone.utc)
    msg_body_2 = {"field2": "value2"}

    storer = CSVStorer(csv_path)
    storer.store_data("Message2", "Source2", msg_body_2, msg_time_2, False)
    storer.close()

    # Assert
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        headers = next(reader)
        assert headers == ["Timestamp", "Source", "Item", "Message Body", "CRC"]

        row1 = next(reader)
        assert row1[2] == "Message1"

        row2 = next(reader)
        assert row2[2] == "Message2"


def test_csv_storer_with_parser_integration(
    tmp_path, run_in_receiver, patch_receiver_config, nrt_bytes
):
    """Test CSVStorer integration with TelemetryParser."""
    from Receiver.storer_extension import CSVStorer
    from Receiver.telemetry_parser3 import TelemetryParser
    from Receiver.telemetry_storer import TelemetryStorer

    csv_path = tmp_path / "integration_test.csv"

    # Arrange
    parser = TelemetryParser()
    parser.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0, tzinfo=timezone.utc
    )
    csv_storer = CSVStorer(csv_path)
    storer = TelemetryStorer(parser, storage_plugin_list=[csv_storer])

    # Act
    storer.store_data(nrt_bytes[20])
    storer.end_session()

    # Assert
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        headers = next(reader)
        assert headers == ["Timestamp", "Source", "Item", "Message Body", "CRC"]

        data_row = next(reader)
        assert data_row[1] == "Orion"
        assert data_row[2] == "PackParameters"
        assert data_row[4] == "True"
