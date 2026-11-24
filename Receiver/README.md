# Receiver (telemetry laptop)

[LiveTelemetry.py](LiveTelemetry.py) reads radio frames from the XBee serial port, checks each frame's CRC and decodes it using the CAN database files in [../dbc/](../dbc/). Each decoded message is passed to the storage plugins enabled in [config.yml](config.yml):

* InfluxDB 1.x, database `DUSCiESC` on `localhost:8086`, for the Grafana dashboard to display (on by default)
* an Excel workbook (off by default)
* a CSV file (on by default)
* a raw `.BIN` file of every frame as received, in the same format as the SD card log (on by default)

Every decoded message is also printed to the terminal.

## Dependencies

Python 3.10 or later, and, from the top of the repository:

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

It first asks for these settings for this session, showing each default from [config.yml](config.yml) in square brackets. Press Enter to use the default, or type a new value; true/false questions also accept yes/no. The answers apply to this run only: `config.yml` is not changed.

Before the `Serial port` question it lists the USB serial ports, with what each one is (the XBee is always a USB device; any other serial ports are summarised on one line). If the default port is not plugged in, it also suggests the port most likely to be the XBee: the last used port if it is plugged in (type `l`), otherwise an FTDI device ("probably the XBee"), otherwise any USB serial device (type its name):

```
Serial ports found:
  /dev/ttyUSB1  (FT231X USB UART, FTDI)
  (and 32 other serial ports, not USB so not the XBee: /dev/ttyS0 to /dev/ttyS31)
Suggested: /dev/ttyUSB1 (FTDI USB serial, probably the XBee): type it to use it
Serial port [ default: /dev/ttyUSB0 ]:
```

The port listing and suggestion come from Ben Jennery's `PERI-DEVELOPMENT-BBJ-1126` branch ([serial_port.py](serial_port.py)).

```
Serial port [ default: /dev/ttyUSB0 ]:
Telemetry Session Name (no spaces) [ default: telem-received ]:
Excel logging (true/false) [ default: false ]:
BIN logging (true/false) [ default: true ]:
CSV logging (true/false) [ default: true ]:
InfluxDB logging (true/false) [ default: true ]:
InfluxDB database name [ default: DUSCiESC ]:
InfluxDB username [ default: admin ]:
InfluxDB password [ default: password ]:
```

The InfluxDB database name, username and password are only asked for if you answer `true` to `InfluxDB logging`. The receiver then checks that the database exists:

* If it does, it says `InfluxDB database '...' found` and carries on.
* If it does not, it asks whether to **create** it or use the **default** (the database in `config.yml`, `DUSCiESC`); pressing Enter uses the default, which guards against a mistyped name. If you choose create, it says it is creating the database, and reminds you that Grafana reads from the database set in its InfluxDB data source: to see this session in Grafana, change that data source's **Database** to the new name (**Connections → Data sources → InfluxDB**), or add a second data source for it. It then waits until you press Return on its own to continue, or `q` (or `Q`) then Return to quit without starting the receiver (the new database is kept); any other answer asks again.
* If the default database itself does not exist (e.g. on a new laptop), it asks whether to create it.
* If InfluxDB cannot be reached (not running, or wrong username or password with authentication on), it says so and waits until you press Return on its own to start anyway (nothing is stored in InfluxDB until it can be reached and the database exists), or `q` (or `Q`) then Return to quit; any other answer asks again. The session name starts each output file's name (`<session name>-YEAR-MONTH-DAY-HHMMSS.csv`), so it cannot contain spaces (use `-` or `_`) or `/ \ : * ? " < > |`. The other settings in the table below are always taken from `config.yml`. If there is no keyboard input (for example, the receiver is started as a service), the defaults are used.

**Last used settings.** Once the serial port has opened, the answers are saved in a file called `.env` in the directory the receiver was started from (normally the top of the repository). The next time it is started from that directory, each question also shows the value used last time:

```
Serial port [ default: /dev/ttyUSB0, last used: /dev/ttyUSB1 ]:
```

