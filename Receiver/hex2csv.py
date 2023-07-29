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
    choices=["a", "w"],
)
args = parser.parse_args()
# TODO: we can also consider taking a list of bin files?

hexfile = args.hexfile
outfile = args.outfile
mode = args.mode


def hex2csv(hex_file, output_csv="output.csv") -> None:
    """Convert hex file to csv

    Requires to be executed in a location that telemetryParser2.py can locate
    the config correctly.

    :param hex_file: hex file path
    :param output_csv: output file path
    :return: None
    """
    end_of_frame_marker = b"\x7E"
    time_start = time()
    with open(hex_file, mode="rb") as file:
        input_bytes = file.readlines()
    msgs = bytearray().join(input_bytes).split(end_of_frame_marker)
    with open(output_csv, mode) as file:
        for msg in msgs:
            msg_item, msg_source, msg_body, msg_time, msg_crc_status = translateMsg(msg)
            msg_body = [",".join([str(i), str(j)]) for i, j in msg_body.items()]
            msg_body = msg_body + (8 - len(msg_body)) * 2 * [""]
            line = f'{msg_item},{msg_source},{",".join(msg_body)},' \
                   f'{msg_time.strftime("%d/%m/%Y %T.%f")},{msg_crc_status}\n'
            file.write(line)
    print(f"Converted to csv in: {time()-time_start} seconds")


hex2csv(hexfile, outfile)
