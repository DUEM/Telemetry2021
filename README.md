# Telemetry Operation Guide

[ N.B. tested with Peri - Nov. 2026, TPB, BG, BJ]

### Setup (one time only)

```
git clone git@github.com:DUEM/Telemetry2021.git
cd Telemetry2021
git checkout PERI-DEVELOPMENT-TPB-1126
python3 -m venv ~/virtualenv/telemetry

pip install -r Receiver/requirements.txt
```

## How to get started with the vehicle

(If needed) Check Arduino is reading CAN msg - serial connection to it (via onboard USB) with the car running. 

Check Telemery Laptop (master) is receiving packets from the xBee:

* Check xBee is plugged into the right port: 
    ```shell 
    $ cd /dev	
    $ ls -la
    ```
    and check if there is a `ttyUSB0` in the list.

Then run main telemetry script as: 
    
    source ~/virtualenvs/telemetry/bin/activate
    python3 -m Receiver.LiveTelemetry
    

Check that the script is writing data to influx
* Check if influx is good: 
```shell
$ systemctl status influxd.service
$ curl -sl -I http://localhost:8086/ping
```
* Check that the connection info in telemetryStorer.py is correct.
  * cd to the directory and open the file using nano
  ```shell
    $ nano telemtryStorer.py 
    ```
  * exit using ctrl+x

## Maintainence

Set up new database in influx:
``` shell
$ influx
> CREATE DATABASE "DatabaseName"
> exit
```

Export a measurement from influxdb
``` shell
$ influx
> SHOW DATABASES
> use database_name
> SHOW MEASUREMENTS
> SELECT * FROM measurement_name
> SELECT * FROM measurement_name > /path/to/export.csv
```


## Updating the Telemetry Board
1. Get the latest code from GitHub. Navigate to Telemetry2021 and run the 
    following command. You'll need internet access for this. 
    ```shell
   git switch nick-22Library
   git pull origin nick-22Library
   git submodule init
   git submodule update
   git status
    ```
   and the console should show 
    ```
    On branch nick-22Library
    Your branch is up to date with 'origin/nick-22Library'
    ```
2. In the Arduino IDE, open sketch -> Telemetry2021/Telemetry/Telemetry.ino
   Connect the Arduino to a computer
   Upload Sketch
   Done

## Files on the Telemetry Laptop
```
TBC
```
#### LiveTelemetry.py
Entry point for the whole process
#### telemeteryParser2.py
Called by `telemetryStorer.py`. References `CANBusData.xlsm` to decode the CAN 
messages.
#### telemetryStorer.py
Uses `telemetryParser2.py` to decode the can messages and stores it in either
Excel or Influx. Edit this file to configure the influx credentials or the 
output Excel file. 
### CANTranslator
[That repo](https://github.com/DUEM/CANTranslator)
