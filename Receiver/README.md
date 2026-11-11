# Receiver (telemetry laptop)

[LiveTelemetry.py](LiveTelemetry.py) reads radio frames from the XBee serial port, checks each frame's CRC and decodes it using the CAN database files in [../dbc/](../dbc/). Each decoded message is passed to the storage plugins enabled in [receiver_config.py](receiver_config.py):

* InfluxDB 1.x, database `DUSCiESC` on `localhost:8086`, for the Grafana dashboard to display (on by default)
* an Excel workbook (off by default)
* a CSV file (off by default)

Every decoded message is also printed to the terminal.

## Dependencies

Python 3.9 or later, and, from the top of the repository:

```shell
pip install -r Receiver/requirements.txt     # pyserial, influxdb, openpyxl, crccheck, numpy, cantools, tqdm
```

`influxdb` is the InfluxDB **1.x** client. The receiver will not work against InfluxDB 2.x or 3.x without code changes.

The user also needs read access to the serial port (`sudo usermod -aG dialout $USER`, then log out and in again).

The [live calculations](live_calculations/README.md) have their own, separate `requirements.txt`.

## Running

The receiver is a Python package, so run it as a module from the **top** of the repository (not from this directory):

```shell
python3 -m Receiver.LiveTelemetry
```

Press **Ctrl-C** to stop it. The output files and the InfluxDB connection are closed cleanly.

## Configuration

| Setting | Where | Default |
|---|---|---|
| Serial port | `SERIALPORT` at the top of [LiveTelemetry.py](LiveTelemetry.py) | `/dev/ttyUSB0` |
| Baud rate | `BAUD` in [LiveTelemetry.py](LiveTelemetry.py) | **115200** (must match the XBee) |
| InfluxDB host, port, user, password, database | `InfluxCredentials` in [receiver_config.py](receiver_config.py) | `localhost`, `8086`, `admin`, `password`, `DUSCiESC` |
| InfluxDB on / off | `enabled` in `InfluxCredentials` | on |
| Excel output | `xlsxOutputFile` in [receiver_config.py](receiver_config.py) | `''` (off) |
| Excel save interval | `xlsxSaveInterval` in [receiver_config.py](receiver_config.py) | **10** seconds |
| CSV output | `csvOutputFile` in [receiver_config.py](receiver_config.py) | `''` (off) |
| CAN database files | `dbc_files` in [receiver_config.py](receiver_config.py) | the four files in [../dbc/](../dbc/) |

Output file paths are relative to the directory the receiver is started from (normally the top of the repository). Existing Excel and CSV files are **appended to**, not overwritten. The `ExcelOutput/` and `Output/` directories are git-ignored, so session logs are not committed by accident.

## Radio frame format

Each frame from the vehicle is:

```
[millis 4B, little-endian][CAN ID 2B, big-endian][DLC 1B][data, DLC bytes][CRC16 2B, big-endian][0x7E]
```

