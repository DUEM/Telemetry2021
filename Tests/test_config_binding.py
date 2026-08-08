"""Guard against re-introducing import-time config binding.

`from Receiver.receiver_config import dbc_files` copies the value into the
importing module, so monkeypatching `receiver_config` afterwards has no effect
and tests silently run against production config. Modules must reach through
`receiver_config.<name>` at call time instead.
"""

CONFIG_NAMES = ("dbc_files", "xlsxOutputFile", "csvOutputFile", "ifCredentials")


def test_config_is_read_at_call_time():
    import Receiver.can_dbc_decoder as can_dbc_decoder
    import Receiver.telemetry_storer as telemetry_storer

    leaked = [
        f"{module.__name__}.{name}"
        for module in (can_dbc_decoder, telemetry_storer)
        for name in CONFIG_NAMES
        if hasattr(module, name)
    ]
    assert not leaked, (
        f"config bound at import time: {leaked}. Use `from Receiver import "
        f"receiver_config` and read `receiver_config.<name>` at call time, or "
        f"monkeypatching it will silently do nothing."
    )
