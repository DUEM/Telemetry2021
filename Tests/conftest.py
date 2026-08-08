import sys
from pathlib import PurePath
from typing import NamedTuple

import pytest


@pytest.fixture(autouse=True)
def run_in_receiver():
    # No-op: tests run from the project root (see pythonpath in pytest.ini).
    # Kept so existing tests that request it keep resolving.
    pass


@pytest.fixture(autouse=True)
def patch_receiver_config(request, monkeypatch):
    dbc_folder = PurePath(request.config.rootdir + "/Tests/data/dbc")
    dbc_files = [
        dbc_folder / "wavesculptor_22.dbc",
        dbc_folder / "MPPT.dbc",
        dbc_folder / "Telemetry.dbc",
        dbc_folder / "Orion.dbc",
    ]
    monkeypatch.setattr("Receiver.receiver_config.dbc_files", dbc_files)
    monkeypatch.setattr("Receiver.receiver_config.xlsxOutputFile", "")

    class influxCredentials(NamedTuple):
        enabled: bool = False

    monkeypatch.setattr("Receiver.receiver_config.ifCredentials", influxCredentials())

    # force reloading of telemetry parser and storer
    try:
        del sys.modules["Receiver.telemetry_parser3"]
    except KeyError:
        pass

    try:
        del sys.modules["Receiver.telemetry_storer"]
    except KeyError:
        pass

    try:
        del sys.modules["Receiver.storer_extension"]
    except KeyError:
        pass


@pytest.fixture(scope="session")
def nrt_bytes(request):
    hex_file = request.config.rootdir + "/Tests/data/NRT.BIN"
    end_of_frame_marker = b"\x7E"
    with open(hex_file, mode="rb") as file:
        input_bytes = file.readlines()
    msgs = bytearray().join(input_bytes).split(end_of_frame_marker)
    return msgs


@pytest.fixture(scope="session")
def mppt_bytes(request):
    hex_file = request.config.rootdir + "/Tests/data/MPPT.BIN"
    end_of_frame_marker = b"\x7E"
    with open(hex_file, mode="rb") as file:
        input_bytes = file.readlines()
    msgs = bytearray().join(input_bytes).split(end_of_frame_marker)
    return msgs
