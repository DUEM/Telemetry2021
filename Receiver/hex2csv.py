"""CLI Tool to convert offloaded binary files to csv.

This tool is backwards compatiable to HexReader and will output the csv in the
same format as the excel file.

usage:
    `hex2csv.py [-h] -i HEXFILE [-o OUTFILE] [-m {a,w}]`
example:
    `python hex2csv.py -i 23071805.BIN -o 230718.csv -m a`
"""
import argparse
from time import time

import numpy as np
import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

import logging, sys
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stdout))

from telemetryParser2 import translateMsg

parser = argparse.ArgumentParser(description="Convert hex file to csv")
parser.add_argument(
    "-i",
    "--hexfile",
    action="store",
    type=str,
    help="Hex file to convert",
    required=True,
)
parser.add_argument(
    "-o",
    "--outfile",
    action="store",
    type=str,
    help="Out csv file path",
    default="output.csv",
)
parser.add_argument(
    "-m",
    "--mode",
    action="store",
    type=str,
    help="File writing mode: append or overwrite",
    default="a",
    choices=["a", "w", "x"],
)
args = parser.parse_args()
# TODO: we can also consider taking a list of bin files?

hexfile = args.hexfile
outfile = args.outfile
mode = args.mode


def hex2csv(hex_file, output_csv="output.csv", csv_write_mode=mode) -> None:
    """Convert hex file to csv

    Requires to be executed in a location that telemetryParser2.py can locate
    the config correctly.

    Args:
        hex_file: hex file path
        output_csv: output file path
        csv_write_mode: write mode for the output csv, either "a" for append or
        "w" for overwrite

    Returns:
            None
    """
    end_of_frame_marker = b"\x7E"
    time_start = time()
    with open(hex_file, mode="rb") as file:
        input_bytes = file.readlines()
    msgs = bytearray().join(input_bytes).split(end_of_frame_marker)
    with open(output_csv, csv_write_mode) as file:
        with logging_redirect_tqdm():
            for msg in tqdm.tqdm(msgs):
                msg_item, msg_source, msg_body, msg_time, msg_crc_status = translateMsg(msg)
                if msg_crc_status:
                    recievedMillisTime = np.frombuffer(msg[0:4],
                                                       dtype=np.uint32)[0]
                else:
                    recievedMillisTime = -1
                msg_body = [",".join([str(i), str(j)]) for i, j in msg_body.items()]
                msg_body = msg_body + (8 - len(msg_body)) * 2 * [""]
                line = (
                    f'{msg_time.strftime("%d/%m/%Y")},{msg_time.strftime("%T.%f")},{msg_item},'
                    f'{msg_source},{",".join(msg_body)},{msg_crc_status},{recievedMillisTime}\n'
                )
                file.write(line)
    print(f"Converted to csv in: {time() - time_start} seconds")


hex2csv(hexfile, outfile, mode)
