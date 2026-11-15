#ifndef SD_HEADER
#define SD_HEADER

struct conf {
    unsigned int gps_update;
    unsigned int sd_update;
    unsigned int status_update;
    unsigned int mppt_update;
    long time_fix;
    int serialCanMsg;
    double value0; 
    double value1;
};

void setupSD();
void startSDLog();
void logNMEAChar(char c); // buffer one raw GPS byte for the NMEA log
void flushSDLogs();       // write buffered NMEA and flush both log files

void getConfig();

void SDwriteLine();
void SDwrite();

#endif
