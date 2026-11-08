import pytest
from unittest.mock import MagicMock, call, patch
from datetime import datetime, timezone



# Mock the Workbook and Worksheet
@pytest.fixture(scope="function")
def mock_xlsx_workbook(monkeypatch):
    # dbc_files, ifCredentials and csvOutputFile come from patch_receiver_config
    monkeypatch.setattr("Receiver.receiver_config.xlsxOutputFile", "mock.xlsx")

    # patch where the name is looked up, not where it is defined
    with patch("Receiver.storer_extension.Workbook", spec=True) as mock_workbook:
        workbook_instance = mock_workbook.return_value
        mock_worksheet = MagicMock()
        workbook_instance.create_sheet.return_value = mock_worksheet

        yield workbook_instance, mock_worksheet


def test_data_written_to_xlsx(nrt_bytes, mock_xlsx_workbook):
    # Arrange
    mock_workbook, mock_worksheet = mock_xlsx_workbook
    from Receiver.telemetry_parser3 import TelemetryParser
    from Receiver.storer_extension import ExcelStorer
    from Receiver.telemetry_storer import TelemetryStorer

    telemetry_parser = TelemetryParser()
    telemetry_parser.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0,
        tzinfo=timezone.utc
    )
    storer = TelemetryStorer(
        telemetry_parser, storage_plugin_list=[ExcelStorer("mock.xlsx")]
    )

    # Act
    storer.store_data(nrt_bytes[20])

    # Assert
    assert mock_worksheet.cell.call_args_list == [
        call(column=1, row=1, value='Date'),
        call(column=2, row=1, value='Time'),
        call(column=3, row=1, value='Source'),
        call(column=4, row=1, value='Item'),
        call(column=5, row=1, value='Data...'),
        call(column=21, row=1, value='CRC check'),
        call(column=1, row=2, value=datetime(1970, 1, 1, 3, 0, 1, 880000)),
        call(column=2, row=2, value=datetime(1970, 1, 1, 3, 0, 1, 880000)),
        call(column=3, row=2, value="Orion"),
        call(column=4, row=2, value="PackParameters"),
        call(column=5, row=2, value="PackCurrent"),
        call(column=6, row=2, value=0),
        call(column=7, row=2, value="PackInstVoltage"),
        call(column=8, row=2, value=1305),
        call(column=9, row=2, value="PackSoc"),
        call(column=10, row=2, value=159),
        call(column=11, row=2, value="RelayState"),
        call(column=12, row=2, value=32843),
        call(column=21, row=2, value=True),
    ]
    mock_workbook.save.assert_called_once_with("mock.xlsx")


def test_xlsx_closed(monkeypatch, nrt_bytes, run_in_receiver, mock_xlsx_workbook):
    # Arrange
    mock_workbook, mock_worksheet = mock_xlsx_workbook
    from Receiver.telemetry_storer import end_session

    # Act
    end_session()

    # Assert
    mock_workbook.save.assert_called_once_with("mock.xlsx")
    mock_workbook.close.assert_called_once_with()


def test_xlsx_saved_at_most_once_per_interval(monkeypatch, mock_xlsx_workbook):
    """Saving rewrites the whole workbook, so it must not happen on every row."""
    # Arrange
    mock_workbook, _ = mock_xlsx_workbook
    from Receiver.storer_extension import ExcelStorer

    clock = [1000.0]
    monkeypatch.setattr("Receiver.storer_extension.time.monotonic", lambda: clock[0])
    storer = ExcelStorer("mock.xlsx", save_interval=10.0)
    msg_time = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)

    def store_row():
        storer.store_data("PackParameters", "Orion", {"PackSoc": 159}, msg_time, True)

    # Act / Assert
    store_row()  # first row: saved straight away so the file appears
    assert mock_workbook.save.call_count == 1

    for _ in range(50):  # many rows within the interval: not saved
        clock[0] += 0.1
        store_row()
    assert mock_workbook.save.call_count == 1

    clock[0] += 5.0  # 10 s since the last save: saved again
    store_row()
    assert mock_workbook.save.call_count == 2

    store_row()  # within the new interval: not saved until close
    storer.close()
    assert mock_workbook.save.call_count == 3
    mock_workbook.save.assert_called_with("mock.xlsx")
    mock_workbook.close.assert_called_once_with()


def test_xlsx_save_interval_from_config(monkeypatch, mock_xlsx_workbook):
    # Arrange
    monkeypatch.setattr("Receiver.receiver_config.xlsxSaveInterval", 2.5)
    from Receiver.storer_extension import ExcelStorer
    from Receiver.telemetry_storer import storer_wrapper

    # Act
    plugins = storer_wrapper.telemetry_storer.storage_plugin_list

    # Assert
    excel_storers = [p for p in plugins if isinstance(p, ExcelStorer)]
    assert [s.save_interval for s in excel_storers] == [2.5]
