from datetime import timezone, datetime
from typing import NamedTuple
from unittest.mock import MagicMock

import pytest
from influxdb import InfluxDBClient


@pytest.fixture(scope="function")
def mock_influxdb_client(monkeypatch):
    mock_client_class = MagicMock(
        spec=InfluxDBClient
    )
    # patch where the name is looked up, not where it is defined
    monkeypatch.setattr(
        "Receiver.storer_extension.InfluxDBClient", mock_client_class
    )
    mock_client_instance = mock_client_class.return_value

    return mock_client_class, mock_client_instance


def test_data_written_to_influx(
    monkeypatch, nrt_bytes,  run_in_receiver, patch_receiver_config, mock_influxdb_client,
):
    # arrange
    class influxCredentials(NamedTuple):
        username: str = "mock"
        password: str = "mockmockmock"
        db: str = "mockDB"
        host: str = "localhost"
        port: int = 8086
        enabled: bool = True

    monkeypatch.setattr("Receiver.receiver_config.ifCredentials", influxCredentials())

    monkeypatch.setattr("Receiver.receiver_config.xlsxOutputFile", "")

    from Receiver.telemetry_storer import store_data
    from Receiver.telemetry_parser3 import TelemetryParser

    telemetry_parser = TelemetryParser()
    telemetry_parser.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0, tzinfo=timezone.utc
    )
    # StorerWrapper builds its own parser; hand it this pre-seeded one
    monkeypatch.setattr(
        "Receiver.telemetry_storer.TelemetryParser", lambda: telemetry_parser
    )

    # Act
    store_data(nrt_bytes[20])

    # Assert
    mock_client_class, mock_client_instance = mock_influxdb_client
    mock_client_class.assert_called_once_with(
        host="localhost",
        port=8086,
        username="mock",
        password="mockmockmock",
        database="mockDB",
    )

    mock_client_instance.write_points.assert_called_once_with(
        [
            {
                "measurement": "Orion/PackParameters",
                "time": "1970-01-01T03:00:01.880000Z",
                "fields": {
                    "PackCurrent": 0,
                    "PackInstVoltage": 1305,
                    "PackSoc": 159,
                    "RelayState": 32843,
                },
            }
        ],
        time_precision="ms",
        protocol="json",
    )


def test_influx_closed(monkeypatch, nrt_bytes, run_in_receiver, patch_receiver_config, mock_influxdb_client):
    # Arrange
    class influxCredentials(NamedTuple):
        username: str = "mock"
        password: str = "mockmockmock"
        db: str = "mockDB"
        host: str = "localhost"
        port: int = 8086
        enabled: bool = True

    monkeypatch.setattr("Receiver.receiver_config.ifCredentials", influxCredentials())

    monkeypatch.setattr("Receiver.receiver_config.xlsxOutputFile", "")

    from Receiver.telemetry_storer import end_session

    # Act

    end_session()

    # Assert
    mock_client_class, mock_client_instance = mock_influxdb_client
    mock_client_class.assert_called_once_with(
        host="localhost",
        port=8086,
        username="mock",
        password="mockmockmock",
        database="mockDB",
    )
    mock_client_instance.close.assert_called_once_with()
