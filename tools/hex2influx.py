"""For batch import of data to influx

Does it in batch instead of by line and will be significantly faster compared to
telemetry Storer.

Uses the receiver's influx settings (ifCredentials in Receiver/receiver_config.py,
database DUSCiESC). Use -d to import into a different database, e.g. to keep an
old session apart from live data.

Run it as a script, from any directory. File paths are relative to the
directory you run it from.

usage:
    `python3 tools/hex2influx.py [-h] -i HEXFILE [-d DATABASE]`
example (from the top of the repository):
    `python3 tools/hex2influx.py -i 23071805.BIN`
"""

import argparse
from time import time

import tqdm
from influxdb import InfluxDBClient

import sys
from pathlib import Path

# Run as a script (python3 tools/<name>.py), so put the repository root on the
# import path to find the Receiver package. Works from any directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Receiver import receiver_config
from Receiver.telemetry_parser import TelemetryParser
from Receiver.frame_reader import read_frames
from datetime import datetime


def hex2influx(hex_file, telemetry_parser=None, database=None) -> None:
    """Convert hex file to influx

    In contrast to telemetry_storer this write up to 5000 CAN messages at a time.

    Args:
        hex_file: hex file path
        telemetry_parser: parser to decode with, one is created if not given
        database: database to import into; the receiver's (receiver_config) if not given

    Returns:
            None
    """
    if telemetry_parser is None:
        telemetry_parser = TelemetryParser()
    time_start = time()
    msgs = read_frames(hex_file)
    data = list()
    for msg in tqdm.tqdm(msgs, desc=hex_file):
        (
            msg_item,
            msg_source,
            msg_body,
            msg_time,
            msg_crc_status,
        ) = telemetry_parser.translate_msg(msg)
        if msg_source == "ERROR":  # unrecognised ID, DLC mismatch or decode error
            continue
        data.append(
            to_point(msg_item, msg_source, msg_body, msg_time, msg_crc_status))
    # read at call time, as the receiver does, so tests can patch receiver_config
    credentials = receiver_config.ifCredentials
    influxClient = InfluxDBClient(host=credentials.host,
                                  port=credentials.port,
                                  username=credentials.username,
                                  password=credentials.password,
                                  database=database or credentials.db)
    influx_success = influxClient.write_points(data, time_precision='ms',
                                               protocol='line', batch_size=5000)
    print(f"Imported to in: {time() - time_start} seconds")


def to_point(msgItem: str, msgSource: str, msgBody: dict, msgTime: datetime,
             msgCRCStatus: bool) -> str:
    """ Convert decoded message to influx line protocol.

    Args:
        msgItem: CAN msg Identifier.
        msgSource: Device Identifier.
        msgBody: key value pair of fields
        msgTime: Time of msg received.
        msgCRCStatus: Passed CRC check

    Returns:
        string for data formatted in influx line protocol
    """
    if not msgCRCStatus:  # CRC failed, message was corrupted. Do not add to database
        # print("CRC FAILED for " + msgSource + "/" + msgItem + " at " + msgTime.strftime("%Y-%m-%d %H:%M:%S"))
        return ''
    if not msgBody:  # e.g. the MPPT poll requests carry no data; influx needs at least one field
        return ''
    point = f'{msgSource}/{msgItem} '
    for key, value in msgBody.items():
        if isinstance(value, str):  # e.g. GPS hemisphere chars, quote for influx
            value = f'"{value}"'
        point += f'{key}={value},'
    point = point[:-1]
    point += f' {int(msgTime.timestamp() * 1e3)}'  # convert from seconds to ms
    return point


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import hex file to influxdb, using the influx settings "
                    "in Receiver/receiver_config.py"
    )
    parser.add_argument(
        "-i",
        "--hexfile",
        action="store",
        type=str,
        help="Hex file to import",
        required=True,
    )
    parser.add_argument(
        "-d",
        "--database",
        action="store",
        type=str,
        help="Database to import into (default: the receiver's, set in Receiver/receiver_config.py)",
        default=None,
    )
    args = parser.parse_args()

    hex2influx(args.hexfile, database=args.database)
