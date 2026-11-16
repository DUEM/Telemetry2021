import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List

from Receiver.telemetry_parser import TelemetryParser
from Receiver import receiver_config
from Receiver.storer_extension import (
    StorerExtension,
    ExcelStorer,
    Influx1Storer,
    CSVStorer,
    BinStorer,
)

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class TelemetryStorer:
    """Decodes and store the CAN message."""
    def __init__(
        self, parser: TelemetryParser, storage_plugin_list: List[StorerExtension] = None
    ):
        self.parser = parser
        self.storage_plugin_list = storage_plugin_list or []

    def store_data(self, msg: bytearray) -> None:
        """Decode and store the message.


        Args:
            msg: The message in byte array

        """
        # raw frame first, so it is kept even if decoding fails
        for storage_plugin in self.storage_plugin_list:
            storage_plugin.store_raw(msg)
        (
            msg_item,
            msg_source,
            msg_body,
            msg_time,
            msg_crc_status,
        ) = self.parser.translate_msg(msg)
        can_id = self.parser.get_can_id(msg)
        logger.info(
            "%s %s %s/%s %s CRC %s",
            msg_time.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "ID ?" if can_id is None else "0x%03X" % can_id,
            msg_source,
            msg_item,
            msg_body,
            "OK" if msg_crc_status else "FAIL",
        )
        for storage_plugin in self.storage_plugin_list:
            storage_plugin.store_data(
                msg_item, msg_source, msg_body, msg_time, msg_crc_status
            )

    def end_session(self):
        for storage_class in self.storage_plugin_list:
            storage_class.close()


def session_log_file(folder, extension: str, started: datetime) -> Path:
    """Path of this session's log file in `folder`, e.g.
    <folder>/telem-received-2026-11-15-143012.csv, creating the folder if needed."""
    os.makedirs(folder, exist_ok=True)
    name = f"{receiver_config.sessionLogName}-{started:%Y-%m-%d-%H%M%S}.{extension}"
    return Path(folder) / name


class StorerWrapper:
    """Wrapper to store data and end session via single methods.

    Wrapper to handle lazy initialisation of the storer to provide backwards
    compatibility to the store_data and end_session functions.

    Attributes:
        telemetry_storer:
    """

    def __init__(self):
        self._is_storer_init = False
        self._telemetry_storer = None

    @property
    def telemetry_storer(self):
        if not self._is_storer_init:
            self.init_storer()
        return self._telemetry_storer

    def init_storer(self):
        # read config at call time so monkeypatching receiver_config takes effect
        storer_extension_list = []
        started = datetime.now()  # local time, shared by all of this session's files
        if receiver_config.xlsxEnabled:
            excel_storer = ExcelStorer(
                session_log_file(receiver_config.xlsxOutputFolder, "xlsx", started),
                save_interval=receiver_config.xlsxSaveInterval,
            )
            storer_extension_list.append(excel_storer)
        if receiver_config.csvEnabled:
            csv_storer = CSVStorer(
                session_log_file(receiver_config.csvOutputFolder, "csv", started)
            )
            storer_extension_list.append(csv_storer)
        if receiver_config.binEnabled:
            bin_storer = BinStorer(
                session_log_file(receiver_config.binOutputFolder, "BIN", started)
            )
            storer_extension_list.append(bin_storer)
        if receiver_config.ifCredentials.enabled:
            influx_storer = Influx1Storer(receiver_config.ifCredentials)
            storer_extension_list.append(influx_storer)
        self._telemetry_storer = TelemetryStorer(
            TelemetryParser(), storage_plugin_list=storer_extension_list
        )
        self._is_storer_init = True

    def store_data(self, *args):
        self.telemetry_storer.store_data(*args)

    def end_session(self):
        self.telemetry_storer.end_session()


storer_wrapper = StorerWrapper()


def store_data(*args):
    storer_wrapper.store_data(*args)


def end_session():
    storer_wrapper.end_session()
