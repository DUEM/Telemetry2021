"""For batch import of data to influx

Does it in batch instead of by line and will be significantly faster compared to
telemetry Storer

usage:
    `hex2influx.py [-h] -i HEXFILE`
example:
    `python hex2influx.py -i 23071805.BIN`
"""

import argparse
from time import time
from typing import NamedTuple

import tqdm
from influxdb import InfluxDBClient

from Receiver.telemetry_parser3 import TelemetryParser
from Receiver.frame_reader import read_frames
from datetime import datetime


class influxCredentials(NamedTuple):
    # influx configuration - edit these
    username: str = "admin"
    password: str = "password"
    db: str = "Test22DB"  # "PalaceGreen_2022"
    host: str = "127.0.0.1"
    port: int = 8086
    enabled: bool = True  # Default to true (otherwise i forget and get confused when theres no data in influx)


ifCredentials = influxCredentials()


def hex2influx(hex_file, telemetry_parser=None) -> None:
    """Convert hex file to influx

    In contrast to telemetryStorer this write up to 5000 CAN messages at a time.

    Args:
        hex_file: hex file path
        telemetry_parser: parser to decode with, one is created if not given

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
        if msg_item == "ID UNRECOGNISED":
            continue
        data.append(
            to_point(msg_item, msg_source, msg_body, msg_time, msg_crc_status))
    influxClient = InfluxDBClient(host=ifCredentials.host,
                                  port=ifCredentials.port,
                                  username=ifCredentials.username,
                                  password=ifCredentials.password,
                                  database=ifCredentials.db)
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
    point = f'{msgSource}/{msgItem} '
    for key, value in msgBody.items():
        if isinstance(value, bytes):
            value = '"' + str(value, encoding='utf8') + '"'
        point += f'{key}={value},'
    point = point[:-1]
    point += f' {int(msgTime.timestamp() * 1e3)}'  # convert from seconds to ms
    return point


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import hex file to influxdb, configure the influx "
                    "credentials in the script before running"
    )
    parser.add_argument(
        "-i",
        "--hexfile",
        action="store",
        type=str,
        help="Hex file to import",
        required=True,
    )
    # TODO: we can also consider taking a list of bin files?
    args = parser.parse_args()

    hex2influx(args.hexfile)
