from pathlib import PurePath
from typing import NamedTuple


# used by all live_calculation scripts
#xlsxOutputFile: str = './ExcelOutput/ExcelTest.xlsx' #set equal to '' to switch off xslx output
xlsxOutputFile: str = ''


class InfluxCredentials(NamedTuple):
    username: str = "admin"
    password: str = "password"
    db: str = "Test22DB"
    host: str = "localhost"
    port: int = 8086
    enabled: bool = True


ifCredentials = InfluxCredentials()

# Paths are resolved relative to this file, so the receiver can be started from
# any working directory (e.g. as a service on the Pi).
_repo_root = PurePath(__file__).parent.parent

# configFile: str = './CANConfig.xslx' #raspberrypi
configFile: str = str(
    _repo_root.parent / "CANTranslator/config/CANBusConfig.xlsm"
)  # testing with windows

dbc_folder = _repo_root / "dbc"
dbc_files = [
    dbc_folder / "wavesculptor_22.dbc",
    dbc_folder / "MPPT.dbc",
    dbc_folder / "Telemetry.dbc",
    dbc_folder / "Orion.dbc",
]
