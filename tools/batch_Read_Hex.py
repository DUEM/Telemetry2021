"""Import every SD card log file in a directory into influx.

Finds the bin files in a directory whose names match a regular expression, and
runs hex2influx.py (in this directory) on each of them, in name order. By
default it matches the board's log file names, YYMMDDNN.BIN (any case).

Run it as a script, from any directory. Use -n first to check which files
would be imported.

usage:
    `python3 tools/batch_Read_Hex.py [-h] -d DIRECTORY [-p PATTERN] [-n]`
examples (from the top of the repository):
    `python3 tools/batch_Read_Hex.py -d /media/sdcard -n`
    `python3 tools/batch_Read_Hex.py -d /media/sdcard -p "231018[0-9]{2}\\.BIN"`
"""

import argparse
import re
import subprocess as sp
import sys
from pathlib import Path
from time import time

HEX2INFLUX = Path(__file__).resolve().parent / "hex2influx.py"

# The board names its log files YYMMDDNN.BIN (see Telemetry/README.md)
DEFAULT_PATTERN = r"[0-9]{8}\.BIN"


def find_bin_files(directory, pattern=DEFAULT_PATTERN) -> list:
    """Files in `directory` whose whole name matches `pattern` (any case), sorted."""
    regex = re.compile(pattern, re.IGNORECASE)
    return sorted(
        f for f in Path(directory).iterdir() if f.is_file() and regex.fullmatch(f.name)
    )


def batch_import(bin_files) -> list:
    """Run hex2influx.py on each file. Returns the files that failed."""
    failed = []
    for bin_file in bin_files:
        print(f"Importing {bin_file}")
        # run with the same Python (and so the same virtual environment) as this script
        result = sp.run([sys.executable, str(HEX2INFLUX), "-i", str(bin_file)])
        if result.returncode != 0:
            failed.append(bin_file)
    return failed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Import every bin file in a directory to influxdb using "
        "hex2influx.py. Configure the influx credentials in hex2influx.py "
        "before running."
    )
    parser.add_argument(
        "-d",
        "--directory",
        action="store",
        type=str,
        help="Directory containing the bin files",
        required=True,
    )
    parser.add_argument(
        "-p",
        "--pattern",
        action="store",
        type=str,
        help="Regular expression the whole file name must match (any case). "
        f"Default: {DEFAULT_PATTERN} (the board's YYMMDDNN.BIN log files)",
        default=DEFAULT_PATTERN,
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Only list the files that would be imported",
    )
    args = parser.parse_args(argv)

    if not Path(args.directory).is_dir():
        parser.error(f"not a directory: {args.directory}")

    bin_files = find_bin_files(args.directory, args.pattern)
    if not bin_files:
        print(f"No files in {args.directory} match {args.pattern}")
        return 1
    if args.dry_run:
        print("\n".join(str(f) for f in bin_files))
        print(f"{len(bin_files)} file{'s' if len(bin_files) != 1 else ''} would be imported")
        return 0

    time_start = time()
    failed = batch_import(bin_files)
    print(
        f"\n{len(bin_files) - len(failed)} of {len(bin_files)} files imported "
        f"in {time() - time_start:.1f} seconds."
    )
    if failed:
        print("Failed: " + ", ".join(str(f) for f in failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