* `millis` is the board's uptime in ms when the frame was sent. It is used for the timestamp (see [Timestamps](#timestamps)).
* The CRC is CRC-16/MODBUS (reflected polynomial `0xA001`, initial value `0xFFFF`), the same as AVR `_crc16_update` on the board. It is calculated over the millis, CAN ID, DLC and data bytes. The receiver **does** check it: frames that fail are dropped from InfluxDB and flagged `False` in the Excel/CSV output.
* `0x7E` marks the end of a frame and is **not** escaped inside the frame (see Known limitations in the top-level [README](../README.md#known-limitations)). Splitting a capture into frames is done in [frame_reader.py](frame_reader.py).

## CAN decoding (DBC files)

Messages are decoded with [cantools](https://cantools.readthedocs.io/) from the standard `.dbc` CAN database files in [../dbc/](../dbc/):

| File | Device(s) | Messages |
|---|---|---|
| [wavesculptor_22.dbc](../dbc/wavesculptor_22.dbc) | Tritium WaveSculptor motor controller, driver controls | motor, bus and status messages |
| [Orion.dbc](../dbc/Orion.dbc) | Orion BMS | `PackParameters` (0x700), `CellTempsDCL` (0x701), `CellVoltages` (0x702) |
| [MPPT.dbc](../dbc/MPPT.dbc) | MPPTs `Javed` and `Woof`, plus the board's MPPT poll requests | `Javed` (0x771), `Woof` (0x772), `MpptPollJaved` (0x711), `MpptPollWoof` (0x712) |
| [Telemetry.dbc](../dbc/Telemetry.dbc) | The telemetry board itself | GPS `TimeAndFix` (0xF6), `SpeedAndAngle` (0xF7), `Latitude` (0xF8), `Longitude` (0xF9), `AltitudeAndSatellites` (0xFA), `SystemStatusMessages` (0x111) |

**What every message and signal means, its unit and scaling, and what to query in Grafana:** see the generated [CAN signal reference (dbc/SIGNALS.md)](../dbc/SIGNALS.md). For an introduction to CAN and DBC files, and how this documentation is maintained, see [dbc/README.md](../dbc/README.md).

How a DBC entry maps to the output:

* The message name (`BO_ <id> <name>`) becomes the **Item**, e.g. `PackParameters`.
* The message's sender (the last word of the `BO_` line) becomes the **Source**, e.g. `Orion`.
* Each signal (`SG_`) becomes one field, using the DBC's scaling, offset and byte order.
* A signal with the unit `"ascii"` is decoded as a single character instead of a number. This is used for the GPS hemisphere characters `GpsLat` (N/S) and `GpsLon` (E/W).
* Value tables (`VAL_`, e.g. 255 = "Good") are documentation only: the receiver always stores the number, so InfluxDB fields stay numeric.

GPS latitude and longitude are stored **as sent by the GPS**, in NMEA `ddmm.mmmm` format, with the sign in the separate hemisphere character. They are not converted to decimal degrees by the receiver ([live_calculations/road_lookup.py](live_calculations/road_lookup.py) does this conversion).

The tests decode with the same `dbc/` files, so `pytest` catches a DBC change that breaks the expected output.

### Adding a new CAN message

Follow the steps in [dbc/README.md](../dbc/README.md#changing-or-adding-a-message-or-signal): edit the `.dbc` file (including a plain-English comment), regenerate `dbc/SIGNALS.md`, and run `pytest`. If you add a new `.dbc` file, also list it in `dbc_files` in [receiver_config.py](receiver_config.py). Then replay a capture that contains the message (see [Testing without hardware](#testing-without-hardware)) and check the decoded values.

Renaming a message, sender or signal, or changing its scaling, changes what is stored in InfluxDB; see the warning in [dbc/README.md](../dbc/README.md#changing-or-adding-a-message-or-signal).

Frames with a CAN ID that is not in any DBC file are logged as a warning and stored as Item `ID UNRECOGNISED`, Source `ERROR`, with the CAN ID as the only field.

## InfluxDB schema

You need to know this schema when building Grafana panels:

| Measurement | Fields | Example |
|---|---|---|
| `<Source>/<Item>` | One field per DBC signal, named as in the DBC | `Orion/PackParameters`: `PackCurrent`, `PackInstVoltage`, `PackSoc`, `RelayState` |
| `ERROR/ID UNRECOGNISED` | `ID` (the unknown CAN ID) | |

Measurement names contain `/` (and sometimes spaces), so they must be double-quoted in InfluxQL:

```shell
influx -database DUSCiESC -execute 'SELECT * FROM "Orion/PackParameters" LIMIT 10'
```

The [live calculations](live_calculations/README.md) write their results back to InfluxDB under their own measurements.

### Timestamps

Points are stamped with the **vehicle's GPS time**, not the laptop's receive time:

* Each `TimeAndFix` message (CAN ID 0xF6) with a valid date sets the reference time to the GPS time, along with the board's `millis` value when it was sent.
* Every other frame is stamped with that GPS time plus the difference between its `millis` and the reference `millis`.
* Until the first valid GPS time arrives, the reference is the laptop's clock when the receiver started, plus the board's uptime. Timestamps from before the first GPS fix are therefore only approximate.

## Output files

* **Excel** (`xlsxOutputFile`): sheet `Translated Messages`, one row per message: `Date`, `Time`, `Source`, `Item`, then pairs of field name and value, with the CRC result in column U. When appending, a three-row gap separates sessions. Saving rewrites the whole workbook, so it is saved at most every `xlsxSaveInterval` seconds (and straight away for the first row), plus once more when the receiver stops. Stop the receiver with Ctrl-C so the last rows are saved.
* **CSV** (`csvOutputFile`): one row per message: `Timestamp` (ISO 8601), `Source`, `Item`, `Message Body` (`name=value` pairs in one quoted column), `CRC`.

Note that `tools/hex2csv.py` (below) writes a **different** CSV layout.

## Offline tools (SD card logs)

The board writes every frame to its SD card as `YYMMDDNN.BIN`, in the same frame format as the radio link (see [../Telemetry/README.md](../Telemetry/README.md#sd-card)). The scripts in [../tools/](../tools/) decode those files after a session. They are ordinary Python scripts: run them with `python3 <path to script>` from any directory, with the virtual environment active. File names are relative to the directory you run them from. From the top of the repository:

```shell
# decode to CSV: time,item,source,name1,value1,...,name8,value8,crc_ok,millis
python3 tools/hex2csv.py -i 23071805.BIN -o 230718.csv -m a     # -m a = append (default), w = overwrite

# import into InfluxDB, in batches of 5000 points (much faster than the live receiver)
python3 tools/hex2influx.py -i 23071805.BIN

# import every log file in a directory (e.g. the SD card) into InfluxDB, using hex2influx.py
python3 tools/batch_Read_Hex.py -d /media/$USER/SDCARD -n     # -n: only list the files it would import
python3 tools/batch_Read_Hex.py -d /media/$USER/SDCARD
```

Add `-h` to any of these scripts to see all its options.

[hex2influx.py](../tools/hex2influx.py) has its **own** InfluxDB credentials at the top of the script (database `Test22DB`), not the ones in `receiver_config.py`. Edit them before use. Unlike the live receiver, it skips frames with unrecognised CAN IDs.

[batch_Read_Hex.py](../tools/batch_Read_Hex.py) runs `hex2influx.py` on each file in the directory given with `-d`, in name order. By default it picks the board's log files, named `YYMMDDNN.BIN` (in upper or lower case). To choose other files, give a regular expression that the whole file name must match with `-p`; for example, `-p "231018[0-9]{2}\.BIN"` picks only the files from 18 October 2023. At the end it reports how many files were imported, and lists any that failed.

## Testing without hardware (sofware in the loop, SIL)

**Unit tests.** From the top of the repository:

```shell
pip install -r Tests/requirements-test.txt
pytest
```

The tests replay the sample captures in [../Tests/data/](../Tests/data/) (`NRT.BIN`, `MPPT.BIN`) and compare the decoded output with the matching `.csv` files. They do not need InfluxDB.

**Live replay.** You can replay a capture through a virtual serial port. Note that this **writes to the live `DUSCiESC` database** unless you turn InfluxDB off in `receiver_config.py`.

```shell
# terminal 1: create a one way virtual serial port, and then replay the sample capture through it at a given rate (2500 bytes per second ~= 20 Kbps)

pv -L 2500 Tests/data/NRT.BIN | socat - PTY,link=/tmp/ttyV0,raw,echo=0

# terminal 2: set SERIALPORT in Receiver/LiveTelemetry.py to the FIRST /tmp/ttyV0 name, then
python3 -m Receiver.LiveTelemetry

```

Stop the receiver with Ctrl-C when the output stops. Remember to set `SERIALPORT` back afterwards.

## Adding a storage option

Subclass `StorerExtension` in [storer_extension.py](storer_extension.py), implementing `store_data` and `close`. Then enable it in `StorerWrapper.init_storer` in [telemetry_storer.py](telemetry_storer.py), behind a setting in [receiver_config.py](receiver_config.py), following how `CSVStorer` is wired up.
