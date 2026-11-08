# Telemetry Operation Guide

_[ A simplier tele receiver code use for ESC 2024 + ESC 2026 with known limitations; on vehicle code unchanged from earlier BWSC2023 - EG, JCJ, TPB]_

Check xBee is plugged into the right port: 
```shell 
cd /dev	
ls -la
```
and check 
if there is a `ttyUSB0` in the list.

Run the following script from the terminal:
```shell
cd Telemetery2021
./RunTelemetry.sh
```

Check that the script is writing data to influx:
```shell
systemctl status influxd.service
curl -sl -I http://localhost:8086/ping
```

## Maintainence

Set up new database in influx:
``` shell
influx
> CREATE DATABASE "DatabaseName"
> exit
```

Export a measurement from influxdb
``` shell
influx
> SHOW DATABASES
> use database_name
> SHOW MEASUREMENTS
> SELECT * FROM measurement_name
> SELECT * FROM measurement_name > /path/to/export.csv
```

## Updating code from GitHub to Laptop
1. Get the latest code from GitHub. Navigate to Telemetry2021 and run the following command. You'll need internet access for this. 
    ```shell
   git clone  git@github.com:DUEM/Telemetry2021.git
   cd Telemetry2021
   git switch ESC-CODE
   git pull origin ESC-CODE
   git status
    ```
   and the console should show 
    ```
    On branch ESC-CODE
    Your branch is up to date with 'origin/ESC-CODE'
    ``` 

3. Switch over to the telemetry LAN. 

4. Start browser and point to ``localhost:3000``
to see Grafana.

## Updating the Telemetry Board
1. Get the latest code from GitHub. Navigate to Telemetry2021 and run the 
    following command. You'll need internet access for this. 
    ```shell
   git switch ESC-CODE
   git pull origin ESC-CODE
   git submodule init
   git submodule update
   git status
    ```
   and the console should show 
    ```
    On branch ESC-CODE
    Your branch is up to date with 'origin/ESC-CODE'
    ```
2. In the Arduino IDE, open sketch -> Telemetry2021/Telemetry/Telemetry.ino
   Connect the Arduino to a computer
   Upload Sketch
   Done

## Files in this Repo
```
├── README.md
├── Receiver                      (python receiver software)
│   ├── BIN                       (test output)
│   │   └── Test1.BIN
│   ├── CAN-decode-sheet.csv       (CAN specification ID/packet/format)
│   ├── CSV                        (test output)
│   │   └── Test1.csv
│   └── Live-Telem-05-09-2024-WIP.py 
├── RunTelemetry.sh                (run telemetry reciever)
└── Telemetry (on vehicle ardiuno software - unchanged from [this branch](https://github.com/DUEM/Telemetry2021/tree/nick-22Library))
    ├── config.txt
    ├── SD.cpp
    ├── SD.hpp
    ├── SendMessage.cpp
    ├── SendMessage.hpp
    ├── SensorInputs.cpp
    ├── SensorInputs.hpp
    ├── SerialDebugMacros.hpp
    ├── src
    │   └── CANApi
    ├── StatusMsg.cpp
    ├── StatusMsg.hpp
    ├── Telemetry.ino
    └── UseMsgList.hpp

```

## Known Limitations

* GPS transmission is independant for latitude and longitude leading to positional mismatches
* decoding of GPS latitude and longitude is potentially erroneous 
* telemetry readings/value entries into the influxDB are not time/position stamped
* CRC checks on incoming packets are not carried out leading to erroneous telemetry readings being sent to influxDB
* CANbus decoding uses exhaustive search over a ``CVS`` format config file which has some missing CANBus IDs against vehicle hardware as of 2026.