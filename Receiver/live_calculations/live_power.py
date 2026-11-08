"""Script to calculated the theoretical instantaneous power


"""
import logging
import pandas as pd
from influxdb import InfluxDBClient, DataFrameClient
from config import influxCredentials, VEHICLE_MASS, G, MOTOR_EFF, CRR, CDA, RHO,\
    NPOINTS, TDELTA

logger = logging.getLogger(__name__)

# Measurement names as written by the receiver: "<Source>/<Item>", i.e. the
# sender and message name in the dbc files (see Receiver/README.md).
VELOCITY_MEASUREMENT = "Tritium/Velocity"  # dbc/wavesculptor_22.dbc
ROAD_LOOKUP_MEASUREMENT = "road_lookup"  # written by road_lookup.py
# Both MPPTs have the same fields (VoltageIn, CurrentIn), so each one's fields
# get a suffix to tell them apart once merged.
MPPT_MEASUREMENTS = {"Mppt/Javed": "1", "Mppt/Woof": "2"}  # dbc/MPPT.dbc

REQUIRED_COLUMNS = [
    "VehicleVelocity",
    "Incline",
    "VoltageIn1",
    "CurrentIn1",
    "VoltageIn2",
    "CurrentIn2",
]


def calc_incline_power(df):
    df.loc[:, "InclineDrag"] = VEHICLE_MASS * G * df.Incline
    df.loc[:, "InclinePower"] = df.InclineDrag * df.VehicleVelocity


def calc_accel(df):
    """Calculates the acceleration and take a 5s rolling average.
    Assumes that the index is already resampled to 1s.
    """
    df.loc[:, "Accel"] = (
        df.VehicleVelocity.diff().rolling(pd.Timedelta("5s")).mean()
    )


def calc_rolling_power(df):
    df.loc[:, "RollingPower"] = VEHICLE_MASS * CRR * G * df.VehicleVelocity


def calc_drive_power(df):
    df.loc[:, "DriveThrust"] = VEHICLE_MASS * df.Accel
    df.loc[:, "DrivePower"] = (df.DriveThrust * df.VehicleVelocity) / MOTOR_EFF


def calc_aero_power(df):
    # TODO: update when we have wind data
    df.loc[:, "HeadWind"] = df.VehicleVelocity
    df.loc[:, "AeroDrag"] = 0.5 * RHO * CDA * df.HeadWind**2
    df.loc[:, "AeroPower"] = df.AeroDrag * df.HeadWind


def calc_solar_power(df):
    # CAN conversion factor from MPPT datasheet
    df.loc[:, "SolarPower1"] = (
        df.VoltageIn1 * 0.15049 * df.CurrentIn1 * 8.72 * 1e-3
    )
    df.loc[:, "SolarPower2"] = (
        df.VoltageIn2 * 0.15049 * df.CurrentIn2 * 8.72 * 1e-3
    )
    df.loc[:, "SolarPower"] = (
        df.loc[:, "SolarPower1"] + df.loc[:, "SolarPower2"]
    )


def main(
    if_credentials: influxCredentials = influxCredentials(),
) -> None:
    """Estimate the power terms from the latest data in influxdb.

    Reads the vehicle velocity, the incline (from road_lookup.py) and the input
    voltage and current of both MPPTs, resamples them to 1 s, and writes the
    calculated drive, incline, rolling, aero and solar power back to influxdb
    under the measurement "live_power".

    Args:
        if_credentials: Credentials for influxDB.

    Returns:
        None
    """
    logger.info("Live power script started.")

    # Read from influx
    influx_client = InfluxDBClient(
        host=if_credentials.host,
        port=if_credentials.port,
        username=if_credentials.username,
        password=if_credentials.password,
        database=if_credentials.db,
    )

    influx_df_client = DataFrameClient(
        host=if_credentials.host,
        port=if_credentials.port,
        username=if_credentials.username,
        password=if_credentials.password,
        database=if_credentials.db,
    )
    # TODO: query wind data as well when it is integrated with Influx.
    measurements = [VELOCITY_MEASUREMENT, ROAD_LOOKUP_MEASUREMENT, *MPPT_MEASUREMENTS]
    query_where = (
        'SELECT "VehicleVelocity","Incline","VoltageIn","CurrentIn" '
        "FROM " + ",".join(f'"{m}"' for m in measurements) + " "
        f"WHERE (time > now() - {TDELTA}) ORDER BY time DESC LIMIT {NPOINTS}"
    )

    ifdfq = influx_df_client.query(query_where)
    logger.info("Influx query successful")

    if ifdfq == {}:
        logger.info("No new points to process.")
        return

    missing_measurements = [m for m in measurements if m not in ifdfq]
    if missing_measurements:
        logger.warning("No data in the last %s for: %s", TDELTA, missing_measurements)

    # Each measurement comes back as its own dataframe, holding only the
    # columns it has data for. Give the MPPT columns their suffix (rename
    # returns a copy, so the query result is left unchanged), then merge.
    frames = []
    for measurement, frame in ifdfq.items():
        suffix = MPPT_MEASUREMENTS.get(measurement)
        if suffix is not None:
            frame = frame.rename(
                columns={"VoltageIn": f"VoltageIn{suffix}", "CurrentIn": f"CurrentIn{suffix}"}
            )
        frames.append(frame)
    df = pd.concat(frames, axis=1)

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        logger.error(
            "Cannot calculate power, no data for: %s (is road_lookup.py running, "
            "and are both MPPTs sending?)",
            missing_columns,
        )
        return

    df = (
        df.resample("1s")
        .mean(numeric_only=True)
        .dropna(how="all", axis=1)
        .interpolate()
    )
    logger.info("preprocessing completed. df size %s", df.shape)
    # Calculate
    calc_accel(df)
    calc_drive_power(df)
    calc_incline_power(df)
    calc_rolling_power(df)
    calc_aero_power(df)
    calc_solar_power(df)

    logger.info("Calculations complete.")
    # Write to influx
    # write mapped distance
    influx_df_client.write_points(
        df,
        "live_power",
        {"live_power": True, "power": True},
        protocol="line",
        batch_size=10000,
    )

    # # It takes a long time to overwrite all these data so we are just gonna
    # #  process the latest n datapoint as an alternative.
    # # add tag to processed data
    # for measurement, measurement_df in ifdfq.items():
    #     influx_df_client.write_points(
    #         measurement_df,
    #         measurement,
    #         tags={"live_power": True},
    #         protocol="line",
    #         batch_size=5000,
    #     )
    #     influx_client.delete_series(
    #         measurement=measurement, tags={"live_power": ""}
    #     )

    logger.info("All data written to influx.")

    influx_df_client.close()
    influx_client.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,  # Set the root logger's level
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[logging.StreamHandler()],  # Add a handler for the root logger
    )

    main()
