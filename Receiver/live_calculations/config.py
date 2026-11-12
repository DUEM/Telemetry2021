from typing import NamedTuple

# used by all live_calculation scripts: the same database the receiver writes to
# (Receiver/receiver_config.py)
class influxCredentials(NamedTuple):
    username: str = "admin"
    password: str = "password"
    db: str = "DUSCiESC"
    host: str = "localhost"
    port: int = 8086
    enabled: bool = True


ifCredentials = influxCredentials()

# road_lookup.py
ROAD_FILE_PATH = "RoadFile-LatLon-2021.dat"
ROAD_FILE_PATH = "Road-Top-Gear-Foo-V1.dat"

# live_power.py
TDELTA = "180d"  # how far back do we retrieve data (e.g. "2h", "180d")
NPOINTS = 100000  # how many data points we limit to
VEHICLE_MASS = 250
G = 9.81
MOTOR_EFF = 0.95
CRR = 0.004
CDA = 0.1
RHO = 1.225
