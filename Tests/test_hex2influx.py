from datetime import timezone, datetime
from unittest.mock import MagicMock


def test_hex2influx_writes_decoded_points(monkeypatch, run_in_receiver):
    # arrange
    import tools.hex2influx as hex2influx_module
    from Receiver.telemetry_parser import TelemetryParser

    # patch where the name is looked up, not where it is defined
    mock_client = MagicMock()
    monkeypatch.setattr("tools.hex2influx.InfluxDBClient", mock_client)

    telemetry_parser = TelemetryParser()
    telemetry_parser.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0, tzinfo=timezone.utc
    )

    # the receiver's real influx settings (conftest replaces them with a stub)
    from Receiver.receiver_config import InfluxCredentials
    monkeypatch.setattr("Receiver.receiver_config.ifCredentials", InfluxCredentials())

    # act
    hex2influx_module.hex2influx("Tests/data/MPPT.BIN", telemetry_parser)

    # uses the receiver's database
    assert mock_client.call_args.kwargs["database"] == "DUSCiESC"

    # assert
    write_points = mock_client.return_value.write_points
    write_points.assert_called_once()
    points = write_points.call_args[0][0]

    javed = [point for point in points if point.startswith("Mppt/Javed")]
    assert javed, "no Mppt/Javed points were decoded"
    # raw 586 * 0.15049 V per bit (dbc/MPPT.dbc)
    assert f"VoltageIn={586 * 0.15049}" in javed[0]
    assert javed[0].endswith("1689689137000"), "timestamp is not epoch ms"

    # the whole point of this tool is writing in batches rather than per line
    assert write_points.call_args[1]["protocol"] == "line"
    assert write_points.call_args[1]["batch_size"] == 5000


def test_hex2influx_database_option(monkeypatch, run_in_receiver):
    import tools.hex2influx as hex2influx_module
    from Receiver.receiver_config import InfluxCredentials

    mock_client = MagicMock()
    monkeypatch.setattr("tools.hex2influx.InfluxDBClient", mock_client)
    monkeypatch.setattr("Receiver.receiver_config.ifCredentials", InfluxCredentials())

    hex2influx_module.hex2influx("Tests/data/MPPT.BIN", database="OldSession")

    assert mock_client.call_args.kwargs["database"] == "OldSession"
