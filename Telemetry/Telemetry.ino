#include "src/CANApi/CANHelper.hpp"
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

CANHelper::CANHandler canHandler(MCP_SS, CAN_50KBPS);
extern conf config;
extern File dataFile;
extern CANHelper::CANHelperBuffer time;

void setup() { //dont forget to change bitrate to 50KBPS
  Serial.begin(230400);
  DEBUG_PRINTLN("Setting up");

  setupStatusMsg(canHandler);

  //Set status LED pinmodes
  pinMode(35, OUTPUT);
  pinMode(37, OUTPUT);
  pinMode(39, OUTPUT);

  uint8_t statusNumber = 0; //For status LEDs
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

  DEBUG_PRINTLN("Setup complete");
}

uint32_t sd_timer = millis();
uint32_t status_timer = millis();
uint32_t gps_timer = millis();
uint32_t mppt_timer = millis();
void loop() {
  powerStatus();  // Check power status
  flagStatus();   // Check flag
  canHandler.read();      // Read incoming CAN message and treat accordingly

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
    CANHelper::CANHelperBuffer poll;
    poll.payloadBuffer.as_Telemetry_MpptPollJaved.Blank = 0; //mppt has 1 byte as influx complains of 0 byte payloads. Also doent matter as to which struct its casted to as poll and javed have equal structures

    canHandler.setCanMeta(poll, CAN_META_Telemetry_MpptPollJaved);
    sendMessage(poll); //send over radio (and SD)
    canHandler.send(poll); //send to CAN bus

    canHandler.setCanMeta(poll, CAN_META_Telemetry_MpptPollWoof);
    sendMessage(poll);
    canHandler.send(poll);

    mppt_timer = millis();
  }
}

void updateStatusLEDs(uint8_t statusCode) {
  digitalWrite(35, (statusCode & 4) ? HIGH : LOW);
  digitalWrite(37, (statusCode & 2) ? HIGH : LOW);
  digitalWrite(39, (statusCode & 1) ? HIGH : LOW);
}

//Just relays all CAN messages over radio
void CANHelper::CanMsgHandler::processAll(CANHelper::CANHelperBuffer& msg) {
  sendMessage(msg);
}

//test function
void CANHelper::CanMsgHandler::processMessage(CANHelper::Messages::DriverControls::SpeedValCurrVal& msg) {
  Serial.print("Set Current: ");
  Serial.print(msg.DriverSetCurrent);
  Serial.print("| Set Speed: ");
  Serial.println(msg.DriverSetSpeed);
}