Type `l` to use the last used value, or `d` (or press Enter) for the default from `config.yml`; you can still type a new value instead. (So while a last used value is shown, `d` and `l` cannot be used as a serial port or session name.) If InfluxDB is off, the InfluxDB database name, username and password from the time before are kept in `.env`. A setting that is missing from `.env`, or not a valid answer (e.g. after editing the file by hand), is shown without a last used value. The settings are not saved if you quit at one of the questions, or before a serial port opens (so a mistyped port is not saved). `.env` holds the InfluxDB password in plain text, so it is git-ignored: do not commit or share it. Delete it to go back to the defaults only.

Press **Ctrl-C** to stop it. The output files and the InfluxDB connection are closed cleanly. Ctrl-C at one of the questions quits without starting the receiver.

If the serial port cannot be opened, the receiver prints `Cannot open serial port ...` with the reason and what to check, lists the ports again and asks for the port again (Enter tries the default again, e.g. after plugging the XBee in); no output is created until a port opens. For example, the XBee is not plugged in or the port is the wrong one (`... does not exist`), another program has it open, or you do not have permission to use it (on Linux, add yourself to the `dialout` group). Ctrl-C at the question quits. If there is no keyboard input to ask with (e.g. started as a service), it exits instead.

Once the port is open it prints `Opened <port> at <baud> baud`. If `serialBaud` in `config.yml` is not 115200, it also warns that it must match the XBee's baud rate: a wrong rate gives no error, only `CRC FAIL` frames. A port that opens is not proof the XBee is working: if nothing is printed, or every frame is `CRC FAIL`, check it with [tools/check_xbee_settings.py](../tools/check_xbee_settings.py).

## Configuration

All the receiver's settings are in [config.yml](config.yml), in this folder; [receiver_config.py](receiver_config.py) reads it when the receiver starts. For the settings asked for when the receiver starts (see [Running](#running)), the values in `config.yml` are the defaults. Relative folders are relative to the top of the repository, except the three output folders, which are always inside `sessionLogsFolder` (`session-logs`). Every setting must be present: if one is missing, misspelt or the wrong type (for example `"false"` in quotes instead of `false`), the receiver stops with an error naming the file and the setting. The file has a comment explaining each one.

| Setting | Name in `config.yml` | Default |
|---|---|---|
| Serial port | `serialPort` | `/dev/ttyUSB0` |
| Baud rate | `serialBaud` | **115200** (must match the XBee) |
| InfluxDB host, port, user, password, database | `host`, `port`, `username`, `password`, `db` under `ifCredentials` | `localhost`, `8086`, `admin`, `password`, `DUSCiESC` |
| InfluxDB on / off | `enabled` under `ifCredentials` | `true` (on) |
| Excel on / off | `xlsxEnabled` | `false` (off) |
| Excel folder, inside `sessionLogsFolder` | `xlsxOutputFolder` | `excel` |
| Excel save interval | `xlsxSaveInterval` | **10** seconds |
| CSV on / off | `csvEnabled` | `true` (on) |
| CSV folder, inside `sessionLogsFolder` | `csvOutputFolder` | `csv` |
| BIN (raw) on / off | `binEnabled` | `true` (on) |
| BIN folder, inside `sessionLogsFolder` | `binOutputFolder` | `BIN` |
| Output file name | `sessionLogName` | `telem-received` (files are `telem-received-YEAR-MONTH-DAY-HHMMSS.xlsx` / `.csv` / `.BIN`) |
| CAN database files | `dbc_files`, in folder `dbc_folder` | the four files in [../dbc/](../dbc/) |

Each output is switched on or off with its own `true`/`false` setting. Output files go in the `session-logs/` folder at the top of the repository, whichever directory the receiver is started from: Excel in `session-logs/excel/`, CSV in `session-logs/csv/`, BIN in `session-logs/BIN/`. The folders are created when first needed. Each run of the receiver writes **new** files, named after the local date and time the **first frame arrived**, e.g. `session-logs/csv/telem-received-2026-11-15-143012.csv`; the files from one run have the same name. The files (and the InfluxDB connection) are only set up when the first frame arrives: if none arrives, empty files are created when the receiver stops. If the serial port cannot be opened, no files are created. `session-logs/` is git-ignored, so session logs are not committed by accident.

