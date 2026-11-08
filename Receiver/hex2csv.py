"""CLI Tool to convert offloaded binary files to csv.

This tool is backwards compatible with HexReader and outputs the csv in the
same layout as the Excel output: time, item, source, up to eight pairs of field
name and value, CRC result and the board's millis.

Run it as a module from the top of the repository (it imports the `Receiver`
package, so `python hex2csv.py` from inside Receiver/ does not work).

usage:
    `python3 -m Receiver.hex2csv [-h] -i HEXFILE [-o OUTFILE] [-m {a,w}]`
example:
    `python3 -m Receiver.hex2csv -i 23071805.BIN -o 230718.csv -m a`
"""
import argparse
from time import time

import numpy as np
import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from Receiver.telemetry_parser3 import TelemetryParser
from Receiver.frame_reader import read_frames

mode = "a"
def hex2csv(hex_file, output_csv="output.csv", csv_write_mode=mode, telemetry_parser=None) -> None:
    """Convert hex file to csv

    Decodes with the dbc files listed in receiver_config. Their paths are
    resolved relative to the repository, so this can be run from anywhere.

    Args:
        hex_file: hex file path
        output_csv: output file path
        csv_write_mode: write mode for the output csv, either "a" for append or
        "w" for overwrite

    Returns:
            None
    """
    if telemetry_parser is None:
        telemetry_parser = TelemetryParser()
    time_start = time()
    msgs = read_frames(hex_file)
    with open(output_csv, csv_write_mode) as file:
        with logging_redirect_tqdm():
            for msg in tqdm.tqdm(msgs):
                msg_item, msg_source, msg_body, msg_time, msg_crc_status = telemetry_parser.translate_msg(msg)
                if msg_crc_status:
                    recievedMillisTime = np.frombuffer(msg[0:4],
                                                       dtype=np.uint32)[0]
                else:
                    recievedMillisTime = -1
                msg_body = [",".join([str(i), str(j)]) for i, j in msg_body.items()]
                msg_body = msg_body + (8 - len(msg_body)) * 2 * [""]
                line = (
                    f'{msg_time.strftime("%d/%m/%Y %T.%f")},{msg_item},'
                    f'{msg_source},{",".join(msg_body)},{msg_crc_status},{recievedMillisTime}\n'
                )
                file.write(line)
    print(f"Converted to csv in: {time() - time_start} seconds")


if __name__ == '__main__':
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
        choices=["a", "w"],
    )
    args = parser.parse_args()
    # TODO: we can also consider taking a list of bin files?

    hexfile = args.hexfile
    outfile = args.outfile
    mode = args.mode
    hex2csv(hexfile, outfile, mode)
