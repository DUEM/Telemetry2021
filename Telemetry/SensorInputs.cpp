#include "Adafruit_PMTK.h"
#include "SensorInputs.hpp"
#include "SerialDebugMacros.hpp"
#include <Adafruit_GPS.h>
#include "src/CANApi/CanApiv04.hpp"
#include "StatusMsg.hpp"
#include "SD.hpp"
#include "SendMessage.hpp"
using namespace CANHelper::Messages::Telemetry;

#define GPSSerial Serial1 //hardware serial that GPS is connected to
#define GPSECHO //enables GPS debug messages to serial

//Boolean states
bool car_on; // = !safestate
bool flag_status;
Adafruit_GPS GPS(&GPSSerial); //GPS handle

_TimeAndFix time; //store time in memory
extern conf config;
extern CANHelper::CanMsgHandler CANHandler;
long millisWhenGpsTimeUpdate;

void updateTimeCANMsg() {
  time.data.GpsHour = GPS.hour;
  time.data.GpsMinute = GPS.minute;
  time.data.GpsSeconds = GPS.seconds;
  time.data.GpsDay = GPS.day;
  time.data.GpsMonth = GPS.month;
  time.data.GpsYear = GPS.year;
  time.data.GpsFix = GPS.fix;
  time.data.GpsFixquality = GPS.fixquality;
  millisWhenGpsTimeUpdate = millis();
}

GPSData gpsData; //would be nice if this worked by using 1 can_frame variable rather than a struct of 4
void gps2canMsgs() {
  // Time + fix
  updateTimeCANMsg();
  sendMessage(time);
  //sendMessage(time);

  // Speed + angle
  gpsData.speedAngle.data.GpsSpeed = GPS.speed;
  gpsData.speedAngle.data.GpsAngle = GPS.angle;
  sendMessage(gpsData.speedAngle);

  // Latitude + longitude together (0x0FB), from the same fix. Replaces the
  // separate Latitude (248) and Longitude (249) messages, which sent NMEA
  // ddmm.mmmm as a float with the hemisphere as a separate character.
  // latitude_fixed/longitude_fixed are degrees x 1e7 parsed from the NMEA text
  // with integer maths only. Don't build them from latitudeDegrees: a double is
  // only 32-bit on the Mega (about 0.4 m steps at our latitude).
  // Adafruit_GPS 1.9 already makes south/west negative; older versions gave
  // the magnitude only. Taking the magnitude and applying the hemisphere here
  // is correct with either.
  int32_t lat = labs(GPS.latitude_fixed);
  int32_t lon = labs(GPS.longitude_fixed);
  if (GPS.lat == 'S') lat = -lat;
  if (GPS.lon == 'W') lon = -lon;
  gpsData.position.data.GpsLatitudeDeg = lat;
  gpsData.position.data.GpsLongitudeDeg = lon;
  sendMessage(gpsData.position);

  // Altitude + satellites
  gpsData.altitudeSatellites.data.GpsAltitude = GPS.altitude;
  gpsData.altitudeSatellites.data.GpsSatellites = GPS.satellites;
  sendMessage(gpsData.altitudeSatellites);

  //testing time since time fix function
  //Serial.println(GPS.secondsSinceTime());
}
/*can_frame GPSMessageStore;
void gps2canMsgs() { //doesnt work because casting from can_frame does not add id and dlc
  // Time + fix
  updateTimeCANMsg();
  sendMessage(time);

  // Speed + angle
  ((_SpeedAndAngle&) GPSMessageStore).data.GpsSpeed = GPS.speed;
  ((_SpeedAndAngle&) GPSMessageStore).data.GpsAngle = GPS.angle;
  sendMessage(GPSMessageStore);

  // Latitude
  ((_Latitude&) GPSMessageStore).data.GpsLatitude = GPS.latitude;
  ((_Latitude&) GPSMessageStore).data.GpsLat = GPS.lat;
  sendMessage(GPSMessageStore);

  // Longitude
  ((_Longitude&) GPSMessageStore).data.GpsLongitude = GPS.longitude;
  ((_Longitude&) GPSMessageStore).data.GpsLon = GPS.lon;
  sendMessage(GPSMessageStore);

  // Altitude + satellites
  ((_AltitudeAndSatellites&) GPSMessageStore).data.GpsAltitude = GPS.altitude;
  ((_AltitudeAndSatellites&) GPSMessageStore).data.GpsSatellites = GPS.satellites;
  sendMessage(GPSMessageStore);
}*/

void setupSensorInputs() {
  GPS.begin(9600);

  GPS.sendCommand(PMTK_SET_NMEA_OUTPUT_RMCGGA);
  GPS.sendCommand(PMTK_SET_NMEA_UPDATE_1HZ);
  //GPS.sendCommand(PGCMD_ANTENNA);
  //GPSSerial.println(PMTK_Q_RELEASE);

  //fix to stop excel complaining about illegal characters when GPS fix not yet aqcuired. Ignore this. GPS fix messages are no longer sent until fix is found
  //gpsData.latitude.data.GpsLat = 'U'; //U = Unknown. Will become either E or W when GPS gets location
  //gpsData.longitude.data.GpsLon = 'U'; //Will become either N or S when GPS gets location
  //DEBUG_PRINTLN("Set GpsLat and GpsLon to U to stop excel complaining");

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
                  //print_datetimefix();
                  updateTimeCANMsg(); //Moved to Telemetry.ino as this runs before logging and radio are initialised.

                  break;
              }
              else {
                  DEBUG_PRINTLN("Time not yet acquired");
                  //print_datetimefix();
              }
          }
          else {
              DEBUG_PRINTLN("parsing failed");
          }
      }
      //Telemetry should not start until GPS time and fix acquired. This is to avoid time desync issues between this and receiver (grafana) and make sure log files are properly named
      /*uint32_t timerCheck = millis();
      if (timerCheck - timer > config.time_fix) {
          DEBUG_PRINTLN("timeout for time acquisition exceeded.");
          DEBUG_PRINT("GPS time acquire timer check: "); DEBUG_PRINTLN(timerCheck);
          break;
      }*/
  }
}

void readGPS() {
  //DEBUG_PRINTLN("Poll GPS");
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
  //if (GPS.newNMEAreceived()) {
    DEBUG_PRINTLN("New NMEA received");
    if(GPS.parse(GPS.lastNMEA())) {
      //print_datetimefix();
      //print_location();
      DEBUG_PRINTLN("New NMEA parsed");
      //gps2canMsgs();  // Convert, send and log time, location etc from GPS
    } else {
      DEBUG_PRINTLN("Could not parse new NMEA");            
    }
    //debug print NMEA
    DEBUG_PRINT("NMEA: ");
    DEBUG_PRINTLN(GPS.lastNMEA());
  }
}

void updateGPS() { //https://learn.adafruit.com/adafruit-ultimate-gps?view=all //FIX LED flashes every second until it gets a fix
    //char c = GPS.read(); //check why reading more frequently than logging. (reads every loop but only logs after a certain time interval). Not sure if necessary
    //if (millis() - timer > config.gps_update) { //handled in calling code (Telemetry.ino)
        //timer = millis(); // reset the timer
        if(GPS.fix) {
          gps2canMsgs();
        }
    //}
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
        //updateStatus(0, car_on);
        setPowerStatus(car_on);
        //sendMessage(sysStatus);
        //dataFile.flush();
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
        //updateStatus(4, digitalRead(FLAG_INT));
        //sendMessage(sysStatus);
        setMarkerFlagStatus(flag_status);
        DEBUG_PRINT("Flag: ");
        DEBUG_PRINTLN(flag_status);
    }
}
