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

How a DBC entry maps to the output:

* The message name (`BO_ <id> <name>`) becomes the **Item**, e.g. `PackParameters`.
* The message's sender (the last word of the `BO_` line) becomes the **Source**, e.g. `Orion`.
* Each signal (`SG_`) becomes one field, using the DBC's scaling, offset and byte order.
* A signal with the unit `"ascii"` is decoded as a single character instead of a number. This is used for the GPS hemisphere characters `GpsLat` (N/S) and `GpsLon` (E/W).

GPS latitude and longitude are stored **as sent by the GPS**, in NMEA `ddmm.mmmm` format, with the sign in the separate hemisphere character. They are not converted to decimal degrees by the receiver ([live_calculations/road_lookup.py](live_calculations/road_lookup.py) does this conversion).

The tests decode with the same `dbc/` files, so `pytest` catches a DBC change that breaks the expected output.

### Adding a new CAN message

1. Add the message to the right `.dbc` file (or add a new file and list it in `dbc_files` in [receiver_config.py](receiver_config.py)). Use a DBC editor or edit the text directly, and set the sender to the device name you want as the Source.
2. Check that the file still loads: `python3 -c "import cantools; cantools.database.load_file('dbc/<file>.dbc')"`.
3. Replay a capture that contains the message (see [Testing without hardware](#testing-without-hardware)) and check the decoded values.
4. If the board should forward the message, check [../Telemetry/UseMsgList.hpp](../Telemetry/UseMsgList.hpp). By default it forwards every message (`PROCESS_ALL_MSG`).

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

Note that `hex2csv` (below) writes a **different** CSV layout.

## Offline tools (SD card logs)

The board writes every frame to its SD card as `YYMMDDNN.BIN`, in the same frame format as the radio link (see [../Telemetry/README.md](../Telemetry/README.md#sd-card)). These tools decode those files after a session. Run them from the top of the repository:

```shell
# decode to CSV: time,item,source,name1,value1,...,name8,value8,crc_ok,millis
python3 -m Receiver.hex2csv -i 23071805.BIN -o 230718.csv -m a     # -m a = append (default), w = overwrite

# import into InfluxDB, in batches of 5000 points (much faster than the live receiver)
python3 -m Receiver.hex2influx -i 23071805.BIN
```

`hex2influx` has its **own** InfluxDB credentials at the top of [hex2influx.py](hex2influx.py) (database `Test22DB`), not the ones in `receiver_config.py`. Edit them before use. Unlike the live receiver, it skips frames with unrecognised CAN IDs.

[batch_Read_Hex.py](batch_Read_Hex.py) runs `hex2influx` on every file in a folder whose name matches a regular expression. Edit `bin_folder` and `regex_pattern` at the top of the script first, then run `python3 -m Receiver.batch_Read_Hex` from the top of the repository.

## Testing without hardware

**Unit tests.** From the top of the repository:

```shell
pip install -r Tests/requirements-test.txt
pytest
```

The tests replay the sample captures in [../Tests/data/](../Tests/data/) (`NRT.BIN`, `MPPT.BIN`) and compare the decoded output with the matching `.csv` files. They do not need InfluxDB.

**Live replay.** You can replay a capture through a virtual serial port pair. Note that this **writes to the live `DUSCiESC` database** unless you turn InfluxDB off in `receiver_config.py`.

```shell
# terminal 1: create a linked pair of virtual serial ports; note the two /dev/pts/N names it prints
socat -d -d pty,raw,echo=0 pty,raw,echo=0

# terminal 2: set SERIALPORT in Receiver/LiveTelemetry.py to the FIRST /dev/pts/N name, then
python3 -m Receiver.LiveTelemetry

# terminal 3: feed the sample capture into the SECOND port
cat Tests/data/NRT.BIN > /dev/pts/M
```

Stop the receiver with Ctrl-C when the output stops. Remember to set `SERIALPORT` back afterwards.

## Adding a storage option

Subclass `StorerExtension` in [storer_extension.py](storer_extension.py), implementing `store_data` and `close`. Then enable it in `StorerWrapper.init_storer` in [telemetry_storer.py](telemetry_storer.py), behind a setting in [receiver_config.py](receiver_config.py), following how `CSVStorer` is wired up.
