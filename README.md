# Telemetry Operation Guide

[ N.B. tested with Peri - Nov. 2026, TPB, BG, BJ]

### Setup (one time only)

```shell
git clone --recurse-submodules git@github.com:DUEM/Telemetry2021.git
cd Telemetry2021
git checkout PERI-DEVELOPMENT-TPB-1126
git submodule update --init

python3 -m venv ~/virtualenvs/telemetry
source ~/virtualenvs/telemetry/bin/activate
pip install -r Receiver/requirements.txt
```

The live calculations (`Receiver/live_calculations/`) and the solarsim upload
client (`Client/`) have their own requirements files, install those only if
you need them:

```shell
pip install -r Receiver/live_calculations/requirements.txt
pip install -r Client/requirements.txt
```

## How to get started with the vehicle

(If needed) Check Arduino is reading CAN msg - serial connection to it (via onboard USB) with the car running.

Check Telemetry Laptop (master) is receiving packets from the xBee:

* Check xBee is plugged into the right port:
    ```shell
    $ ls -la /dev/ttyUSB*
    ```
    and check that `/dev/ttyUSB0` is listed.

Then, from the top level `Telemetry2021` directory, run the main telemetry
script as:

```shell
source ~/virtualenvs/telemetry/bin/activate
python3 -m Receiver.LiveTelemetry
```

Check that the script is writing data to influx
* Check if influx is good:
    ```shell
    $ systemctl status influxd.service
    $ curl -sl -I http://localhost:8086/ping
    ```
* Check that the influx connection info (`InfluxCredentials`) in
  `Receiver/receiver_config.py` is correct:
    ```shell
    $ nano Receiver/receiver_config.py
    ```
    (exit using ctrl+x)

## Maintenance

Set up new database in influx:
```shell
$ influx
> CREATE DATABASE "DatabaseName"
> exit
```

Export a measurement from influxdb
```shell
$ influx
> SHOW DATABASES
> use database_name
> SHOW MEASUREMENTS
> SELECT * FROM measurement_name
> SELECT * FROM measurement_name > /path/to/export.csv
```

Run the tests (from the top level `Telemetry2021` directory):
```shell
pip install -r Tests/requirements-test.txt
pytest
```

## Updating the Telemetry Board
1. Get the latest code from GitHub. Navigate to Telemetry2021 and run the
    following commands. You'll need internet access for this.
    ```shell
    git switch PERI-DEVELOPMENT-TPB-1126
    git pull
    git submodule update --init
    git status
    ```
    and the console should show
    ```
    On branch PERI-DEVELOPMENT-TPB-1126
    Your branch is up to date with 'origin/PERI-DEVELOPMENT-TPB-1126'
    ```
2. In the Arduino IDE, open sketch -> Telemetry2021/Telemetry/Telemetry.ino
   Connect the Arduino to a computer
   Upload Sketch
   Done

## Repository layout

| Path | Contents |
| --- | --- |
| `Telemetry/` | Arduino firmware for the telemetry board (`Telemetry.ino`); `config.txt` goes on its SD card |
| `Telemetry/src/CANApi` | [CANApi](https://github.com/DUEM/CANApi) git submodule, shared CAN message definitions |
| `Receiver/` | Python receiver run on the telemetry laptop |
| `dbc/` | CAN database (`.dbc`) files used to decode messages, by both the receiver and the tests |
| `Client/` | Standalone script to upload solarsim output to influx |
| `Tests/` | pytest suite; `Tests/data/` holds sample captures (`.BIN`) and their expected decoded output (`.csv`) |

## Files in Receiver/

#### LiveTelemetry.py
Entry point for the whole process. Reads frames from the xBee serial port and
passes them to `telemetry_storer.py`.
#### receiver_config.py
Configuration: influx credentials, optional Excel / CSV output files, and the
list of DBC files used for decoding. Edit this file to configure the receiver.
#### telemetry_storer.py
Uses `telemetry_parser3.py` to decode the CAN messages and stores them using
the storage plugins in `storer_extension.py` (influx, Excel, CSV).
#### telemetry_parser3.py / can_dbc_decoder.py / frame_reader.py
Splits a capture into frames and decodes each CAN message using the files in
`dbc/`.
#### hex2csv.py / hex2influx.py / batch_Read_Hex.py
Offline tools to convert binary files offloaded from the board's SD card to
CSV or into influx.

### CANTranslator
[That repo](https://github.com/DUEM/CANTranslator)
