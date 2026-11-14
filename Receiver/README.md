# Receiver (telemetry laptop)

[Live-Telem-05-09-2024-WIP.py](Live-Telem-05-09-2024-WIP.py) reads radio frames from the XBee serial port and decodes them using [CAN-decode-sheet.csv](CAN-decode-sheet.csv). It then:

* writes the raw bytes to `BIN/<name>.BIN`
* writes the decoded values to `CSV/<name>.csv`
* writes each decoded value to InfluxDB 1.x, database `DUSCiESC` on `localhost:8086`, for Grafana to display

## Dependencies

Python 3 and:

```shell
pip install -r requirements.txt     # pandas, numpy, pyserial, influxdb
```

`influxdb` is the InfluxDB **1.x** client. The receiver will not work against InfluxDB 2.x or 3.x without code changes.

The user also needs read access to the serial port (`sudo usermod -aG dialout $USER`, then log out and in again).

## Running

Run the script from this directory, because it opens `CAN-decode-sheet.csv`, `BIN/` and `CSV/` using relative paths. [../RunTelemetry.sh](../RunTelemetry.sh) does this for you. For the prompts, see the top-level [README](../README.md#how-to-run-telemetry-race-day).

The InfluxDB connection details (host, port, user, password, database) are hardwired near the top of the script under `SET UP INFLUX DB`.

## Radio frame format

Each frame from the vehicle is:

```
[millis 4B, little-endian][CAN ID 2B, big-endian][DLC 1B][data, DLC bytes][CRC16 2B, big-endian][0x7E]
```

* `millis` is the board's uptime in ms when the frame was sent. The receiver decodes it but does not use it.
* The CRC is AVR `_crc16_update` (reflected polynomial `0xA001`, initial value `0xFFFF`), calculated over the millis, CAN ID, DLC and data bytes. The receiver does not check it.
* `0x7E` marks the end of a frame and is **not** escaped inside the frame (see Known limitations in the top-level README).

## CAN decode sheet

[CAN-decode-sheet.csv](CAN-decode-sheet.csv) has one row per CAN message:

| Column | Meaning |
|---|---|
| `Item` | Human-readable message name |
| `Source` | Sending device. `Orion` is decoded **big-endian**; all other sources are decoded little-endian. |
| `Period (s)`, `freq`, `rate (byte/s)` | Informational only, not used by the receiver |
| `CAN_ID` / `CAN_ID (dec)` | CAN ID in hex / decimal. The receiver matches on the **decimal** column. |
| `DLC` | Expected data length. Frames with a different DLC are rejected. |
| `BYTE_0` … `BYTE_7` | Signal name for each byte position. A signal's name goes on its **first** byte. Use `IN USE` for the remaining bytes of a multi-byte value, `-` for unused bytes, and `spare1`/`spare2`/`spare3` for spare bytes, which are skipped. |
| `1` … `8` | Data type of the 1st, 2nd, … signal in order. Use `-` for unused entries. Valid types: `int8`, `uint8`, `int16`, `uint16`, `int32`, `uint32`, `float`, `char`, `spare1`/`spare2`/`spare3` (1 byte). |

Special cases in the code:

* **248 / 249 (GPS latitude / longitude)**: the GPS `ddmm.mmmm` value is converted to decimal degrees. The sign comes from the N/S or E/W `char`, and the result is written to the `location` measurement.
* **1809 / 1810 (MPPT polls)**: logged to CSV but not written to InfluxDB.

### Adding a new CAN message

1. Add a row with the decimal CAN ID, DLC, byte names and data types as described above.
2. Check that the total size of the types in `1`…`8` matches the bytes named in `BYTE_0`…`BYTE_7`.
3. If the source sends big-endian data and is not `Orion`, the endianness check in the script needs updating.
4. Replay a capture (see below) and check the decoded values.

## InfluxDB schema

The receiver uses this schema, which you need to know when building Grafana panels:

| Measurement | Fields | Notes |
|---|---|---|
| `<signal name>` (e.g. `Pack SOC`, `Bus Voltage 20`) | `Float_value`, `Bool_value` (always `true`) | One measurement per signal name from the decode sheet |
| `location` | `latitude`, `longitude`, `Bool_value` | Signed decimal degrees, for the Grafana Geomap panel |

Timestamps are the laptop's UTC time when each frame is received.

## Output files

* `BIN/<name>.BIN`: every byte received from the serial port, in the frame format above. It uses the same format as the `.bin` log on the vehicle's SD card.
* `CSV/<name>.csv`: one line per decoded frame, `timestamp,name1,value1,name2,value2,...`

These directories are git-ignored apart from the sample files `Test1.BIN` and `Test1.csv`, so session logs are not committed by accident.

## Testing without hardware

You can replay a capture through a virtual serial port (needs `sudo apt install socat pv`). Note that this **writes to the live `DUSCiESC` database**.

```shell
# terminal 1: create a one way virtual serial port, and then replay the sample capture through it at about the rate data is received over the radio (250 bytes per second)
pv -L 250 Receiver/BIN/Test1.BIN | socat - PTY,link=/tmp/ttyV0,raw,echo=0,wait-slave

# terminal 2: run the receiver and give it /tmp/ttyV0 as the port (it is not in the list of ports shown, type it anyway)
#             (don't use "Test1" as the output BIN name, or it will overwrite the file being replayed)
cd Receiver
python3 ./Live-Telem-05-09-2024-WIP.py
```

Start terminal 1 first, as it creates `/tmp/ttyV0`. With `wait-slave`, `socat` sends nothing until the receiver opens the port, so no data is lost while you answer the receiver's prompts. Stop the receiver with Ctrl-C when the output stops.

The `-L` rate is in bytes per second. The board has no fixed rate: it sends each CAN message as it arrives, so choose the rate for what you want to imitate:

| `pv -L` | Imitates |
|---|---|
| `250` | A radio capture at roughly the rate it was received (about 220–450 bytes/s reached the receiver at iESC 2026) |
| `1800` | An SD card log at the rate the board writes it while driving (about 100 frames/s of about 17 bytes) |
| `11520` | The limit of the board's 115200 baud XBee serial link (10 bits per byte), as a stress test |

This receiver timestamps each message with the laptop's clock when it arrives, so the replay rate sets the stored timestamps. `Test1.BIN` holds about 1.5 minutes of data, recorded at about 875 bytes/s; at 250 bytes/s it is spread over about 5.5 minutes.
