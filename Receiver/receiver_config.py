from pathlib import PurePath
from typing import NamedTuple


# Paths are resolved relative to this file, so the receiver can be started from
# any working directory (e.g. as a service on the Pi).
_repo_root = PurePath(__file__).parent.parent

# used by all live_calculation scripts
# Each output is switched on or off with its own True/False setting. Each run of
# the receiver writes a new file named after the time it started, e.g.
# session-logs/csv/telem-received-2026-11-15-143012.csv. The folders are created if
# they do not exist.
sessionLogsFolder = _repo_root / "session-logs"
sessionLogName: str = "telem-received"  # file names are <sessionLogName>-YYYY-MM-DD-HHMMSS.<ext>

# Excel (.xlsx) output
xlsxEnabled: bool = False
xlsxOutputFolder = sessionLogsFolder / "excel"
# Save the xlsx file at most this often (seconds), and when the receiver stops.
# Saving rewrites the whole workbook, so saving after every message gets slower
# as the file grows. If the receiver is killed without stopping cleanly, up to
# this many seconds of rows are missing from the xlsx (the SD card log on the
# board still has them).
xlsxSaveInterval: float = 10.0

# CSV output
csvEnabled: bool = False
csvOutputFolder = sessionLogsFolder / "csv"

# Raw radio data (.BIN), every frame as received, in the same format as the SD
# card log on the vehicle. Can be decoded later with tools/hex2csv.py or
# tools/hex2influx.py, or replayed through a virtual serial port.
binEnabled: bool = False
binOutputFolder = sessionLogsFolder / "BIN"

# InfluxDB output: switched on or off with `enabled` below
class InfluxCredentials(NamedTuple):
    username: str = "admin"
    password: str = "password"
    db: str = "DUSCiESC"
    host: str = "localhost"
    port: int = 8086
    enabled: bool = True


ifCredentials = InfluxCredentials()

dbc_folder = _repo_root / "dbc"
dbc_files = [
    dbc_folder / "wavesculptor_22.dbc",
    dbc_folder / "MPPT.dbc",
    dbc_folder / "Telemetry.dbc",
    dbc_folder / "Orion.dbc",
]
