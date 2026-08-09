from datetime import timezone, datetime
from unittest.mock import MagicMock


def test_hex2influx_writes_decoded_points(monkeypatch, run_in_receiver):
    # arrange
    import Receiver.hex2influx as hex2influx_module
    from Receiver.telemetry_parser3 import TelemetryParser

    # patch where the name is looked up, not where it is defined
    mock_client = MagicMock()
    monkeypatch.setattr("Receiver.hex2influx.InfluxDBClient", mock_client)

    telemetry_parser = TelemetryParser()
    telemetry_parser.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0, tzinfo=timezone.utc
    )

    # act
    hex2influx_module.hex2influx("Tests/data/MPPT.BIN", telemetry_parser)

    # assert
    write_points = mock_client.return_value.write_points
    write_points.assert_called_once()
    points = write_points.call_args[0][0]

    javed = [point for point in points if point.startswith("Mppt/Javed")]
    assert javed, "no Mppt/Javed points were decoded"
    assert "VoltageIn=586" in javed[0]
    assert javed[0].endswith("1689689137000"), "timestamp is not epoch ms"

    # the whole point of this tool is writing in batches rather than per line
    assert write_points.call_args[1]["protocol"] == "line"
    assert write_points.call_args[1]["batch_size"] == 5000
