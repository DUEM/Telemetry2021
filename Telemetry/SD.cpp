#include "Arduino.h"
#include "SD.hpp"
#include "SerialDebugMacros.hpp"
#include <SD.h>
#include "StatusMsg.hpp"
#include <ArduinoJson.h>
#include "src/CANApi/CANHelper.hpp"

#define SD_SS 12 //was 12 or 53
#define CONFIG_FILENAME "config.txt"

conf config;
extern CANHelper::CANHelperBuffer time;
File dataFile;

void set_defaults() {
    /* We run this if for whatever reason we can't read config.txt
        a)  Either can't initialise SD card, or
        b)  can't find file or deserialize it.
        c)  At the moment if a field doesn't exist, it's incorrectly read as zero.
     */
    config.gps_update = 2000; // 2000ms update on position and time
    config.sd_update = 2000;
    config.status_update = 500;
    config.time_fix = 20000; //
    config.mppt_update = 1000;
    config.serialCanMsg = 1;    // Default send CAN messages on serial
    config.value0 = -1;
    config.value1 = -1;
    DEBUG_PRINTLN("Using defaults");

    /// Actually probably better to set these at the start and overwrite IF we can. ie if we can't we just use the original value
    /// However, I think a null field just overwrites as zero...
}

void load_config() {
    // Open file for reading
    File configFile = SD.open(CONFIG_FILENAME);
    DEBUG_PRINT("Opening: ");
    DEBUG_PRINTLN(CONFIG_FILENAME);

    // Size of the stuff
    DynamicJsonDocument doc(192); // Tool to calculate this value: https://arduinojson.org/v6/assistant/

    // Parse the file
    DeserializationError error = deserializeJson(doc, configFile);

    if (error) {
        setLoadedConfigStatus(STAT_DEFAULTS); // Cry if we have an error
        DEBUG_PRINT(F("deserializeJson() failed: "));
        DEBUG_PRINTLN(error.f_str());
        // But also do what we can and use some defaults
        set_defaults();
        return;
    }

    setLoadedConfigStatus(STAT_GOOD); // No error

    // Put the read values into our config structure
    config.gps_update = doc["gps_update"];  DEBUG_PRINT("GPS UPDATE:\t");   DEBUG_PRINTLN(config.gps_update);
    config.time_fix = doc["time_fix"];      DEBUG_PRINT("TIME FIX:\t");     DEBUG_PRINTLN(config.time_fix);
    config.sd_update = doc["sd_update"];    DEBUG_PRINT("SD UPDATE:\t");    DEBUG_PRINTLN(config.sd_update);
    config.status_update = doc["status_update"];    DEBUG_PRINT("STATUS UPDATE:\t");    DEBUG_PRINTLN(config.status_update);
    config.gps_update = doc["mppt_update"]; DEBUG_PRINT("MPPT UPDATE:\t");  DEBUG_PRINTLN(config.mppt_update);
    config.serialCanMsg = doc["serialCanMsg"];      DEBUG_PRINT("SERIAL CAN:\t");       DEBUG_PRINTLN(config.serialCanMsg);
    config.value0 = doc["spare"][0];   DEBUG_PRINT("VAL0:\t");   DEBUG_PRINTLN(config.value0);
    config.value1 = doc["spare"][1];   DEBUG_PRINT("VAL1:\t");   DEBUG_PRINTLN(config.value1);

    DEBUG_PRINTLN("Configuration set from SD, closing file");
    // Close the file; we can only have one open at a time
    configFile.close();

    // If wanted to do a bigger file: https://arduinojson.org/v6/how-to/deserialize-a-very-large-document/
}

void startSDLog() {
    // https://learn.adafruit.com/adafruit-data-logger-shield/using-the-real-time-clock-3
    DEBUG_PRINTLN("Starting SD log");

    // Get date. If GPS signal is not available this will default to 00/00/00
    int8_t YY = time.payloadBuffer.as_Telemetry_TimeAndFix.GpsYear;
    int8_t MM = time.payloadBuffer.as_Telemetry_TimeAndFix.GpsMonth;
    int8_t DD = time.payloadBuffer.as_Telemetry_TimeAndFix.GpsDay;

    char filename[13]; //"YYMMDD00.txt" Filename is max 12 characters long

    // Replace YYMMDD with date
    filename[0] = YY/10 + '0';
    filename[1] = YY%10 + '0';
    filename[2] = MM/10 + '0';
    filename[3] = MM%10 + '0';
    filename[4] = DD/10 + '0';
    filename[5] = DD%10 + '0';
    
    filename[8] = '.';
    filename[9] = 'b'; //t
    filename[10] = 'i'; //x
    filename[11] = 'n'; //t
    filename[12] = '\0';

    // If we've already recorded today, +1 to trailing number
    for (uint8_t i = 0; i < 100; i++) {
        filename[10-4] = i/10 + '0';
        filename[11-4] = i%10 + '0';
        if (! SD.exists(filename)) {
            dataFile = SD.open(filename, FILE_WRITE); // Only create a new file which doesn't exist
            if (dataFile) {
                DEBUG_PRINT("Opening file: ");
                DEBUG_PRINTLN(filename);
                setLoadedConfigStatus(100 + i);
            }
            // if the file isn't open, pop up an error:
            else {
                DEBUG_PRINT("Could not open file: ");
                DEBUG_PRINTLN(filename);
                /// Some sort of backup filename here?
                // will only log in loop if dataFile==True
                setLoadedConfigStatus(90);
            }
            return;
        }
    }
}

void setupSD() {
  /* Start the SD card */
  if(SD.begin(SD_SS)) {
    DEBUG_PRINTLN("SD card initialised");
    setWritingSDStatus(STAT_GOOD);
    load_config(); // Load mode and pop it in config
  } else {
    DEBUG_PRINTLN("SD card failed, or not present");
    setWritingSDStatus(STAT_BAD);
    set_defaults(); //use default config
  }
}
