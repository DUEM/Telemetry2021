from datetime import timezone, datetime
from fixtures import run_in_receiver, patch_receiver_config


def test_hex2csv(monkeypatch, tmp_path, run_in_receiver):
    # arrange
    from Receiver.hex2csv import hex2csv
    from Receiver.telemetry_parser3 import TelemetryParser

    tp = TelemetryParser()
    tp.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0, tzinfo=timezone.utc
    )
    # act
    hex2csv("Tests/data/NRT.BIN", f"{tmp_path}/output.csv", "w", tp)

    # assert
    with open(f"{tmp_path}/output.csv") as f1:
        with open("Tests/data/NRT.csv") as f2:
            f1lines = f1.readlines()
            f2lines = f2.readlines()
            f2lines = [
                line.replace("CellTempsDischargeChageCurrentLimit", "CellTempsDCL")
                for line in f2lines
            ]
            for i, (line1, line2) in enumerate(zip(f1lines, f2lines)):
                assert (
                    line1 == line2
                ), f"Difference found at line {i}: {line1} != {line2}"
            assert f1lines == f2lines


def test_hex2csv2(monkeypatch, tmp_path, run_in_receiver):
    # arrange
    from Receiver.hex2csv import hex2csv
    from Receiver.telemetry_parser3 import TelemetryParser

    tp = TelemetryParser()
    tp.last_gps_time = datetime(
        year=1970, month=1, day=1, hour=3, minute=0, second=0, tzinfo=timezone.utc
    )

    # act
    hex2csv("Tests/data/MPPT.BIN", f"{tmp_path}/output.csv", "w", tp)

    # assert
    with open(f"{tmp_path}/output.csv") as f1:
        with open("Tests/data/MPPT.csv") as f2:
            f1lines = f1.readlines()
            f2lines = f2.readlines()
            f2lines = [line.replace("Flag/", "") for line in f2lines]
            for i, (line1, line2) in enumerate(zip(f1lines, f2lines)):
                l1 = line1.split(",")[3:19]
                l2 = line1.split(",")[3:19]
                l1Body = dict()
                l2Body = dict()
                for i in range(8):
                    l1Body[l1[i * 2]] = l1[i * 2 + 1]
                    l2Body[l2[i * 2]] = l2[i * 2 + 1]
                assert (
                    l1Body == l2Body
                ), f"Difference found at line {i}: {line1} != {line2}"
                assert set(line1.split(",")) == set(line2.split(","))
