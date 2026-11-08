"""Utility script to read multiple bin files

It obtains a list of bin files via regex and runs hex2influx for each of them.
Edit `bin_folder` and `regex_pattern` below first, then run it as a module from
the top of the repository:

    `python3 -m Receiver.batch_Read_Hex`
"""

import logging
import subprocess as sp
import os
import re
import sys
from time import time

timeStart = time()
# TODO: set the to the folder containing all the bin files
bin_folder=r'E:\2023Dunsfold2'
# TODO: set regex pattern to filter all the interested bin files
regex_pattern = r"231018[0-9]{2}\.BIN"

dir = os.listdir(bin_folder)

vaild_list = []
for file in dir:
    mtch = re.match(regex_pattern, file)
    if mtch is not None:
        vaild_list.append(mtch.group(0))
        print(mtch.group(0))

for file in vaild_list:
    # same interpreter, run as a module so the Receiver package can be imported
    sp.run([sys.executable, "-m", "Receiver.hex2influx", "-i", os.path.join(bin_folder, file)])


timeEnd = time()
timeTaken = timeEnd - timeStart
print(f'\n All files converted in {timeTaken} seconds.')