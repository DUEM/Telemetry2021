import csv
import logging
import os
import time

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Union

from Receiver.frame_reader import END_OF_FRAME_MARKER, UnterminatedPiece

from openpyxl import load_workbook, Workbook
from os.path import exists as fileExists

from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class StorerExtension(ABC):
    """Represents a storage option.

    Each class represents a storage option (e.g. csv, excel, influx, bin...)
    The methods `store_data` and `close` must be implemented. `store_raw`
    can be overridden to receive each frame as received, before decoding.

    Additional methods can be implemented to be called by either `store_data`
    or `close`.

    To add a new storage option, subclass this and then add it to
    `StorerWrapper.init_storer` in `telemetry_storer.py` behind a setting in
    `config.yml` (read by `receiver_config.py`), following how `CSVStorer` is wired up. Storers can
    also be passed directly to `TelemetryStorer` if the wrapper is not used.
    """

    @abstractmethod
    def store_data(
        self,
        msg_item: str,
        msg_source: str,
        msg_body: dict,
        msg_time: datetime,
        msg_crc_status: bool,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    def store_raw(self, frame: bytes) -> None:
        """Called with each frame exactly as received, before it is decoded.

        Does nothing unless overridden: only storers that keep the raw radio
        data (e.g. `BinStorer`) need it.
        """


class ExcelStorer(StorerExtension):
    """Storer for an Excel file.

    A new Excel will be created if not already present and a sheet named
    `Translated Messages` will be created.

    Each row will correspond to a single CAN message.

    When appending to an existing file, a gap of three lines will be added
    before the new session.

    Saving rewrites the whole workbook, so the time it takes grows with the
    file. Rows are therefore saved at most every `save_interval` seconds (the
    first row is saved straight away, so the file appears as soon as data
    arrives), and again on `close`.
    """

    def __init__(
        self, xlsx_output_file: Union[str, os.PathLike], save_interval: float = 10.0
    ):
        self.xlsx_output_file = xlsx_output_file
        self.save_interval = save_interval
        # -inf so the first row is saved immediately
        self._last_save: float = float("-inf")
        # skip first row as that is for column labels
        self.xlsx_out_row_pointer: int = 2
        # if '', disable xlsx output
        if self.xlsx_output_file == "":
            logger.error("No excel output path provided.")
            return

        if fileExists(self.xlsx_output_file):
            self.xlsx_out_workbook = load_workbook(
                self.xlsx_output_file, read_only=False
            )
            if "Translated Messages" in self.xlsx_out_workbook.sheetnames:
                self.xlsx_out_worksheet = self.xlsx_out_workbook["Translated Messages"]
                self.xlsx_out_row_pointer = self.xlsx_out_worksheet.max_row + 3
                # leave gap in between sessions. Just to make reader aware
                # that more than one session continued with the same file
            else:
                self.create_new_sheet()
        else:
            self.xlsx_out_workbook = Workbook()  # Create new workbook
            self.create_new_sheet()

    def create_new_sheet(self):
        # Create the new sheet
        self.xlsx_out_worksheet = self.xlsx_out_workbook.create_sheet(
            title="Translated Messages"
        )

        # Add columns labels at the top of the sheet
        for i, label in enumerate(["Date", "Time", "Source", "Item", "Data..."]):
            self.xlsx_out_worksheet.cell(column=i + 1, row=1, value=label)

        # longest record is 19 cells so put CRC in 20th
        self.xlsx_out_worksheet.cell(column=21, row=1, value="CRC check")

        # Add filters to columns (Source and Item)
        self.xlsx_out_worksheet.auto_filter.ref = "A1:T" + str(
            self.xlsx_out_worksheet.max_row
        )

        # Set the pointer to write at the first row under the labels
        self.xlsx_out_row_pointer = 2

    def store_data(
        self,
        msg_item: str,
        msg_source: str,
        msg_body: dict,
        msg_time: datetime,
        msg_crc_status: bool,
    ) -> None:
        xlsx_out_workbook = self.xlsx_out_workbook
        xlsx_out_worksheet = self.xlsx_out_worksheet
        xlsx_out_row_pointer = self.xlsx_out_row_pointer
        xlsx_output_file = self.xlsx_output_file

        msg_time = msg_time.replace(tzinfo=None)
        xlsx_out_worksheet.cell(column=1, row=xlsx_out_row_pointer, value=msg_time)
        xlsx_out_worksheet.cell(column=2, row=xlsx_out_row_pointer, value=msg_time)

        xlsx_out_worksheet.cell(column=3, row=xlsx_out_row_pointer, value=msg_source)
        xlsx_out_worksheet.cell(column=4, row=xlsx_out_row_pointer, value=msg_item)

        column_pointer: int = 5
        for data_label, value in msg_body.items():
            xlsx_out_worksheet.cell(
                column=column_pointer, row=xlsx_out_row_pointer, value=data_label
            )
            xlsx_out_worksheet.cell(
                column=column_pointer + 1, row=xlsx_out_row_pointer, value=value
            )
            column_pointer += 2

        xlsx_out_worksheet.cell(
            column=21, row=xlsx_out_row_pointer, value=msg_crc_status
        )

        self.xlsx_out_row_pointer += 1

        # Save at most every save_interval seconds, not after every row. If the
        # program does not exit cleanly (e.g. the computer is unplugged), rows
        # since the last save are lost from the xlsx (and a save cut short can
        # corrupt it). This is fine as it can be rebuilt from the telemetry hex
        # dump on the SD card.
        now = time.monotonic()
        if now - self._last_save >= self.save_interval:
            xlsx_out_workbook.save(xlsx_output_file)
            self._last_save = now

    def close(self) -> None:
        logger.info("Closing xlsx output file")
        self.xlsx_out_workbook.save(self.xlsx_output_file)
        self.xlsx_out_workbook.close()


class Influx1Storer(StorerExtension):
    """Storer for Influx db 1.x

    Storer for Influx db 1.x utilising the python-influxdb library.
    This storer does not support Influx 2 or 3.
    """

    def __init__(self, if_credentials):
        # if false, do not initialise or enable influx output
        if if_credentials.enabled:
            self.influx_client = InfluxDBClient(
                host=if_credentials.host,
                port=if_credentials.port,
                username=if_credentials.username,
                password=if_credentials.password,
                database=if_credentials.db,
            )
        else:
            logger.error("Influx credentials not enable.")

    def store_data(
        self,
        msg_item: str,
        msg_source: str,
        msg_body: dict,
        msg_time: datetime,
        msg_crc_status: bool,
    ) -> None:
        if not msg_crc_status:
            # CRC failed, message was corrupted. Do not add to database
            logger.debug(
                "CRC FAILED for %s/%s at %s",
                msg_source,
                msg_item,
                msg_time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            return
        if not msg_body:
            # e.g. the MPPT poll requests, which carry no data: influx
            # rejects a point with no fields
            logger.debug("No fields to store for %s/%s", msg_source, msg_item)
            return

        # Write data and check if successful
        body = [
            {
                # NOTE: Should check format.
                # Old format was "measurement": msgSource but assumes that
                # all fields in all items are uniquely named
                "measurement": msg_source + "/" + msg_item,
                "time": msg_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                # dictionary of all fields and corresponding values in CAN message
                "fields": msg_body,
            }
        ]
        try:
            influx_success = self.influx_client.write_points(
                body, time_precision="ms", protocol="json"
            )
        except InfluxDBClientError as e:
            # e.g. database missing or bad credentials. Log and drop this
            # message rather than letting it stop the receiver.
            logger.error(
                "Influx rejected write for %s/%s: %s", msg_source, msg_item, e
            )
            return
        if influx_success is False:
            logger.warning(
                "Error writing to Influx for %s/%s (%s)", msg_source, msg_item, msg_body
            )

    def close(self) -> None:
        logger.info("Closing InfluxDB connection")
        self.influx_client.close()


class CSVStorer(StorerExtension):
    """Storer for CSV file output.

    Writes decoded CAN messages to a CSV file with the following columns:
    - Timestamp: ISO format datetime
    - Source: Message source (e.g., 'Orion', 'Tritium')
    - Item: Message name (e.g., 'PackParameters')
    - Data columns: One value per column (field_name, field_value)
    - CRC: CRC validation status

    A header row with column labels is added when a new file is created.
    """

    def __init__(self, csv_output_file: Union[str, os.PathLike]):
        """Initialize CSV storer.

        Args:
            csv_output_file: Path to the CSV output file. Will be created if
                it does not exist. Existing files will be appended to.

        Raises:
            IOError: If the file cannot be opened for writing.
        """
        self.csv_output_file = csv_output_file
        self.csv_file = None
        self.csv_writer = None

        try:
            # Check if file exists to determine if we need to write headers
            file_exists = os.path.exists(csv_output_file)

            # Open file in append mode
            self.csv_file = open(csv_output_file, mode='a', newline='', encoding='utf-8')
            self.csv_writer = csv.writer(self.csv_file)

            # Write header if file is new
            if not file_exists:
                self._write_header()

        except IOError as e:
            logger.error(f"Failed to open CSV file {csv_output_file}: {e}")
            raise

    def _write_header(self) -> None:
        """Write CSV header row."""
        if self.csv_writer:
            headers = ["Timestamp", "Source", "Item", "Message Body", "CRC"]
            self.csv_writer.writerow(headers)
            self.csv_file.flush()

    def store_data(
        self,
        msg_item: str,
        msg_source: str,
        msg_body: dict,
        msg_time: datetime,
        msg_crc_status: bool,
    ) -> None:
        """Store decoded message data to CSV file.

        Args:
            msg_item: Message name/identifier
            msg_source: Message source (sender)
            msg_body: Dictionary of decoded message fields and values
            msg_time: Timestamp of the message
            msg_crc_status: CRC validation result

        Note:
            Message body fields are written as comma-separated key-value pairs
            in a single column for compact representation.
        """
        if not self.csv_writer:
            logger.warning("CSV file not initialized; skipping store_data")
            return

        try:
            # Format message body as key=value pairs
            msg_body_str = ",".join(
                f"{key}={value}" for key, value in msg_body.items()
            )

            # Write row: timestamp, source, item, body, crc
            row = [
                msg_time.isoformat(),
                msg_source,
                msg_item,
                msg_body_str,
                msg_crc_status,
            ]
            self.csv_writer.writerow(row)
            self.csv_file.flush()

            logger.debug(
                f"Wrote to CSV: {msg_source}/{msg_item} at {msg_time.isoformat()}"
            )
        except Exception as e:
            logger.error(f"Error writing to CSV: {e}")

    def close(self) -> None:
        """Close the CSV file and flush any buffered data."""
        if self.csv_file:
            try:
                self.csv_file.close()
                logger.info(f"Closed CSV output file: {self.csv_output_file}")
            except Exception as e:
                logger.error(f"Error closing CSV file: {e}")
            finally:
                self.csv_file = None
                self.csv_writer = None


class BinStorer(StorerExtension):
    """Storer for the raw radio data, as received (a .BIN file).

    Writes every frame exactly as it arrived from the radio, each followed by
    the end of frame marker 0x7E, so the file has the same format as the SD
    card log on the vehicle (and the ESC-CODE receiver's BIN files). Frames
    that fail their CRC or have an unknown CAN ID are kept too. The file can
    be decoded later with tools/hex2csv.py or tools/hex2influx.py, or replayed
    through a virtual serial port (see the receiver README).

    A frame split by an unescaped 0x7E is written as it arrived, marker
    included, once all its pieces have been received. Frames split apart
    after radio losses are written back without the marker they did not have. Bytes after the last
    0x7E when the receiver stops (an unfinished frame) are not written.
    """

    def __init__(self, bin_output_file: Union[str, os.PathLike]):
        self.bin_output_file = bin_output_file
        # append, like the other storers, so an existing file is never lost
        self.bin_file = open(bin_output_file, mode="ab")

    def store_raw(self, frame: bytes) -> None:
        # bytes split off the front of a longer piece were not followed by a
        # marker when received (see frame_reader.split_run_together)
        marker = b"" if isinstance(frame, UnterminatedPiece) else END_OF_FRAME_MARKER
        self.bin_file.write(bytes(frame) + marker)
        self.bin_file.flush()  # a crash loses at most the frame in progress

    def store_data(
        self,
        msg_item: str,
        msg_source: str,
        msg_body: dict,
        msg_time: datetime,
        msg_crc_status: bool,
    ) -> None:
        pass  # the raw frame was already written by store_raw

    def close(self) -> None:
        logger.info("Closing BIN output file: %s", self.bin_output_file)
        self.bin_file.close()
