from datetime import timedelta, timezone, datetime


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
                l2 = line2.split(",")[3:19]
                l1Body = dict()
                l2Body = dict()
                for j in range(8):
                    l1Body[l1[j * 2]] = l1[j * 2 + 1]
                    l2Body[l2[j * 2]] = l2[j * 2 + 1]
                assert (
                    l1Body == l2Body
                ), f"Difference found at line {i}: {line1} != {line2}"
                assert set(line1.split(",")) == set(line2.split(","))


def test_sessions_do_not_share_clock_state(tmp_path, run_in_receiver):
    """Each conversion must start with its own parser.

    hex2csv used to hold `telemetry_parser=TelemetryParser()` as a default
    argument. Default arguments are evaluated once at import, so every
    conversion in a process shared one parser, and a second session inherited
    the first session's GPS clock instead of starting from the current time.
    """
    # arrange
    from Receiver.hex2csv import hex2csv

    # act - two sessions, neither passing an explicit parser
    hex2csv("Tests/data/MPPT.BIN", f"{tmp_path}/session1.csv", "w")
    hex2csv("Tests/data/MPPT.BIN", f"{tmp_path}/session2.csv", "w")

    # assert - session 2 starts from the current time, not session 1's GPS clock
    with open(f"{tmp_path}/session2.csv") as f2:
        started = datetime.strptime(
            f2.readline().split(",")[0], "%d/%m/%Y %H:%M:%S.%f"
        )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs(now - started) < timedelta(minutes=5), (
        f"session 2 started at {started}, not near {now}: "
        f"clock state leaked from session 1"
    )
