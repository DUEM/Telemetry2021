"""Shared fixtures for the test suite.

Test captures live in `Tests/data/*.BIN` and are stored without the end of
frame marker, as `read_frames` splits on it. The expected output for a capture
sits alongside it as `Tests/data/*.csv`.
"""

from typing import NamedTuple

import pytest

from Receiver.frame_reader import read_frames


@pytest.fixture(autouse=True)
def run_in_receiver():
    # No-op: tests run from the project root (see pythonpath in pytest.ini).
    # Kept so existing tests that request it keep resolving.
    pass


@pytest.fixture(autouse=True)
def patch_receiver_config(request, monkeypatch):
    # The DBC files are not patched: tests decode with the same files in dbc/
    # that the receiver uses, so a DBC change is caught by the tests.
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
    return read_frames(request.config.rootdir + "/Tests/data/NRT.BIN")


@pytest.fixture(scope="session")
def mppt_bytes(request):
    return read_frames(request.config.rootdir + "/Tests/data/MPPT.BIN")
