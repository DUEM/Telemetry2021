
#define SLEEP_INT 33
#define FLAG_INT 22

void setupSensorInputs();
void powerStatus(); //Power check
void flagStatus(); //Marker switch check

void updateGPS(); //Update GPS
void readGPS(); //Get GPS to read
long whenTimeFix(); //For time resolving
