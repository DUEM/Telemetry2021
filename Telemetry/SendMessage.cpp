#include "SendMessage.hpp"
#include "HardwareSerial.h" //for Serial class
#include <SD.h>
#include "util/crc16.h"
#include "SerialDebugMacros.hpp"
#include "StatusMsg.hpp"
#include "SensorInputs.hpp"

#define LOG_TO_SERIAL //Now a copy of SD stream and radio stream will be logged to serial output.

//buffer structure: ID0 ID1 DLC D[1]...D[DLC] CRC0 CRC1
uint8_t byte_buffer[13]; // For CAN message in byte format to be transmitted (includes crc). 13 is the max size = 2+1+dlc+2

#define XBeeSerial Serial2
extern CANHelper::CANHandler canHandler;
extern File dataFile;
union absoluteTimeUnion_t {
  long asLong;
  uint8_t asBytes[sizeof(long)];
};
absoluteTimeUnion_t absoluteTime;

void setupSending() {
  XBeeSerial.begin(115200);
}

void out_byte(uint8_t b) {
    /* Send and log byte. Send to serial if set in config file */

    //Send over radio
    XBeeSerial.write(b);

#ifdef LOG_TO_SERIAL
    Serial.print(b, HEX);
    Serial.print(" ");
#endif
    if(dataFile) {
      dataFile.write(b);
    }
    /*if (dataFile) {
        dataFile.print(b, HEX);
        dataFile.print(" ");
        if (sysStatus.data[1] == STAT_BAD) {
            updateStatus(1, STAT_GOOD);
            sendMessage(sysStatus);
        }
    }
    else if (sysStatus.data[1] == STAT_GOOD) {
        updateStatus(1, STAT_BAD);
        sendMessage(sysStatus);
    }*/ //will come back to this
}

void gencrc() {
    uint16_t crc = 0xFFFF, i;
    for(i = 0; i < sizeof(absoluteTime); i++) {
      crc = _crc16_update(crc, absoluteTime.asBytes[i]);
    }
    for(i = 0; i < byte_buffer[2] + 3; i++) {
      crc = _crc16_update(crc, byte_buffer[i]);
    }
    byte_buffer[byte_buffer[2] + 3] = (crc >> 8) & 0xFF; // Bit shift. print most significant byte first, then least.
    byte_buffer[byte_buffer[2] + 4] = crc & 0xFF;
}

//Sending Data
void sendMessage(CANHelper::CANHelperBuffer& msg) { //Format: TI0 TI1 TI2 TI3 ID0 ID1 DLC B0 B1 B2 B3 B4 B5 B6 B7 CRC0 CRC1
    /* Sends CAN style message to XBee and logs to SD card.
     * By having in one function means we can be sure everything is robust to lack of SD card for example.
     */
    
    // Split CAN ID into 2 bytes in order to .write()
    uint8_t can_id_b0 = (msg.raw.can_id >> 8) & 0xFF;   // Remember, 11 bit CAN ID so 2047 is the max (0x7FF)
    uint8_t can_id_b1 = msg.raw.can_id & 0xFF;

    // Add CAN ID to byte_buffer for later use in CRC calculation
    byte_buffer[0] = can_id_b0;
    byte_buffer[1] = can_id_b1;
    byte_buffer[2] = msg.raw.can_dlc;

    // Add data to byte buffer
    for (int i = 0; i < msg.raw.can_dlc; i++)  {
        byte_buffer[i+3] = msg.raw.data[i];
    }

    //update millis (absolute timestamp which the reciever will use along with latest GPS time fix to get actual time this message was transmitted. Time delta is calculated on the reciver just in case gps time update crc fails)
    absoluteTime.asLong = millis(); //Need to do this before gencrc()
    for(int i = 0; i < sizeof(long); i++) { //Append time millis at the end (to avoid having to modify code in reciever). Ignore that, millis at start anyway
      out_byte(absoluteTime.asBytes[i]);
    }

    gencrc(); //regen CRC with new data in byte buffer

    //Send bytes
    for(int i = 0; i < byte_buffer[2] + 5; i++) { //byte_buffer[2] is the dlc
      out_byte(byte_buffer[i]);
    }

    out_byte(0x7E); //End Of Frame marker

#ifdef LOG_TO_SERIAL
    Serial.println();
#endif
}

GPSData::GPSData() {
  canHandler.setCanMeta(this->altitudeSatellites, CAN_META_Telemetry_AltitudeAndSatellites);
  canHandler.setCanMeta(this->latitude, CAN_META_Telemetry_Latitude);
  canHandler.setCanMeta(this->longitude, CAN_META_Telemetry_Longitude);
  canHandler.setCanMeta(this->speedAngle, CAN_META_Telemetry_SpeedAndAngle);
}
