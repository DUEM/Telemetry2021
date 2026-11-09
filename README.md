# DUSC Telemetry @ ESC 2024 + ESC 2026

_A simpler telemetry receiver used for ESC 2024 and ESC 2026, with known limitations (see below). The on-vehicle code is unchanged from BWSC2023._

## System overview

![Telemetry Archiecture](./assets/telemetry-architecture.png)

```
 Vehicle CAN bus (125 kbps)
   │  BMS (Orion), motor controllers (Tritium), MPPTs, driver controls ...
   ▼
 Arduino Mega 2560 telemetry board  ──►  SD card (raw .bin log of every frame)
   │  MCP2515 CAN controller, Adafruit GPS
   │  XBee radio on Serial2 @ 115200 baud
   ▼
 XBee (USB) on the telemetry laptop  →  /dev/ttyUSB0
   ▼
 Receiver/Live-Telem-05-09-2024-WIP.py  ──►  Receiver/BIN/*.BIN (raw)  +  Receiver/CSV/*.csv (decoded)
   ▼
 InfluxDB 1.x (database "DUSCiESC")
   ▼
 Grafana  →  http://localhost:3000
```

* [Telemetry/README.md](Telemetry/README.md): on-vehicle firmware (building, flashing, SD card `config.txt`, radio frame format)
* [Receiver/README.md](Receiver/README.md): laptop receiver (dependencies, CAN decode sheet, InfluxDB schema, testing without hardware)

## Branches

| Branch | Contents |
|---|---|
| `ESC-CODE` | **This branch.** The cut-down code actually used at ESC 2024 and ESC 2026. |
| `nick-22Library` | Default branch. The full BWSC2023-era code base, including the original firmware development and older receiver tools. |

## First-time setup (telemetry laptop)

_This assumes InfluxDB 1.x and Grafana are already installed and set up._

```shell
git clone -b ESC-CODE --recurse-submodules git@github.com:DUEM/Telemetry2021.git
cd Telemetry2021
pip install -r Receiver/requirements.txt
sudo usermod -aG dialout $USER     # serial port access; log out and in again afterwards
```

Create the database the receiver writes to (the name is hardwired in the receiver script):

```shell
influx
> CREATE DATABASE "DUSCiESC"
> exit
```

## How to run telemetry (race day)

1. Plug in the XBee and check it shows up as a serial port:
   ```shell
   ls /dev/ttyUSB*
   ```
   You would normally expect `/dev/ttyUSB0`.

2. Make sure InfluxDB is running:
   ```shell
   systemctl status influxd.service
   curl -sl -I http://localhost:8086/ping
   ```

3. Start the receiver from the top of the repository:
   ```shell
   cd Telemetry2021
   ./RunTelemetry.sh
   ```
   The script prompts for:
   * **Port**: e.g. `/dev/ttyUSB0`. Available ports are listed above the prompt.
   * **BIN FILE NAME**: name without extension. Raw bytes are saved to `Receiver/BIN/<name>.BIN`.
   * **CSV FILE NAME**: name without extension. Decoded values are saved to `Receiver/CSV/<name>.csv`.

   Existing files with the same name are **overwritten**, so use a new name for each session (e.g. `2026-09-07-day1`).

4. Check that data is reaching InfluxDB:
   ```shell
   influx -database DUSCiESC -execute 'SHOW MEASUREMENTS'
   ```

5. Open Grafana in a browser at <http://localhost:3000>.

6. Press **Ctrl-C** to stop the receiver. The BIN and CSV files are closed and saved.

## Maintenance

Export a measurement from InfluxDB to CSV:

```shell
influx -database DUSCiESC -execute 'SHOW MEASUREMENTS'
influx -database DUSCiESC -execute 'SELECT * FROM "Pack SOC"' -format csv > /path/to/export.csv
```

Measurement names contain spaces, so they must be double-quoted (see the InfluxDB schema in [Receiver/README.md](Receiver/README.md)).

## Updating the code on the laptop

You need internet access for this.

```shell
cd Telemetry2021
git switch ESC-CODE
git pull origin ESC-CODE
git submodule update --init
git status
```

The output should show:

```
On branch ESC-CODE
Your branch is up to date with 'origin/ESC-CODE'
```

Then switch back to the telemetry LAN.

## Updating the telemetry board

Update the code as above (the `git submodule update --init` step is required, because the firmware depends on the `CANApi` submodule). Then follow the build and upload steps in [Telemetry/README.md](Telemetry/README.md).

## Files in this repository

```
├── README.md
├── RunTelemetry.sh                    (starts the receiver)
├── Receiver                           (Python receiver software, see Receiver/README.md)
│   ├── Live-Telem-05-09-2024-WIP.py   (live receiver: serial → BIN/CSV files + InfluxDB)
│   ├── CAN-decode-sheet.csv           (CAN specification: ID / packet / data types)
│   ├── requirements.txt
│   ├── BIN/                           (raw output; Test1.BIN is a sample capture)
│   └── CSV/                           (decoded output; Test1.csv is a sample)
└── Telemetry                          (on-vehicle Arduino firmware, see Telemetry/README.md;
    │                                    unchanged from the nick-22Library branch)
    ├── Telemetry.ino                  (setup / main loop)
    ├── SendMessage.cpp/.hpp           (radio framing, CRC, SD logging)
    ├── SensorInputs.cpp/.hpp          (GPS)
    ├── SD.cpp/.hpp                    (SD card and config.txt loading)
    ├── StatusMsg.cpp/.hpp             (system status message)
    ├── SerialDebugMacros.hpp
    ├── UseMsgList.hpp                 (which CAN messages the board handles)
    ├── config.txt                     (copy to the SD card root)
    └── src/CANApi                     (git submodule: DUEM/CANApi)
```

## Known limitations

**Radio link and framing**
* Frames are terminated by `0x7E`, but `0x7E` bytes inside the frame are not escaped. If any timestamp, data or CRC byte equals `0x7E`, the frame is split and dropped (or misdecoded). About 10% of the frames in `Receiver/BIN/Test1.BIN` are affected.
* The receiver does not check the CRC on incoming packets, so corrupted frames can reach InfluxDB.

**Decoding**
* CAN decoding is an exhaustive search over the `CAN-decode-sheet.csv` file. Some CAN IDs used by the 2026 vehicle hardware are missing from it.
* Unknown IDs are flagged with a sentinel row index of `99`, which will break once the decode sheet has more than 99 rows.
* A NaN value only skips that one field. The remaining fields of the frame are still written.

**GPS**
* Latitude and longitude are sent as separate CAN messages, which can lead to mismatched positions.
* Decoding of GPS latitude and longitude may be wrong.

**Timestamps**
* Values written to InfluxDB are not stamped with the vehicle's time or position. The board's `millis()` timestamp is decoded but discarded, and every point is stamped with the laptop's receive time (`datetime.utcnow()`).

**Usability**
* InfluxDB details (host, port, user `admin`, password, database `DUSCiESC`) are hardwired in the Python code.
* The serial port and BIN/CSV file names have to be entered every time the receiver is run.

## History

* BWSC 2023: on-vehicle firmware (see branch `nick-22Library`)
* ESC 2024: receiver script written by Ethan Glen (EG)
* ESC 2026: documented and reorganised post-event (Nov 2026) by Toby Breckon (TPB)
