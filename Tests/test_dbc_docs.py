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
MAX_TODOS = 52


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
