"""Script to lookup the race distance from GPS lat lon and add to influx

Requires a road file to be located, update the file path to the road file below
before uploading the script.
"""
import logging
import os
from typing import Union
import numpy as np
import pandas as pd
from influxdb import InfluxDBClient, DataFrameClient
import S5.Tecplot as tp
from config import influxCredentials,ROAD_FILE_PATH

logger = logging.getLogger(__name__)


def dist_lookup(
    road: pd.DataFrame,
    latitude: Union[float, np.ndarray],
    longitude: Union[float, np.ndarray],
) -> pd.DataFrame:
    """Maps latitude and longitude to race distance

    Args:
        road: DataFrame containing row that map latitude and longitude to race
            distance, must contain the columns "Latitude", "Longitude" and
            "Distance (km)"
        latitude: Array of latitude in decimal degrees
        longitude: Array of longitude in decimal degrees

    Returns:
        DataFrame with the columns "Latitude", "Longitude" and "Distance (km)".
    """
    mapped_location = pd.DataFrame(
        data=[latitude, longitude], index=["Latitude", "Longitude"]
    )
    mapped_location = mapped_location.T
    if ("Distance (km)" not in road.columns) and (
        road.index.name != "Distance (km)"
    ):
        raise KeyError("road missing Distance (km)")
    if road.index.name != "Distance (km)":
        road.set_index("Distance (km)", inplace=True)

    spots = mapped_location[["Latitude", "Longitude"]].drop_duplicates()
    for _, spot in spots.iterrows():
        distance = np.sqrt(
            (road.Longitude - spot.Longitude) ** 2
            + (road.Latitude - spot.Latitude) ** 2
        )

        # get the point the is closest along the route
        dist_along_route = road.index[distance.argmin()]

        # associate the spot to a distance along the route if it within 100m
        if distance.min() < 0.1:
            mapped_location.loc[
                mapped_location.Latitude == spot.Latitude, "Distance (km)"
            ] = dist_along_route
            logger.debug(
                "Associated spot %f, %f with %f km.",
                spot.Latitude,
                spot.Longitude,
                dist_along_route,
            )
        else:
            mapped_location.loc[
                mapped_location.Latitude == spot.Latitude, "Distance (km)"
            ] = np.NAN
            logger.info(
                "Dropping spot %f, %f, spot is %f km away from the route.",
                spot.Latitude,
                spot.Longitude,
                distance.min(),
            )
    mapped_location.dropna(subset="Distance (km)", inplace=True)
    mapped_location = mapped_location.merge(
        right=road[["Incline"]], on="Distance (km)"
    )
    return mapped_location


def calc_grad(road: tp.TecplotData) -> tp.TecplotData:
    """Calculate the incline for the Road File.

    Calculates the incline using the central difference scheme which is the same
    as what SolarSim does.

    Extract from SolarSim for reference:

    ```c
    (*RoadData).Incline[0] = ((*RoadData).Altitude[1]-(*RoadData).Altitude[0])
                         / ((*RoadData).Distance[1]-(*RoadData).Distance[0]);
    (*RoadData).Incline[(*RoadData).NDistances-1] = (  (*RoadData).Altitude[(*RoadData).NDistances-1]
                                                          -(*RoadData).Altitude[(*RoadData).NDistances-2])
                                                   /(  (*RoadData).Distance[(*RoadData).NDistances-1]
                                                          -(*RoadData).Distance[(*RoadData).NDistances-2]);
    PointN = 1;
    while (PointN < ((*RoadData).NDistances-1)) {

            (*RoadData).Incline[PointN] = ((*RoadData).Altitude[PointN+1]-(*RoadData).Altitude[PointN-1])
                                        / ((*RoadData).Distance[PointN+1]-(*RoadData).Distance[PointN-1]);

            PointN++;
    };
    ```

    Args:
        road:
            Road file as TecplotData object
    Returns:
        TecplotData class representing the road file tih column "Incline" added

    """
    road.data.rename(
        columns={
            "Altitude (m)": "Altitude",
        },
        inplace=True,
    )
    road.data.loc[:, "Distance"] = road.data.loc[:, "Distance (km)"] * 1000
    ndistances = road.zone.ni
    road.data.loc[0, "Incline"] = (
        road.data.Altitude.iloc[1] - road.data.Altitude.iloc[0]
    ) / (road.data.Distance.iloc[1] - road.data.Distance.iloc[0])
    road.data.loc[ndistances - 1, "Incline"] = (
        road.data.Altitude.iloc[-1] - road.data.Altitude.iloc[-2]
    ) / (road.data.Distance.iloc[-1] - road.data.Distance.iloc[-2])
    road.data.loc[1 : ndistances - 2, "Incline"] = (
        road.data.Altitude.loc[2 : ndistances - 1].to_numpy()
        - road.data.Altitude.loc[0 : ndistances - 3].to_numpy()
    ) / (
        road.data.Distance.loc[2 : ndistances - 1].to_numpy()
        - road.data.Distance.loc[0 : ndistances - 3].to_numpy()
    )
    road.data.rename(
        columns={
            "Altitude": "Altitude (m)",
        },
        inplace=True,
    )
    logger.info("Incline calculated.")
    return road


