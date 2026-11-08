# Scripts to live process data
Collection of script that each process some data and uploads the calculated 
parameters back to Influx. 

The scripts will obtain the Influx DB Credentials from `config.py`
If `config.py` is not present in the current working directory, edit
the script to add the path `config.py` to path.

```python
import sys
sys.path.append(r"/path/to/script")
sys.path.append(r"C:\path\to\script")
```

## `road_lookup.py`
This script gets the GPS latitude and longitude off the influx db and uses
a SolarSim road file to map the coordinates to the closest linear distance. 
The mapping is done by finding the point that is closest by Eucledian distance,
and only maps it to a point if the closest one is within 100m.

The incline is also created from the Altitude in the road file. The calculation
is a mirror of that in SolarSim using the central difference method. 

Processing is done on all data that have not been processed. Once data is used 
a tag is added to it (`calc_grad`). Once the tag is added the data will not be 
processed again. 

All calculated parameters are written back to influx as fields written under the
measurement `road_lookup`.

**Make sure a road file is uploaded and `config.py` edited to point to the 
road file**

## `live_power.py`
This script performs live calculations to give estimate of the theoretical power
consumption.
It requires Incline to be calculated by `road_lookup.py` to be available, in 
addition it uses the vehicle velocity from Tritium, voltage and current into th
MPPTs, and (when integrated) wind measurements from the anemometer.
It performs the calculation by getting 
- the latest NPOINTS data points from each field
 
    AND 
- getting the data from the last TDELTA time period. 

These fields are then resampled to 1s for calculation. That does mean that 
you can end up with much more datapoint being calculated as the source 
data are not all on a common timebase. \
**Some tuning should be done to get a good balance between the amount of data 
this script processes and the speed of the script or memory used on the receiver laptop**


All calculated parameters are written back to influx as fields written under the
measurement `live_power`.

**Make sure to check the values used in `config.py`**