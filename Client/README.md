# Client (SolarSim upload)

[upload_solarsim.py](upload_solarsim.py) uploads a SolarSim race strategy (a SolarSim `History.dat` file) to InfluxDB, so the planned values can be shown on the Grafana dashboard next to the live telemetry.

It is a standalone script, independent of the receiver. It can be run from any computer that can reach the InfluxDB server (on the same LAN).

## Dependencies

These are separate from the receiver's. From the top of the repository:

```shell
pip install -r Client/requirements.txt     # S5 (pinned commit), pandas, influxdb
```

## Running

1. Edit the settings at the top of the script:
   * `InfluxCredentials`: host, port, user, password and database. **The default database is `test`**, not `DUSCiESC` (the database the receiver writes to).
2. Edit the settings under `if __name__ == "__main__":` at the bottom of the script:
   * `path_to_SSHistory`: path to the SolarSim `History.dat` file
   * `start_date`: the date of Day 1 of the history file, e.g. `20231022`
   * `tz`: the time zone the history file's times are in, e.g. `Australia/Darwin` or `UTC`
3. Run it:
   ```shell
   python3 Client/upload_solarsim.py
   ```

The script first **deletes all existing data** in the `SolarSim` measurement, then writes the new history to it. Each column of the history file becomes a field.
