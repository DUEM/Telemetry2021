from pathlib import PurePath
from typing import NamedTuple


# used by all live_calculation scripts
# Each output is switched on or off with its own True/False setting. File paths
# are relative to the directory the receiver is started from, and the folder is
# created if it does not exist.

# Excel (.xlsx) output
xlsxEnabled: bool = False
xlsxOutputFile: str = './ExcelOutput/ExcelTest.xlsx'
# Save the xlsx file at most this often (seconds), and when the receiver stops.
# Saving rewrites the whole workbook, so saving after every message gets slower
# as the file grows. If the receiver is killed without stopping cleanly, up to
# this many seconds of rows are missing from the xlsx (the SD card log on the
# board still has them).
xlsxSaveInterval: float = 10.0

# CSV output
csvEnabled: bool = False
csvOutputFile: str = './Output/telemetry.csv'

# InfluxDB output: switched on or off with `enabled` below
class InfluxCredentials(NamedTuple):
    username: str = "admin"
    password: str = "password"
    db: str = "DUSCiESC"
    host: str = "localhost"
    port: int = 8086
    enabled: bool = True


ifCredentials = InfluxCredentials()

# Paths are resolved relative to this file, so the receiver can be started from
# any working directory (e.g. as a service on the Pi).
_repo_root = PurePath(__file__).parent.parent

dbc_folder = _repo_root / "dbc"
dbc_files = [
    dbc_folder / "wavesculptor_22.dbc",
    dbc_folder / "MPPT.dbc",
    dbc_folder / "Telemetry.dbc",
    dbc_folder / "Orion.dbc",
]
