from numpy import uint32
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

    monkeypatch.setattr("Receiver.receiver_config.xlsxEnabled", False)

    from Receiver.telemetry_storer import store_data, end_session
    from Receiver.telemetry_parser import TelemetryParser

    telemetry_parser = TelemetryParser()
    telemetry_parser.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0, tzinfo=timezone.utc
    )
    telemetry_parser.time_fetched = uint32(0)  # reference: millis 0 at that time
    # StorerWrapper builds its own parser; hand it this pre-seeded one
    monkeypatch.setattr(
        "Receiver.telemetry_storer.TelemetryParser", lambda: telemetry_parser
    )

    # Act - points are written in batches, and the last batch when the session ends
    store_data(nrt_bytes[26])
    end_session()

    # Assert
    mock_client_class, mock_client_instance = mock_influxdb_client
    mock_client_class.assert_called_once_with(
        host="localhost",
        port=8086,
        username="mock",
        password="mockmockmock",
        database="mockDB",
        timeout=5,
    )

    mock_client_instance.write_points.assert_called_once_with(
        [
            {
                "measurement": "Orion/PackParameters",
                "time": "1970-01-01T03:22:23.552000Z",
                "fields": {
                    "PackCurrent": 0,
                    "PackInstVoltage": 1179 * 0.1,  # raw x scale in dbc/Orion.dbc
                    "PackSoc": 148 * 0.5,
                    "RelayState": 75,
                    "Checksum": 54,
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

    monkeypatch.setattr("Receiver.receiver_config.xlsxEnabled", False)

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
        timeout=5,
    )
    mock_client_instance.close.assert_called_once_with()


def test_influx_client_error_logged_not_raised(mock_influxdb_client, caplog):
    # Arrange
    from influxdb.exceptions import InfluxDBClientError
    from Receiver.receiver_config import load_config
    from Receiver.storer_extension import Influx1Storer

    _, mock_client_instance = mock_influxdb_client
    mock_client_instance.write_points.side_effect = InfluxDBClientError(
        '{"error":"database not found: \\"mockDB\\""}', 404
    )
    storer = Influx1Storer(load_config()["ifCredentials"]._replace(db="mockDB"))
    msg_time = datetime(1970, 1, 1, tzinfo=timezone.utc)

    # Act
    storer.store_data("PackParameters", "Orion", {"PackSoc": 159}, msg_time, True)
    storer.close()  # writes the batch

    # Assert
    mock_client_instance.write_points.assert_called_once()
    assert "Influx rejected write of 1 points (Orion/PackParameters)" in caplog.text
    assert "database not found" in caplog.text


def test_message_without_fields_not_written(mock_influxdb_client):
    # e.g. the MPPT poll requests carry no data; influx rejects a point with no fields
    from Receiver.storer_extension import Influx1Storer

    class influxCredentials(NamedTuple):
        username: str = "mock"
        password: str = "mock"
        db: str = "mockDB"
        host: str = "localhost"
        port: int = 8086
        enabled: bool = True

    _, client = mock_influxdb_client
    storer = Influx1Storer(influxCredentials())

    storer.store_data("MpptPollJaved", "Telemetry", {}, datetime(2026, 1, 1, tzinfo=timezone.utc), True)

    client.write_points.assert_not_called()


class enabledCredentials(NamedTuple):
    username: str = "mock"
    password: str = "mock"
    db: str = "mockDB"
    host: str = "localhost"
    port: int = 8086
    enabled: bool = True


def store_points(storer, count):
    for i in range(count):
        storer.store_data(
            "Velocity", "Tritium", {"VehicleVelocity": float(i)},
            datetime(2026, 9, 18, 11, 30, 0, i, tzinfo=timezone.utc), True,
        )


def test_points_are_written_in_one_batch(monkeypatch, mock_influxdb_client):
    """One HTTP request per CAN message is too slow for the radio traffic."""
    from Receiver.storer_extension import Influx1Storer

    _, client = mock_influxdb_client
    clock = [100.0]
    monkeypatch.setattr("Receiver.storer_extension.time.monotonic", lambda: clock[0])
    storer = Influx1Storer(enabledCredentials())

    store_points(storer, 10)  # all within the batch time
    client.write_points.assert_not_called()
    clock[0] += 0.5
    store_points(storer, 1)  # batch time reached: all 11 go in one write

    client.write_points.assert_called_once()
    batch = client.write_points.call_args.args[0]
    assert [p["fields"]["VehicleVelocity"] for p in batch] == [float(i) for i in range(10)] + [0.0]


def test_a_full_batch_is_written_without_waiting(monkeypatch, mock_influxdb_client):
    from Receiver.storer_extension import Influx1Storer, INFLUX_BATCH_POINTS

    _, client = mock_influxdb_client
    monkeypatch.setattr("Receiver.storer_extension.time.monotonic", lambda: 100.0)
    storer = Influx1Storer(enabledCredentials())

    store_points(storer, INFLUX_BATCH_POINTS)

    client.write_points.assert_called_once()
    assert len(client.write_points.call_args.args[0]) == INFLUX_BATCH_POINTS


def test_close_writes_the_last_points(mock_influxdb_client):
    from Receiver.storer_extension import Influx1Storer

    _, client = mock_influxdb_client
    storer = Influx1Storer(enabledCredentials())
    store_points(storer, 3)

    storer.close()

    assert sum(len(c.args[0]) for c in client.write_points.call_args_list) == 3
    client.close.assert_called_once_with()


@pytest.mark.parametrize("error", ["timeout", "connection", "server"])
def test_network_errors_are_logged_not_raised(mock_influxdb_client, caplog, error):
    """A slow or lost connection must not stop the receiver."""
    import requests
    from influxdb.exceptions import InfluxDBServerError
    from Receiver.storer_extension import Influx1Storer

    _, client = mock_influxdb_client
    client.write_points.side_effect = {
        "timeout": requests.exceptions.ReadTimeout("Read timed out. (read timeout=5)"),
        "connection": requests.exceptions.ConnectionError("Connection refused"),
        "server": InfluxDBServerError("internal error"),
    }[error]
    storer = Influx1Storer(enabledCredentials())
    store_points(storer, 2)

    storer.close()  # writes the batch, which fails

    assert "Could not write 2 points to Influx (Tritium/Velocity)" in caplog.text
    # the failed batch is dropped, not tried again on the next write
    client.write_points.side_effect = None
    client.write_points.reset_mock()
    store_points(storer, 1)
    storer.close()
    assert len(client.write_points.call_args.args[0]) == 1
