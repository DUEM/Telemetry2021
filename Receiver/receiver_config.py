"""Receiver settings, read from config.yml in this folder.

Change the settings in config.yml, not here: this module only reads that file
and checks it. Every setting must be present and of the right type, otherwise
importing this module raises ConfigError, naming the file and the setting.

Other modules use the values as `receiver_config.<name>`, read at call time,
so that tests can monkeypatch them (see Tests/test_config_binding.py).
"""

from pathlib import Path
from typing import List, NamedTuple

import yaml

CONFIG_FILE = Path(__file__).with_name("config.yml")

# Relative paths in config.yml are relative to the repository root, so the
# receiver can be started from any working directory (e.g. as a service).
_repo_root = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    """config.yml is missing, cannot be read, or has a bad setting."""


class InfluxCredentials(NamedTuple):
    username: str
    password: str
    db: str
    host: str
    port: int
    enabled: bool


# The type each setting must have. "path" is a folder, relative to the
# repository root unless absolute.
_SETTINGS = {
    "serialPort": str,
    "serialBaud": int,
    "sessionLogsFolder": "path",
    "sessionLogName": str,
    "xlsxEnabled": bool,
    "xlsxOutputFolder": "path",
    "xlsxSaveInterval": float,
    "csvEnabled": bool,
    "csvOutputFolder": "path",
    "binEnabled": bool,
    "binOutputFolder": "path",
    "ifCredentials": InfluxCredentials,
    "dbc_folder": "path",
    "dbc_files": List[str],
}

_TYPE_NAMES = {str: "text", int: "a whole number", float: "a number", bool: "true or false"}


def _check(value, expected, where):
    """Return `value` converted to `expected`, or raise ConfigError."""
    if expected == "path":
        return _repo_root / Path(_check(value, str, where)).expanduser()
    if expected is InfluxCredentials:
        if not isinstance(value, dict):
            raise ConfigError(f"{where} must be a group of settings: {', '.join(InfluxCredentials._fields)}")
        _check_names(value, InfluxCredentials._fields, where + ".")
        return InfluxCredentials(
            **{
                name: _check(value[name], InfluxCredentials.__annotations__[name], f"{where}.{name}")
                for name in InfluxCredentials._fields
            }
        )
    if expected == List[str]:
        if not isinstance(value, list) or not value:
            raise ConfigError(f"{where} must be a list of file names, one per line starting with '- '")
        return [_check(item, str, f"{where} item {i + 1}") for i, item in enumerate(value)]
    # bool is a kind of int in Python, so check it separately
    ok = (
        isinstance(value, bool)
        if expected is bool
        else not isinstance(value, bool)
        and isinstance(value, (int, float) if expected is float else expected)
    )
    if not ok:
        raise ConfigError(f"{where} must be {_TYPE_NAMES[expected]}, not {value!r}")
    return float(value) if expected is float else value


def _check_names(found, expected, prefix=""):
    missing = [prefix + name for name in expected if name not in found]
    unknown = [prefix + str(name) for name in found if name not in expected]
    if missing or unknown:
        problems = []
        if missing:
            problems.append(f"missing: {', '.join(missing)}")
        if unknown:
            problems.append(f"not a setting (misspelt?): {', '.join(unknown)}")
        raise ConfigError("; ".join(problems))


def load_config(path=CONFIG_FILE) -> dict:
    """Read and check a settings file; return {setting name: value}.

    Raises ConfigError naming the file and the problem.
    """
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except OSError as e:
        raise ConfigError(f"Cannot read the receiver settings file {path}: {e.strerror}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} is not valid YAML: {e}") from e
    try:
        if not isinstance(raw, dict):
            raise ConfigError("expected one 'name: value' setting per line")
        _check_names(raw, _SETTINGS)
        settings = {name: _check(raw[name], kind, name) for name, kind in _SETTINGS.items()}
    except ConfigError as e:
        raise ConfigError(f"{path}: {e}") from None
    settings["dbc_files"] = [settings["dbc_folder"] / name for name in settings["dbc_files"]]
    return settings


_settings = load_config()

# XBee radio serial port
serialPort: str = _settings["serialPort"]
serialBaud: int = _settings["serialBaud"]

# Output files: session-logs/<format>/<sessionLogName>-YYYY-MM-DD-HHMMSS.<ext>
sessionLogsFolder: Path = _settings["sessionLogsFolder"]
sessionLogName: str = _settings["sessionLogName"]
xlsxEnabled: bool = _settings["xlsxEnabled"]
xlsxOutputFolder: Path = _settings["xlsxOutputFolder"]
xlsxSaveInterval: float = _settings["xlsxSaveInterval"]
csvEnabled: bool = _settings["csvEnabled"]
csvOutputFolder: Path = _settings["csvOutputFolder"]
binEnabled: bool = _settings["binEnabled"]
binOutputFolder: Path = _settings["binOutputFolder"]

# InfluxDB output
ifCredentials: InfluxCredentials = _settings["ifCredentials"]

# CAN database files (full paths)
dbc_folder: Path = _settings["dbc_folder"]
dbc_files: List[Path] = _settings["dbc_files"]
