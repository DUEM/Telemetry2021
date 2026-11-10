from types import SimpleNamespace

import pytest

from tools import batch_Read_Hex


@pytest.fixture
def bin_dir(tmp_path):
    for name in ["23101801.BIN", "23101800.bin", "23101900.BIN", "notes.txt", "2310180.BIN"]:
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "23101802.BIN").mkdir()  # a directory, not a file
    return tmp_path


def test_find_bin_files_default_pattern(bin_dir):
    found = [f.name for f in batch_Read_Hex.find_bin_files(bin_dir)]

    # YYMMDDNN.BIN in any case, sorted; not other names, short names or directories
    assert found == ["23101800.bin", "23101801.BIN", "23101900.BIN"]


def test_find_bin_files_custom_pattern(bin_dir):
    found = [f.name for f in batch_Read_Hex.find_bin_files(bin_dir, r"231018[0-9]{2}\.BIN")]

    assert found == ["23101800.bin", "23101801.BIN"]


def test_main_runs_hex2influx_on_each_file(monkeypatch, bin_dir):
    # Arrange
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return SimpleNamespace(returncode=1 if cmd[-1].endswith("23101801.BIN") else 0)

    monkeypatch.setattr(batch_Read_Hex.sp, "run", fake_run)

    # Act
    exit_code = batch_Read_Hex.main(["-d", str(bin_dir), "-p", r"231018[0-9]{2}\.BIN"])

    # Assert: same python, the hex2influx script next to this one, one file each
    assert [c[:2] for c in calls] == [[batch_Read_Hex.sys.executable, str(batch_Read_Hex.HEX2INFLUX)]] * 2
    assert [c[2:] for c in calls] == [
        ["-i", str(bin_dir / "23101800.bin")],
        ["-i", str(bin_dir / "23101801.BIN")],
    ]
    assert batch_Read_Hex.HEX2INFLUX.exists()
    assert exit_code == 1  # one file failed


def test_main_dry_run_imports_nothing(monkeypatch, bin_dir, capsys):
    monkeypatch.setattr(batch_Read_Hex.sp, "run", pytest.fail)

    assert batch_Read_Hex.main(["-d", str(bin_dir), "-n"]) == 0
    assert "3 files would be imported" in capsys.readouterr().out


def test_main_no_matching_files(bin_dir):
    assert batch_Read_Hex.main(["-d", str(bin_dir), "-p", "nothing"]) == 1


def test_main_rejects_missing_directory(tmp_path):
    with pytest.raises(SystemExit):
        batch_Read_Hex.main(["-d", str(tmp_path / "missing")])
