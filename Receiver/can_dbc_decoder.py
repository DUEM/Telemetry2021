import logging
from typing import Union, Tuple

import cantools.database
from Receiver import receiver_config

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class DbcDecoder:
    def __init__(self, source_files=None):
        if source_files is None:
            # read at call time so monkeypatching receiver_config takes effect
            source_files = receiver_config.dbc_files
        database = cantools.database.Database()
        for dbc_file in source_files:
            database.add_dbc_file(dbc_file)
        self.database = database

    def decode_can_msg(
        self, can_id, msg_bytes
    ) -> Tuple[str, str, dict[str, Union[int, float, str]]]:
        """Decode a CAN message into its name, sender and signal values.

        Signal values are int or float, except for signals whose dbc unit is
        "ascii", which are returned as a single character str. Storers rely on
        this: a str is quoted by influx line protocol and written as text by
        openpyxl and the csv writers.

        Returns:
            (message name, sender, {signal name: value})
        """
        decode_msg: dict[str, Union[int, float, str]]
        message = self.database.get_message_by_frame_id(can_id)
        decode_msg = message.decode(msg_bytes)
        name = message.name
        sender = message.senders
        if len(sender) > 1:
            logger.warning("More than one sender present for message %s", name)
        if len(sender) >= 1:
            sender = sender[0]
        else:
            sender = ""

        # Signals marked with the "ascii" unit in the dbc carry a character, not
        # a number (the GPS hemisphere indicators N/S and E/W, sent as a char by
        # the car). Decode to str so every storer renders them as text; bytes
        # would leak a b'N' repr into the csv outputs.
        for signal in message.signals:
            if signal.unit == "ascii":
                decode_msg[signal.name] = chr(decode_msg[signal.name])
        return name, sender, decode_msg