def main(
    if_credentials: influxCredentials = influxCredentials(),
    road_file_path: os.PathLike = "RoadFile-LatLon-2021.dat",
) -> None:
    """Get Latitude and Longitude info off the influxdb and maps it to race
    distance. Latitude and Longitude from the GPS are in the for DDMM.MMM so
    this script first converts it back to decimal degrees beforehand. Decoded
    latitude, longitude and mapped race distance are written back to the
    influxdb under the measurement "road_lookup"

    Args:
        if_credentials: Credentials for influxDB.
        road_file_path: File path to road file.

    Returns:
        None
    """
    logger.info("Distance mapping script started.")

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
    query_where = (
        'SELECT "GpsLatitude","GpsLongitude","GpsLat","GpsLon" '
        'FROM "Telemetry/Latitude","Telemetry/Longitude" '
        "WHERE (\"calc_grad\"::tag != 'True') AND (time > now() - 180d)"
    )

    ifdfq = influx_df_client.query(query_where)
    logger.info("Influx query successful")

    if ifdfq == {}:
        logger.info("No new points to process.")
        return
    # Reformat the data to a single dataframe and decode
    df = pd.concat([j.copy() for i, j in ifdfq.items()], axis=1)
    # decode the lat lon coordinates
    df["GpsLatitude"] = df["GpsLatitude"].apply(
        lambda x: x // 100 + (x % 100) / 60
    ) * ((df["GpsLat"] == "N") * 2 - 1)
    df["GpsLongitude"] = df["GpsLongitude"].apply(
        lambda x: x // 100 + (x % 100) / 60
    ) * ((df["GpsLon"] == "E") * 2 - 1)
    df = df.resample("1s").mean(numeric_only=True).dropna()
    logger.info("Lat Lon values decoded and resampled.")

    # Lookup
    road = tp.TecplotData(road_file_path)
    road = calc_grad(road)
    mapped_loc = dist_lookup(
        road.data, df.GpsLatitude.to_numpy(), df.GpsLongitude.to_numpy()
    )
    df = df.rename(
        columns={"GpsLatitude": "Latitude", "GpsLongitude": "Longitude"}
    )
    merged = (
        df.reset_index()
        .merge(mapped_loc, on=["Latitude", "Longitude"])
        .set_index("index")
    )
    logger.info("All location mapped.")

    # Write to influx
    # write mapped distance
    influx_df_client.write_points(
        merged,
        "road_lookup",
        {"post_processed": True},
        protocol="line",
        batch_size=5000,
    )

    # add tag to processed data
    for measurement, measurement_df in ifdfq.items():
        influx_df_client.write_points(
            measurement_df,
            measurement,
            tags={"calc_grad": True},
            protocol="line",
            batch_size=5000,
        )
        influx_client.delete_series(
            measurement=measurement, tags={"calc_grad": ""}
        )

    logger.info("All data written to influx.")

    influx_df_client.close()
    influx_client.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,  # Set the root logger's level
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[logging.StreamHandler()],  # Add a handler for the root logger
    )


    main(road_file_path=ROAD_FILE_PATH)