**Temporary solution:** the separate reading thread and the InfluxDB batching described here were added to test whether the receiver's lack of buffering is why most radio data was lost. They work, but have made the code more complicated; once the cause is confirmed on the car they should be rewritten more simply. As part of the same test, every 5 s the receiver logs the radio bandwidth, e.g. `Radio, last 5.0 s: 1,240 B/s (11% of 115200 baud), 68 frames/s, 2 CRC fails, 0 waiting to be stored`. The percentage is of the serial link between the XBee and the laptop; the XBee's over-the-air rate may be lower. With nothing being lost, expect roughly 1,000 to 1,300 B/s while the car is on.

The serial port is read on its own, and the frames are stored by a separate thread ([LiveTelemetry.py](LiveTelemetry.py)), so a slow output (an InfluxDB write over the network, the Excel file being saved) never stops the radio data being read. Frames wait in a queue until they are stored; if more than 2000 are waiting, the receiver logs a warning that the outputs are slower than the radio. When it stops, every frame already received is stored before the outputs are closed. InfluxDB points are written in batches, every 0.5 s or 500 points, whichever comes first, so Grafana shows data up to about 0.5 s later. A write that fails or takes longer than 5 s is logged and that batch is dropped (the BIN, CSV and Excel outputs still have it, and `tools/hex2influx.py` can load it afterwards).

## Radio frame format

Each frame from the vehicle is:

```
[millis 4B, little-endian][CAN ID 2B, big-endian][DLC 1B][data, DLC bytes][CRC16 2B, big-endian][0x7E]
```

