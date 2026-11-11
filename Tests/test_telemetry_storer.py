from datetime import timezone, datetime
from unittest.mock import MagicMock



def test_store_data_nrt(monkeypatch, tmp_path, run_in_receiver, nrt_bytes):
    # arrange
    from Receiver.telemetry_parser import TelemetryParser
    from Receiver.telemetry_storer import TelemetryStorer

    telemetry_parser = TelemetryParser()
    telemetry_parser.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0, tzinfo=timezone.utc
    )

    mock_store_function = MagicMock()
    mock_store_class = MagicMock()
    mock_store_class.store_data = mock_store_function
    telemetry_storer = TelemetryStorer(telemetry_parser, storage_plugin_list=[mock_store_class])

    storeData = telemetry_storer.store_data

    msgs = nrt_bytes
    # act
    storeData(msgs[39])  # Orion
    mock_store_function.assert_called_with(
        "PackParameters",
        "Orion",
        {
            "PackCurrent": 0,
            "PackInstVoltage": 1179,
            "PackSoc": 148,
            "RelayState": 75,
            "Checksum": 54,
        },
        datetime(1970, 1, 1, 3, 22, 23, 552000, tzinfo=timezone.utc),
        True,
    )

    storeData(msgs[1281])  # tritium, while driving
    mock_store_function.assert_called_with(
        "Velocity",
        "Tritium",
        {"MotorVelocity": 153.98561096191406, "VehicleVelocity": 4.498969078063965},
        datetime(1970, 1, 1, 4, 13, 34, 327000, tzinfo=timezone.utc),
        True,
    )

    storeData(msgs[7])  # crc fail
    mock_store_function.assert_called_with(
        "CRCFail",
        "",
        {"Data": b"140007010800780078200d00d600af"},
        datetime(1970, 1, 1, 3, 0, tzinfo=timezone.utc),
        False,
    )

    storeData(msgs[45])  # status msg
    mock_store_function.assert_called_with(
        "SystemStatusMessages",
        "Telemetry",
        {
            "Power": 1,
            "WritingToSd": 255,
            "GpsTimeObtained": 0,
            "LoadedConfig": 125,
            "Flag": 1,
            "Spare1": 0,
            "Spare2": 0,
            "Spare3": 0,
        },
        datetime(1970, 1, 1, 3, 22, 23, 575000, tzinfo=timezone.utc),
        True,
    )

    storeData(msgs[718])  # drv control
    mock_store_function.assert_called_with(
        "Maxbuscurrent",
        "DriverControls",
        {"Zero": 0.0, "MaxBusCurrent": 1.0},
        datetime(1970, 1, 1, 4, 11, 27, 85000, tzinfo=timezone.utc),
        True,
    )

    # assert
    assert mock_store_function.call_count == 5


def test_store_data_mppt(monkeypatch, tmp_path, run_in_receiver, mppt_bytes):
    # arrange
    from Receiver.telemetry_parser import TelemetryParser
    from Receiver.telemetry_storer import TelemetryStorer

    telemetry_parser = TelemetryParser()
    telemetry_parser.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0, tzinfo=timezone.utc
    )

    mock_store_function = MagicMock()
    mock_store_class = MagicMock()
    mock_store_class.store_data = mock_store_function
    telemetry_storer = TelemetryStorer(telemetry_parser, storage_plugin_list=[mock_store_class])

    storeData = telemetry_storer.store_data

    msgs = mppt_bytes

    # act
    storeData(msgs[20])  # Javed
    mock_store_function.assert_called_with(
        "Javed",
        "Mppt",
        {
            "VoltageIn": 508 * 0.15049,  # raw * scale in dbc/MPPT.dbc
            "CurrentIn": 121 * 0.00872,
            "VoltageOut": 612,
            "AmbientTemperature": 20,
            "BatteryVoltageLevelReached": 0,
            "OverTemperature": 0,
            "NoCharge": 0,
            "UnderVoltage": 0,
        },
        datetime(1970, 1, 1, 3, 0, 19, tzinfo=timezone.utc),
        True,
    )

    storeData(msgs[25])  # Woof
    mock_store_function.assert_called_with(
        "Woof",
        "Mppt",
        {
            "VoltageIn": 450 * 0.15049,  # raw * scale in dbc/MPPT.dbc
            "CurrentIn": 121 * 0.00872,
            "VoltageOut": 614,
            "AmbientTemperature": 20,
            "BatteryVoltageLevelReached": 0,
            "OverTemperature": 0,
            "NoCharge": 0,
            "UnderVoltage": 0,
        },
        datetime(1970, 1, 1, 3, 0, 24, tzinfo=timezone.utc),
        True,
    )

    storeData(msgs[100])  # crc fail
    mock_store_function.assert_called_with(
        "CRCFail",
        "",
        {"Data": b"010007720701d4006d02680f8e72"},
        datetime(1970, 1, 1, 3, 0, tzinfo=timezone.utc),
        False,
    )

    # assert
    assert mock_store_function.call_count == 3


def test_store_data_logs_message_at_info(nrt_bytes, caplog):
    # Arrange
    import logging
    from Receiver.telemetry_parser import TelemetryParser
    from Receiver.telemetry_storer import TelemetryStorer

    storer = TelemetryStorer(TelemetryParser())

    # Act
    with caplog.at_level(logging.INFO, logger="Receiver.telemetry_storer"):
        storer.store_data(nrt_bytes[39])

    # Assert
    assert "0x700 Orion/PackParameters" in caplog.text
    assert "'PackInstVoltage': 1179" in caplog.text
    assert "CRC OK" in caplog.text


def test_store_data_logs_short_frame_without_can_id(caplog):
    # Arrange
    import logging
    from Receiver.telemetry_parser import TelemetryParser
    from Receiver.telemetry_storer import TelemetryStorer

    storer = TelemetryStorer(TelemetryParser())

    # Act: two end of frame markers back to back give an empty frame
    with caplog.at_level(logging.INFO, logger="Receiver.telemetry_storer"):
        storer.store_data(bytearray())

    # Assert
    assert "ID ? /CRCFail" in caplog.text
    assert "CRC FAIL" in caplog.text
