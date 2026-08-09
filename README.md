# Telemetry Operation Guide


Check Arduino is reading CAN msg: 
* Serial connection to it with the car running. 

Check Pi is receiving packets from the xBee: 
* Check xBee is plugged into the right port: 
```shell 
$ cd /dev	
$ ls -la
```
and check 
if there is a `ttyUSB0` in the list.
* Restart `telem.service`: 
```shell
$ systemctl restart telem.service
```
* Check that `telem.service` is running: 
```shell
$ systemctl status telem.service
```
* Check the log and see if there are CAN msgs coming in:
```shell
$ journalctl -u telem.service -f
```


Check that the script is writing data to influx
* Check if influx is good: 
```shell
$ systemctl status influxd.service
$ curl -sl -I http://localhost:8086/ping
```
* Check that the connection info in receiver_config.py is correct.
  * cd to the directory and open the file using nano
  ```shell
    $ nano receiver_config.py 
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

## Updating code from GitHub to Pi
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
     
2. Switch over to the telemetry LAN. Copy the files over onto the pi with the 
    following command. Enter the password when prompted.  
    ```shell
	scp -r * pi@raspberrypi.local:~/telemetry22/Telemetry2021/
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

## Files on the Pi
```
~
|- telemetry22
|  |- Telemetry2021
|  |  |- Receiver
|  |  |  |- LiveTelemetry.py
|  |  |  |- telemetry_parser3.py
|  |  |  |- telemetry_storer.py
|  |  |  |- receiver_config.py
|  |  |  ... 
|  |  |- dbc
|  |  |  |- Orion.dbc
|  |  |  ...
|  ...
|- start-telem.sh 
```
### Telemetry2021
[This repo](https://github.com/DUEM/Telemetry2021)
#### LiveTelemetry.py
Entry point for the whole process
#### telemetry_parser3.py
Called by `telemetry_storer.py`. References the dbc files to decode the CAN 
messages.
#### telemetry_storer.py
Uses `telemetry_parser3.py` to decode the can messages and stores it in either
Excel, CSV or Influx.
#### receiver_config.py
Edit this file to configure the influx credentials, the output Excel or CSV 
file, and the dbc files used for decoding.
#### dbc files
Contains info for all the CAN messages and how to decode them. Generated from 
the [CANTranslator repo](https://github.com/DUEM/CANTranslator).

## Running the tests
Run the tests from the root of the repo. The dbc files and test captures are
found relative to the root, so running from anywhere else will fail.
```shell
$ pip install -r Tests/requirements-test.txt
$ pytest
```
To see which lines are not covered, and the coverage figure the pipeline
enforces:
```shell
$ pytest --cov=Receiver --cov=Client --cov-report=term-missing
```
