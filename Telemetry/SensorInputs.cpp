#include "Adafruit_PMTK.h"
#include "SensorInputs.hpp"
#include "SerialDebugMacros.hpp"
#include <Adafruit_GPS.h>
#include "src/CANApi/CANHelper.hpp"
#include "StatusMsg.hpp"
#include "SD.hpp"
#include "SendMessage.hpp"

#define GPSSerial Serial1 //hardware serial that GPS is connected to
#define GPSECHO //enables GPS debug messages to serial

//Boolean states
bool car_on; // = !safestate
bool flag_status;
Adafruit_GPS GPS(&GPSSerial); //GPS handle

#define TIME_CAN_BUF time.payloadBuffer.as_Telemetry_TimeAndFix
CANHelper::CANHelperBuffer time;
extern conf config;
extern CANHelper::CANHandler canHandler;
long millisWhenGpsTimeUpdate;

void updateTimeCANMsg() {
  TIME_CAN_BUF.GpsHour = GPS.hour;
  TIME_CAN_BUF.GpsMinute = GPS.minute;
  TIME_CAN_BUF.GpsSeconds = GPS.seconds;
  TIME_CAN_BUF.GpsDay = GPS.day;
  TIME_CAN_BUF.GpsMonth = GPS.month;
  TIME_CAN_BUF.GpsYear = GPS.year;
  TIME_CAN_BUF.GpsFix = GPS.fix;
  TIME_CAN_BUF.GpsFixquality = GPS.fixquality;
  millisWhenGpsTimeUpdate = millis();
}

GPSData gpsData; //would be nice if this worked by using 1 can_frame variable rather than a struct of 4
#define SPEEDANGLE_CAN_BUF gpsData.speedAngle.payloadBuffer.as_Telemetry_SpeedAndAngle
#define LAT_CAN_BUF gpsData.latitude.payloadBuffer.as_Telemetry_Latitude
#define LON_CAN_BUF gpsData.longitude.payloadBuffer.as_Telemetry_Longitude
#define ALT_CAN_BUF gpsData.altitudeSatellites.payloadBuffer.as_Telemetry_AltitudeAndSatellites
void gps2canMsgs() {
  // Time + fix
  updateTimeCANMsg();
  sendMessage(time);

  // Speed + angle
  SPEEDANGLE_CAN_BUF.GpsSpeed = GPS.speed;
  SPEEDANGLE_CAN_BUF.GpsAngle = GPS.angle;
  sendMessage(gpsData.speedAngle);

  // Latitude
  LAT_CAN_BUF.GpsLatitude = GPS.latitude;
  LAT_CAN_BUF.GpsLat = GPS.lat;
  sendMessage(gpsData.latitude);

  // Longitude
  LON_CAN_BUF.GpsLongitude = GPS.longitude;
  LON_CAN_BUF.GpsLon = GPS.lon;
  sendMessage(gpsData.longitude);

  // Altitude + satellites
  ALT_CAN_BUF.GpsAltitude = GPS.altitude;
  ALT_CAN_BUF.GpsSatellites = GPS.satellites;
  sendMessage(gpsData.altitudeSatellites);
}

void setupSensorInputs() {
  GPS.begin(9600);

  GPS.sendCommand(PMTK_SET_NMEA_OUTPUT_RMCGGA);
  GPS.sendCommand(PMTK_SET_NMEA_UPDATE_1HZ);

  //setup CAN Buffers
  canHandler.setCanMeta(time, CAN_META_Telemetry_TimeAndFix);
  //GPS data buffers are set through the GPSData constructor (defined at bottom)

  /* Check current date and time from GPS */ // - this could do with a whole load of squishing
  DEBUG_PRINTLN("Checking GPS...");
  uint32_t timer = millis();
  DEBUG_PRINT("GPS time acquire timer: "); DEBUG_PRINTLN(timer);
  DEBUG_PRINT("GPS time acquire max: "); DEBUG_PRINTLN(config.time_fix);
  while (0) { //Boot will skip GPS valid time check now. If GPS already has time fix (i.e. RTC is already set), then this shouldn't cause an issue. Otherwise, the pi rtc will be used until GPS gives a time fix message.s
      char c = GPS.read();
#ifdef GPSECHO
      if(c)
        DEBUG_PRINT(c);
#endif
      if (GPS.newNMEAreceived()) {
          //DEBUG_PRINT(GPS.lastNMEA());
          if (GPS.parse(GPS.lastNMEA())) {
              if (!(GPS.year == 0) && !(GPS.year == 80)) { // Before we think life is good, make sure we've actually go the date right - sometimes will read as 0 even when we have time or get it wrong and send 80
                  DEBUG_PRINTLN(">>> Time acquired <<<");
                  setGPSObtainedStatus(STAT_GOOD);  // GPS time acquired
                  updateTimeCANMsg(); //Moved to Telemetry.ino as this runs before logging and radio are initialised.

                  break;
              }
              else {
                  DEBUG_PRINTLN("Time not yet acquired");
              }
          }
          else {
              DEBUG_PRINTLN("parsing failed");
          }
      }
  }
}

void readGPS() {
  if(!GPS.newNMEAreceived()) {
    //DEBUG_PRINTLN("No new NEMA received");
#ifdef GPSECHO
    char c = GPS.read();
    if(c)
      DEBUG_PRINT(c);
#else
    GPS.read();
#endif
  } else {
    DEBUG_PRINTLN("New NMEA received");
    if(GPS.parse(GPS.lastNMEA())) {
      DEBUG_PRINTLN("New NMEA parsed");
    } else {
      DEBUG_PRINTLN("Could not parse new NMEA");            
    }
    //debug print NMEA
    DEBUG_PRINT("NMEA: ");
    DEBUG_PRINTLN(GPS.lastNMEA());
  }
}

void updateGPS() { //https://learn.adafruit.com/adafruit-ultimate-gps?view=all //FIX LED flashes every second until it gets a fix
  if(GPS.fix) {
    gps2canMsgs();
  }
}

long whenTimeFix() {
  return millisWhenGpsTimeUpdate;
}

void powerStatus() {
    /* Check status.
     * Update and send if there has been a change.
     * Flush SD to ensure event recorded
     * Code proceeds as normal; BMS messages can still be received when safestate.
     */
    if (car_on != digitalRead(SLEEP_INT)) {
        car_on = !car_on;
        setPowerStatus(car_on);
        DEBUG_PRINT("State of car: ");
        DEBUG_PRINTLN(car_on);
    }
}

void flagStatus() {
    /* Driver can change the flag to put a marker in the data.
     * Only update and send on a change.
     */
    if (flag_status != digitalRead(FLAG_INT)) {
        flag_status = !flag_status;
        setMarkerFlagStatus(flag_status);
        DEBUG_PRINT("Flag: ");
        DEBUG_PRINTLN(flag_status);
    }
}
