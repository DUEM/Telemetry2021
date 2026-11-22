"""Receiver settings: Receiver/config.yml, read and checked by receiver_config.py."""

import re
from pathlib import Path

import pytest
import yaml

from Receiver.receiver_config import CONFIG_FILE, ConfigError, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_config_yml_is_next_to_receiver_config():
    assert CONFIG_FILE == REPO_ROOT / "Receiver" / "config.yml"


def test_shipped_settings():
    """The defaults in Receiver/config.yml, as documented in Receiver/README.md."""
    settings = load_config()

    assert settings["serialPort"] == "/dev/ttyUSB0"
    assert settings["serialBaud"] == 115200
    assert settings["sessionLogName"] == "telem-received"
    assert (settings["xlsxEnabled"], settings["csvEnabled"], settings["binEnabled"]) == (False, False, False)
    assert settings["xlsxSaveInterval"] == 10.0
    # relative folders are under the repository root, whatever the working directory
    assert settings["sessionLogsFolder"] == REPO_ROOT / "session-logs"
    assert settings["xlsxOutputFolder"] == REPO_ROOT / "session-logs" / "excel"
    assert settings["csvOutputFolder"] == REPO_ROOT / "session-logs" / "csv"
    assert settings["binOutputFolder"] == REPO_ROOT / "session-logs" / "BIN"
    credentials = settings["ifCredentials"]
    assert (credentials.db, credentials.host, credentials.port, credentials.enabled) == ("DUSCiESC", "localhost", 8086, True)
    assert [f.name for f in settings["dbc_files"]] == ["wavesculptor_22.dbc", "MPPT.dbc", "Telemetry.dbc", "Orion.dbc"]
    assert all(f.is_file() for f in settings["dbc_files"])


def test_module_values_come_from_config_yml():
    from Receiver import receiver_config

    settings = load_config()
    # the outputs and InfluxDB settings are replaced for every test by conftest
    for name in ("serialPort", "serialBaud", "sessionLogsFolder", "sessionLogName",
                 "xlsxSaveInterval", "dbc_folder", "dbc_files"):
        assert getattr(receiver_config, name) == settings[name], name


@pytest.fixture
def write_config(tmp_path):
    """Write a copy of the shipped config.yml with `changes` applied; return its path."""

    def write(**changes):
        settings = yaml.safe_load(CONFIG_FILE.read_text())
        for name, value in changes.items():
            if value is ...:
                del settings[name]
            else:
                settings[name] = value
        path = tmp_path / "config.yml"
        path.write_text(yaml.safe_dump(settings))
        return path

    return write


def test_serial_port_can_be_changed(write_config):
    assert load_config(write_config(serialPort="COM8"))["serialPort"] == "COM8"


def test_absolute_folder_is_kept(write_config, tmp_path):
    settings = load_config(write_config(csvOutputFolder=str(tmp_path / "logs")))
    assert settings["csvOutputFolder"] == tmp_path / "logs"


def test_whole_number_is_accepted_as_a_number(write_config):
    assert load_config(write_config(xlsxSaveInterval=5))["xlsxSaveInterval"] == 5.0


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"serialPort": ...}, "missing: serialPort"),
        ({"xlsxEnable": True}, "not a setting (misspelt?): xlsxEnable"),
        ({"csvEnabled": "false"}, "csvEnabled must be true or false, not 'false'"),
        ({"serialBaud": "fast"}, "serialBaud must be a whole number, not 'fast'"),
        ({"serialBaud": True}, "serialBaud must be a whole number, not True"),
        ({"xlsxSaveInterval": "10s"}, "xlsxSaveInterval must be a number, not '10s'"),
        ({"dbc_files": "Orion.dbc"}, "dbc_files must be a list of file names"),
        ({"ifCredentials": {"db": "DUSCiESC"}}, "missing: ifCredentials.username"),
        (
            {"ifCredentials": {"username": "a", "password": "b", "db": "c", "host": "d", "port": "8086", "enabled": True}},
            "ifCredentials.port must be a whole number, not '8086'",
        ),
    ],
)
def test_bad_setting_is_reported_with_its_name(write_config, changes, message):
    path = write_config(**changes)
    with pytest.raises(ConfigError, match=re.escape(f"{path}: {message}")):
        load_config(path)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="Cannot read the receiver settings file .*nothing.yml"):
        load_config(tmp_path / "nothing.yml")


def test_invalid_yaml_is_reported(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("serialPort: [/dev/ttyUSB0\n")
    with pytest.raises(ConfigError, match="is not valid YAML"):
        load_config(path)
