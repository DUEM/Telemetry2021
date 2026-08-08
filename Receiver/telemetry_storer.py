import logging
from typing import List

from Receiver.telemetry_parser3 import TelemetryParser
from Receiver.receiver_config import ifCredentials, xlsxOutputFile, csvOutputFile
from Receiver.storer_extension import StorerExtension, ExcelStorer, Influx1Storer, CSVStorer

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class TelemetryStorer:
    """Decodes and store the CAN message."""
    def __init__(
        self, parser: TelemetryParser, storage_plugin_list: List[StorerExtension] = None
    ):
        self.parser = parser
        self.storage_plugin_list = storage_plugin_list

    def store_data(self, msg: bytearray) -> None:
        """Decode and store the message.


        Args:
            msg: The message in byte array

        """
        (
            msg_item,
            msg_source,
            msg_body,
            msg_time,
            msg_crc_status,
        ) = self.parser.translate_msg(msg)
        for storage_plugin in self.storage_plugin_list:
            storage_plugin.store_data(
                msg_item, msg_source, msg_body, msg_time, msg_crc_status
            )

    def end_session(self):
        for storage_class in self.storage_plugin_list:
            storage_class.close()


telemetry_parser = TelemetryParser()


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
        storer_extension_list = []
        if xlsxOutputFile != "":
            excel_storer = ExcelStorer(xlsxOutputFile)
            storer_extension_list.append(excel_storer)
        if csvOutputFile != "":
            csv_storer = CSVStorer(csvOutputFile)
            storer_extension_list.append(csv_storer)
        if ifCredentials.enabled:
            influx_storer = Influx1Storer(ifCredentials)
            storer_extension_list.append(influx_storer)
        self._telemetry_storer = TelemetryStorer(
            telemetry_parser, storage_plugin_list=storer_extension_list
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