* `millis` is the board's uptime in ms when the frame was sent. It is used for the timestamp (see [Timestamps](#timestamps)).
* The CRC is CRC-16/MODBUS (reflected polynomial `0xA001`, initial value `0xFFFF`), the same as AVR `_crc16_update` on the board. It is calculated over the millis, CAN ID, DLC and data bytes. The receiver **does** check it: frames that fail are dropped from InfluxDB and flagged `False` in the Excel/CSV output.
* Only the `DLC` data bytes are decoded. A frame with more or fewer data bytes than its DLC is rejected even if its CRC passes: frames run together after a lost end of frame marker can pass the 16-bit CRC by chance. A frame with fewer data bytes than its message's length in the DBC file is not decoded either (see below).
* `0x7E` marks the end of a frame and is **not** escaped inside the frame (see Known limitations in the top-level [README](../README.md#known-limitations)), so a `0x7E` in the millis, data or CRC splits the frame. Splitting a capture into frames is done in [frame_reader.py](frame_reader.py). It re-joins split frames: a piece that is not a complete frame (length matching its DLC, valid CRC) is joined back, with the `0x7E`, to the pieces after it until the result is complete. A piece that is a complete frame on its own is never joined. Bytes lost on the radio, sometimes including a `0x7E`, can leave what is left of one frame run into the next (often just the 4 `millis` bytes of a frame, followed by a whole frame). So before giving up on a piece, complete frames at its start and end are split off it and passed on separately; the bytes left are passed on unchanged, so they are still reported as a CRC failure. On the iESC 2026 SD card logs re-joining recovers about 2.4% of frames, which were previously lost (the SD card logs have no radio losses, so nothing is split there). On radio captures, splitting recovers about 6 to 8% more frames (`Tests/data/NRT.BIN`: 284). The live receiver `LiveTelemetry.py` and the offline tools (`hex2csv`, `hex2influx`, `batch_Read_Hex`) both use it, so they store the same frames from the same bytes. Live, a split frame is stored as soon as its last piece arrives.

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

Follow the steps in [dbc/README.md](../dbc/README.md#changing-or-adding-a-message-or-signal): edit the `.dbc` file (including a plain-English comment), regenerate `dbc/SIGNALS.md`, and run `pytest`. If you add a new `.dbc` file, also list it in `dbc_files` in [config.yml](config.yml). Then replay a capture that contains the message (see [Testing without hardware](#testing-without-hardware-software-in-the-loop-sil)) and check the decoded values.

Renaming a message, sender or signal, or changing its scaling, changes what is stored in InfluxDB; see the warning in [dbc/README.md](../dbc/README.md#changing-or-adding-a-message-or-signal).

Frames with a CAN ID that is not in any DBC file are logged as a warning and stored as Item `ID UNRECOGNISED`, Source `ERROR`, with the CAN ID as the only field. Frames of the wrong length are stored the same way, as Item `DLC MISMATCH` (a different number of data bytes from the frame's DLC) or `DECODE ERROR` (fewer data bytes than the message's length in the DBC file).

Messages with no data (the MPPT poll requests) have no fields, so they are not written to InfluxDB.

## InfluxDB schema

You need to know this schema when building Grafana panels:

| Measurement | Fields | Example |
|---|---|---|
| `<Source>/<Item>` | One field per DBC signal, named as in the DBC | `Orion/PackParameters`: `PackCurrent`, `PackInstVoltage`, `PackSoc`, `RelayState` |
| `ERROR/ID UNRECOGNISED` | `ID` (the unknown CAN ID) | |
| `ERROR/DLC MISMATCH` | `ID`, `DLC`, `Bytes` (data bytes actually received) | |
| `ERROR/DECODE ERROR` | `ID`, `DLC` | |

Measurement names contain `/` (and sometimes spaces), so they must be double-quoted in InfluxQL:

```shell
influx -database DUSCiESC -execute 'SELECT * FROM "Orion/PackParameters" LIMIT 10'
```

The [live calculations](live_calculations/README.md) write their results back to InfluxDB under their own measurements.

### Timestamps

Points are stamped with the **vehicle's GPS time**, not the laptop's receive time:

* Each `TimeAndFix` message (CAN ID 0xF6) with a valid date sets the reference time to the GPS time, along with the board's `millis` value when it was sent.
* Every frame is stamped with that GPS time plus the difference between its `millis` and the reference `millis`. The `TimeAndFix` frame itself is stamped with its own GPS time.
* Until the first valid GPS time arrives, the first frame received sets the reference: the laptop's clock when it arrived, at that frame's `millis`. Timestamps from before the first GPS fix are therefore only as accurate as the laptop's clock (plus the radio delay), however long the board has been running. When reading an SD card log or a replay with the offline tools, the laptop's clock is the time of the conversion, so frames before the first GPS time in the file are stamped with that.

## Output files

* **Excel** (`xlsxEnabled`, in `session-logs/excel/`): sheet `Translated Messages`, one row per message: `Date`, `Time`, `Source`, `Item`, then pairs of field name and value, with the CRC result in column U. (If a file of the same name already exists, which only happens if the receiver is restarted within the same second, it is appended to after a three-row gap.) Saving rewrites the whole workbook, so it is saved at most every `xlsxSaveInterval` seconds (and straight away for the first row), plus once more when the receiver stops. Stop the receiver with Ctrl-C so the last rows are saved.
* **CSV** (`csvEnabled`, in `session-logs/csv/`): one row per message: `Timestamp` (ISO 8601), `Source`, `Item`, `Message Body` (`name=value` pairs in one quoted column), `CRC`.
* **BIN** (`binEnabled`, in `session-logs/BIN/`): the raw radio data, exactly the bytes received, `0x7E` markers included, with frames that fail their CRC or have an unknown CAN ID kept too (bytes split off the front of a damaged piece are written without a marker, as they had none). This is the same format as the SD card log and the ESC-CODE receiver's `BIN/` files, so it can be decoded later with [hex2csv.py or hex2influx.py](#offline-tools-sd-card-logs), or replayed through a virtual serial port (see [Testing without hardware](#testing-without-hardware-software-in-the-loop-sil)). Each frame is written as soon as its end of frame marker arrives (a frame split by an unescaped `0x7E` once all its pieces have arrived); bytes after the last marker when the receiver stops are an unfinished frame and are not written.

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

[hex2influx.py](../tools/hex2influx.py) uses the receiver's InfluxDB settings in [config.yml](config.yml) (database `DUSCiESC`). To import into a different database, e.g. to keep an old session apart from live data, add `-d <database>`. Unlike the live receiver, it skips frames with unrecognised CAN IDs.

[batch_Read_Hex.py](../tools/batch_Read_Hex.py) runs `hex2influx.py` on each file in the directory given with `-d`, in name order. By default it picks the board's log files, named `YYMMDDNN.BIN` (in upper or lower case). To choose other files, give a regular expression that the whole file name must match with `-p`; for example, `-p "231018[0-9]{2}\.BIN"` picks only the files from 18 October 2023. At the end it reports how many files were imported, and lists any that failed.

## Testing without hardware (software in the loop, SIL)

**Unit tests.** From the top of the repository:

```shell
pip install -r Tests/requirements-test.txt
pytest
```

The tests replay the sample captures in [../Tests/data/](../Tests/data/) and compare the decoded output with the matching `.csv` files. They do not need InfluxDB.

* `NRT.BIN`: Ortus-T at iESC 2026 (qualifying, 18 September 2026): two sections of the recording, joined. The first (GPS with a position fix) is about 1 minute long; the second (out on track, with the motor controller, driver controls and current dial) is about 8 minutes long, with radio reception getting worse towards the end. Recorded with the ESC-CODE receiver, whose own decoded output was used to check this branch's decoding.
* `MPPT.BIN`: an earlier (July 2023) recording with MPPT status messages, which are not in the iESC 2026 recording.

**Live replay.** You can replay a capture through a virtual serial port. Note that this **writes to the live `DUSCiESC` database** unless you answer `false` to `InfluxDB logging` when the receiver starts. To check the replay in a file instead, answer `true` to `Excel logging`, `BIN logging` or `CSV logging` (the BIN log of a replay should match the capture, up to its last `0x7E`).

```shell
# terminal 1: create a one way virtual serial port, and then replay the sample capture through it at about the rate it was received over the radio (250 bytes per second)

pv -L 250 Tests/data/NRT.BIN | socat - PTY,link=/tmp/ttyV0,raw,echo=0,wait-slave

# terminal 2: start the receiver and enter /tmp/ttyV0 at the Serial port prompt

python3 -m Receiver.LiveTelemetry

```

Stop the receiver with Ctrl-C when the output stops.

Start terminal 1 first, as it creates `/tmp/ttyV0`. With `wait-slave`, `socat` sends nothing until the receiver opens the port, so the start of the capture is not lost while you start terminal 2.

The `-L` rate is in bytes per second. The board has no fixed rate: it sends each CAN message as it arrives, so choose the rate for what you want to imitate:

| `pv -L` | Imitates |
|---|---|
| `250` | A radio capture such as `NRT.BIN` at roughly the rate it was received (about 220–450 bytes/s reached the receiver at iESC 2026) |
| `1800` | An SD card log at the rate the board writes it while driving (about 100 frames/s of about 17 bytes) |
| `11520` | The limit of the board's 115200 baud XBee serial link (10 bits per byte), as a stress test |

The replay rate does not change the stored data: timestamps come from the GPS time and the board's `millis` in each frame, not from when the bytes arrive.

## Adding a storage option

Subclass `StorerExtension` in [storer_extension.py](storer_extension.py), implementing `store_data` (called with each decoded message) and `close`. To keep the raw frames as well, also override `store_raw`, which is called with each frame exactly as received, before decoding (see `BinStorer`). Then enable it in `StorerWrapper.init_storer` in [telemetry_storer.py](telemetry_storer.py), behind a setting in [config.yml](config.yml) (also add it to `_SETTINGS` and the module values in [receiver_config.py](receiver_config.py)), following how `CSVStorer` is wired up.
