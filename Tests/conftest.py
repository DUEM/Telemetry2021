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
    monkeypatch.setattr("Receiver.receiver_config.csvOutputFile", "")

    class influxCredentials(NamedTuple):
        enabled: bool = False

    monkeypatch.setattr("Receiver.receiver_config.ifCredentials", influxCredentials())

    # storer_wrapper is a module-level singleton that caches its plugin list on
    # first use, so give each test a fresh one. Remove once it stops being a
    # module-level global.
    import Receiver.telemetry_storer as telemetry_storer

    monkeypatch.setattr(
        telemetry_storer, "storer_wrapper", telemetry_storer.StorerWrapper()
    )


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
