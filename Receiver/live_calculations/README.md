# Live calculations

Scripts that each read some of the live data from InfluxDB, calculate further values from it, and write the results back to InfluxDB for the Grafana dashboard. They run separately from the [receiver](../README.md), alongside it.

## Dependencies

These are separate from the receiver's. From the top of the repository:

```shell
pip install -r Receiver/live_calculations/requirements.txt     # S5 (pinned commit), pandas, numpy, influxdb
```

## Configuration

All the scripts read their settings from [config.py](config.py):

| Setting | Used by | Meaning |
|---|---|---|
| `influxCredentials` | all | InfluxDB host, port, user, password and database |
| `ROAD_FILE_PATH` | `road_lookup.py` | SolarSim road file, relative to the directory the script is run from |
| `TDELTA`, `NPOINTS` | `live_power.py` | How far back to query (e.g. `"2h"`) and the maximum number of points |
| `VEHICLE_MASS`, `MOTOR_EFF`, `CRR`, `CDA`, `RHO`, `G` | `live_power.py` | Vehicle and physical constants for the power model |

**`config.py` points at database `Test22DB`**, not `DUSCiESC` (the database the receiver writes to). Change `db` in `influxCredentials` before using these scripts with live data.

## Running

The scripts import `config` directly, so run them from **this** directory (unlike the receiver, which is run from the top of the repository):

```shell
cd Receiver/live_calculations
python3 road_lookup.py
python3 live_power.py
```

To run them from somewhere else, add this directory to the Python path first, e.g. `PYTHONPATH=Receiver/live_calculations python3 Receiver/live_calculations/road_lookup.py`.

## road_lookup.py

Reads the GPS position (`Telemetry/Latitude` and `Telemetry/Longitude`) from InfluxDB and converts it from NMEA `ddmm.mmmm` format to signed decimal degrees. It then uses a SolarSim road file to map each position to the closest distance along the route. The closest road file point is found by Euclidean distance, and a position is only mapped if that point is within 100 m.

The incline is calculated from the altitude in the road file, using the same central difference method as SolarSim.

Only data that has not yet been processed is used. Once data has been processed, the tag `calc_grad` is added to it, and it is not processed again.

The results are written to the measurement `road_lookup`.

**Make sure a road file is available and `ROAD_FILE_PATH` in `config.py` points to it.**

## live_power.py

Estimates the theoretical power consumption. It needs:

* the incline from `road_lookup.py`, measurement `road_lookup` (so run that first)
* the vehicle velocity from the Tritium motor controller, measurement `Tritium/Velocity`
* the input voltage and current of both MPPTs, measurements `Mppt/Javed` and `Mppt/Woof`
* (when integrated) wind measurements from the anemometer

These measurement names are set at the top of [live_power.py](live_power.py). They follow the receiver's `<Source>/<Item>` naming from the DBC files (see the [InfluxDB schema](../README.md#influxdb-schema)), so update them if a message or sender is renamed in a DBC file.

For each field it fetches the latest `NPOINTS` points **and** the points from the last `TDELTA` time period. The fields are then resampled to 1 s for the calculation. Because the source data are not on a common time base, this can produce many more points than were read.

**Tune `NPOINTS` and `TDELTA` to balance the amount of data processed against the speed and memory use of the script.**

The results are written to the measurement `live_power`.

## Known limitations

* `live_power.py` needs all of its inputs. If there is no data in the last `TDELTA` for the incline or for either MPPT (e.g. one MPPT is not sending), it logs which inputs are missing and writes nothing.
* The default `config.py` sets `ROAD_FILE_PATH` twice. The second value (`Road-Top-Gear-Foo-V1.dat`) is the one used, and neither road file is in this repository.
