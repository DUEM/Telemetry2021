from datetime import datetime, timedelta, timezone
from typing import Optional
from crccheck.crc import Crc16Modbus
from binascii import hexlify
from cantools.database import DecodeError

import numpy as np
from numpy import uint32
import logging
from Receiver.can_dbc_decoder import DbcDecoder

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class TelemetryParser:
    def __init__(self):
        self.decoder = DbcDecoder()
        # use this by default until the pi rtc goes out of sync (i.e the UPS
        # fails). It can be resynced if reconnected to internet.
        self.last_gps_time: datetime = datetime.now(timezone.utc)
        # Time since time variables were last updated in seconds
        # #round(time.time() * 1000). Using numpy to force unsigned and integer
        # overflows are needed.
        self.time_fetched: uint32 = uint32(0)

    def __get_time(self, received_millis: uint32) -> datetime:
        # uint32 subtraction already wraps around correctly (e.g. 100 - (2**32 - 1000)
        # -> 1100), so no extra unsigning is needed here. This works as long as the
        # GPS update is not older than 2**32-1 milliseconds.
        with np.errstate(over="ignore"):
            millis_delta: uint32 = received_millis - self.time_fetched

        current_time = self.last_gps_time + timedelta(milliseconds=millis_delta.item())
        logger.debug(
            "millis_delta: %i -> Current Time: %s",
            millis_delta.item(),
            current_time.strftime("%Y-%m-%d %H:%M:%S.%f"),
        )
        return current_time

    # TRANSLATE MESSAGE REGION
    def translate_msg(
        self, msg_bytes_and_time: bytearray
    ) -> tuple[
        str, str, dict, datetime, bool
    ]:  # Format: TI0 TI1 TI2 TI3 ID0 ID1 DLC B0 B1 B2 B3 B4 B5 B6 B7 CRC0 CRC1 (NOTE that end of frame marker is not included)
        logger.debug("Translating -> %s", msg_bytes_and_time)

        can_msg_bytes = msg_bytes_and_time[4:]

        # CRC check
        msg_crc_status = self.__check_crc(msg_bytes_and_time)
        if not msg_crc_status:
            logger.debug("CRC FAILED (ignoring message) ")
            return (
                "CRCFail",
                "",
                {"Data": hexlify(msg_bytes_and_time)},
                self.last_gps_time,
                False,
            )

        # convert received millis delta time
        received_millis_time = np.frombuffer(
            msg_bytes_and_time[:4], dtype=uint32
        )[0]
        msg_time = self.__get_time(received_millis_time)

        # do a lookup in spreadsheet using can id to work out can message type
        can_id = self.get_can_id(msg_bytes_and_time)

        # Data bytes: exactly the DLC declares, never the CRC that follows them
        # (Format: TI0..TI3 ID0 ID1 DLC B0..B(DLC-1) CRC0 CRC1)
        dlc = can_msg_bytes[2] if len(can_msg_bytes) > 2 else 0
        frame_data = can_msg_bytes[3:-2]
        if len(frame_data) < dlc:
            logger.warning(
                "CAN ID %x: DLC is %i but the frame has %i data bytes",
                can_id, dlc, len(frame_data),
            )
            return (
                "DLC MISMATCH",
                "ERROR",
                {"ID": can_id, "DLC": dlc, "Bytes": len(frame_data)},
                msg_time,
                msg_crc_status,
            )
        if len(frame_data) > dlc:
            logger.warning(
                "CAN ID %x: DLC is %i but the frame has %i data bytes, ignoring the extra bytes",
                can_id, dlc, len(frame_data),
            )
        frame_data = frame_data[:dlc]

        # Translate
        try:
            message_name, message_source, decoded_message = self.decoder.decode_can_msg(
                can_id, frame_data
            )
        except KeyError:
            logger.warning("No entry in dbc for CAN ID %x", can_id)
            return "ID UNRECOGNISED", "ERROR", {"ID": can_id}, msg_time, msg_crc_status
        except DecodeError as error:
            # e.g. fewer data bytes than the message's length in the dbc file
            logger.warning("CAN ID %x could not be decoded: %s", can_id, error)
            return "DECODE ERROR", "ERROR", {"ID": can_id, "DLC": dlc}, msg_time, msg_crc_status

        if can_id == 0x0F6 and decoded_message["GpsDay"] != 0:
            self.update_last_gps_time(decoded_message, received_millis_time)
        return message_name, message_source, decoded_message, msg_time, msg_crc_status

    def update_last_gps_time(self, gps_message, received_millis_time):
        logger.debug("Updating GPS time...")
        try:
            self.last_gps_time = datetime(
                hour=gps_message["GpsHour"],
                minute=gps_message["GpsMinute"],
                second=gps_message["GpsSeconds"],
                day=gps_message["GpsDay"],
                month=gps_message["GpsMonth"],
                year=2000 + gps_message["GpsYear"],
                tzinfo=timezone.utc,
            )  # msgData only contains last 2 digits of year so have to add 2000
            self.time_fetched = (
                received_millis_time  # update when data was last fetched
            )
            logger.debug(
                "GPS time is now: %s", self.last_gps_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        except ValueError:
            logger.exception("Invalid values for GPS time, %s", str(gps_message))

    @staticmethod
    def get_can_id(msg_bytes_and_time: bytearray) -> Optional[int]:
        """Read the CAN ID (ID0 ID1) from a raw frame.

        Returns None if the frame is too short to hold one, which can happen
        for corrupted frames that fail the CRC check.
        """
        if len(msg_bytes_and_time) < 6:
            return None
        return msg_bytes_and_time[4] << 8 | msg_bytes_and_time[5]

    @staticmethod
    def __check_crc(msg_bytes: bytearray) -> bool:
        data = msg_bytes[0:-2]  # All except the last two
        crc_rcvd = int.from_bytes(
            msg_bytes[-2:], "big"
        )  # Convert received CRC code to int
        crc_calc = Crc16Modbus.calc(data)
        return crc_calc == crc_rcvd
