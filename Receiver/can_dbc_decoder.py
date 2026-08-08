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
    ) -> Tuple[str, str, dict[str, Union[int, float, str, bytes]]]:
        decode_msg: dict[str, Union[int, float, str, bytes]]
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

        # convert back to bytes for backwards compatibility
        if can_id == 248:
            decode_msg["GpsLat"] = decode_msg["GpsLat"].to_bytes(1, "little")
        elif can_id == 249:
            decode_msg["GpsLon"] = decode_msg["GpsLon"].to_bytes(1, "little")
        return name, sender, decode_msg
