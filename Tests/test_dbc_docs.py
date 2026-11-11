"""Keep the CAN documentation in the dbc files complete and dbc/SIGNALS.md in step.

See dbc/README.md for how the documentation is organised.
"""
import cantools
import pytest

from tools import dbc_to_markdown

# Comments in the dbc files that still say "TODO: add ...". When you fill one
# in, lower this number to match, so it can only go down. Run
#     python3 tools/dbc_to_markdown.py
# and see "Still to be documented" at the end of dbc/SIGNALS.md for the list.
MAX_TODOS = 34


@pytest.fixture(scope="module")
def databases():
    return {f.name: dbc_to_markdown.load(f) for f in dbc_to_markdown.dbc_files()}


def test_signals_md_is_up_to_date():
    expected = dbc_to_markdown.render()
    actual = dbc_to_markdown.OUTPUT.read_text(encoding="utf-8")
    assert actual == expected, (
        "dbc/SIGNALS.md is out of date. Regenerate it from the top of the "
        "repository with: python3 tools/dbc_to_markdown.py"
    )


def test_every_device_message_and_signal_has_a_comment(databases):
    missing = []
    for name, db in databases.items():
        missing += [f"{name}: device {n.name}" for n in db.nodes if not n.comment]
        for m in dbc_to_markdown.messages(db):
            if not m.comment:
                missing.append(f"{name}: message {m.name}")
            missing += [
                f"{name}: signal {m.name}.{s.name}" for s in m.signals if not s.comment
            ]
    assert not missing, (
        "Add a CM_ comment (plain English, or 'TODO: add ...') for: " + ", ".join(missing)
    )


def test_todo_count_does_not_grow(databases):
    count = sum(len(dbc_to_markdown.todos(db)) for db in databases.values())
    assert count <= MAX_TODOS, (
        f"{count} TODO comments in the dbc files, more than MAX_TODOS = {MAX_TODOS}. "
        "Document the new message or signal instead of adding a TODO."
    )
    assert count == MAX_TODOS, (
        f"Only {count} TODO comments are left: lower MAX_TODOS in "
        f"Tests/test_dbc_docs.py from {MAX_TODOS} to {count}."
    )


def test_value_tables_do_not_change_decoded_values():
    """VAL_ tables are documentation: the receiver must still store numbers."""
    from Receiver.can_dbc_decoder import DbcDecoder

    # SystemStatusMessages (0x111): Power = 0xFF ("Starting up" in the VAL_ table)
    name, source, values = DbcDecoder().decode_can_msg(0x111, bytes([0xFF, 0, 0, 0, 0, 0, 0, 0]))

    assert (source, name) == ("Telemetry", "SystemStatusMessages")
    assert values["Power"] == 255
    assert type(values["Power"]) is int


def test_dbc_comments_about_the_nrt_capture_are_true():
    """Several dbc comments state what Tests/data/NRT.BIN (iESC 2026 qualifying) contains: keep them honest."""
    from crccheck.crc import Crc16Modbus
    from Receiver.frame_reader import read_frames

    frames = [
        f for f in read_frames(str(dbc_to_markdown.REPO_ROOT / "Tests/data/NRT.BIN"))
        if len(f) >= 9 and Crc16Modbus.calc(f[:-2]) == int.from_bytes(f[-2:], "big")
    ]
    ids = {f[4] << 8 | f[5] for f in frames}

    # seen: controller base 0x300, its reserved message 0x30D, driver controls, current dial
    assert {0x300, 0x30D, 0x101, 0x102, 0x500} <= ids
    # not seen: reserved fan message 0x30A, MPPT status replies
    assert not ids & {0x30A, 0x771, 0x772}
    # controller identification: device identifier 0x4003 (WaveSculptor22), serial number 3315
    ident = next(f for f in frames if (f[4] << 8 | f[5]) == 0x300)
    assert int.from_bytes(ident[7:11], "little") == 0x4003
    assert int.from_bytes(ident[11:15], "little") == 3315
    # Orion checksum: (sum of bytes 0 to 6 + offset) & 0xFF, offsets as in dbc/Orion.dbc
    for can_id, offset in ((0x700, 184), (0x701, 185), (0x702, 0)):
        orion = [f for f in frames if (f[4] << 8 | f[5]) == can_id]
        assert orion
        assert all((sum(f[7:14]) + offset) & 0xFF == f[14] for f in orion)
