#include "src/CANApi/CanApiv04.hpp"
#include "SD.hpp"
#include <SD.h>
#include "SendMessage.hpp"
#include <Adafruit_GPS.h>
#include "SerialDebugMacros.hpp"
#include "SendMessage.hpp"
#include "StatusMsg.hpp"
#include "SensorInputs.hpp"

//pins
#define MCP_SS 10 //was 51 or 10
#define SLEEP_INT 33
#define FLAG_INT 22

CANHelper::CanMsgHandler CANHandler(MCP_SS);
extern conf config;
extern File dataFile;
extern CANHelper::Messages::Telemetry::_TimeAndFix time;

//#define canTestMsg //This was running the whole time and sending false status messages lol
#ifdef canTestMsg
CANHelper::Messages::Telemetry::_SystemStatusMessages canTest; //synthetic CAN test
#endif

uint8_t statusNumber; //For status LEDs
void setup() { //dont forget to change bitrate to 50KBPS
  Serial.begin(230400);
  DEBUG_PRINTLN("Setting up");

  //Set status LED pinmodes
  pinMode(35, OUTPUT);
  pinMode(37, OUTPUT);
  pinMode(39, OUTPUT);

  statusNumber = 0;
  updateStatusLEDs(++statusNumber);
  //Set pinmodes
  pinMode(12, OUTPUT); //stop SDSS going into slave mode. This might be why the SD card is freezing
  pinMode(10, OUTPUT); // Default CS pin must be set o/p even if not being used.
  pinMode(SLEEP_INT, INPUT_PULLUP);
  pinMode(FLAG_INT, INPUT_PULLUP);

  //feature boards setups
  updateStatusLEDs(++statusNumber);
  setupSD(); //must be done before sensor inputs because GPS needs this
  updateStatusLEDs(++statusNumber);
  setupSensorInputs();
  updateStatusLEDs(++statusNumber);
  startSDLog(); //must be done after sensor inputs because this needs GPS
  updateStatusLEDs(++statusNumber);
  setupSending();
  updateStatusLEDs(++statusNumber);
  sendMessage(time); //To synchronise receiver. This should be the first message in SD log and radio

  //mcp2515.reset(); //Here to remind myself to add to library
  updateStatusLEDs(0);

  setPowerStatus(STAT_GOOD);  // Position 0 is power. Send status that setup is happening.
  updateStatus();

  //CAN test test data
#ifdef canTestMsg
  canTest.data.Power = 24;
#endif

  DEBUG_PRINTLN("Setup complete");
}

uint32_t sd_timer = millis();
uint32_t status_timer = millis();
uint32_t gps_timer = millis();
uint32_t mppt_timer = millis();
void loop() {
  //Serial.println("LOOP START");

  powerStatus();  // Check power status
  flagStatus();   // Check flag
  CANHandler.read();      // Read incoming CAN message and treat accordingly
  //pollSensor();   // Poll additional sensors

  /* Flush SD file at interval defined in config file */
  if ((millis() - sd_timer) > config.sd_update) {
    sd_timer = millis();
    dataFile.flush();
    DEBUG_PRINTLN("SD Flush");
  }

  /* Update GPS */
  readGPS();
  if((millis() - gps_timer) > config.gps_update) {
    gps_timer = millis();
    updateGPS();
  }

  /* Send system status update at desired interval */
  if ((millis() - status_timer) > config.status_update) {
    updateStatus();
    status_timer = millis();
  }

  /* MPPT Poll */
  if((millis() - mppt_timer) > config.mppt_update) {
    CANHelper::Messages::Telemetry::_MpptPollJaved javedPoll;
    CANHelper::Messages::Telemetry::_MpptPollWoof woofPoll;

    //Send to radio and SD
    sendMessage(javedPoll);
    sendMessage(woofPoll);

    //Send over CAN bus
    CANHandler.send(javedPoll);
    CANHandler.send(woofPoll);
    mppt_timer = millis();
  }

#ifdef canTestMsg
  CANHandler.send(canTest);
#endif

  //Serial.println("Reading...");
  //CANHandler.read();

  //DEBUG_PRINTLN(""); //println break between frames. Easier to read serial
  //delay(1000); //This breaks GPS. Something to do with Serial overwriting probably
}

void updateStatusLEDs(uint8_t statusCode)
{
  digitalWrite(35, (statusCode & 4) ? HIGH : LOW);
  digitalWrite(37, (statusCode & 2) ? HIGH : LOW);
  digitalWrite(39, (statusCode & 1) ? HIGH : LOW);
  //delay(1000);
}

//Just relays all CAN messages over radio
void CANHelper::Messages::processAll(CANHelper::Messages::CANMsg& msg)
{
  sendMessage(msg);

  //if 0xXX1, its a status message. See updateStatus below
  /*if(msg.metadata.is & 1) {

  }*/
}

/*void updateStatus(int pos, uint8_t val) { //wandering if worth adding to library. Then all IDs in format 0xXX1 could be status IDs. Can then log them in status logs
    // Have as a function so we can add functionality like LEDs.
    sysStatus.data[pos] = val;
}*/

void CANHelper::Messages::processMessage(CANHelper::Messages::DriverControls::_SpeedValCurrVal& msg) {
  Serial.print("Set Current: ");
  Serial.print(msg.data.DriverSetCurrent);
  Serial.print("| Set Speed: ");
  Serial.println(msg.data.DriverSetSpeed);
  CANHandler.send(msg); //just reflecting data to confirm message was received
}
void CANHelper::Messages::processMessage(CANHelper::Messages::Telemetry::_SystemStatusMessages& msg) {}
void CANHelper::Messages::processMessage(CANHelper::Messages::Telemetry::_TimeAndFix& msg) {}
void CANHelper::Messages::processMessage(CANHelper::Messages::Telemetry::_SpeedAndAngle& msg) {}
void CANHelper::Messages::processMessage(CANHelper::Messages::Telemetry::_AltitudeAndSatellites& msg) {}
void CANHelper::Messages::processMessage(CANHelper::Messages::Telemetry::_MpptPollJaved& msg) {}
void CANHelper::Messages::processMessage(CANHelper::Messages::Telemetry::_MpptPollWoof& msg) {}
