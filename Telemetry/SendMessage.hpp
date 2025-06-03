#ifndef SENDMESSAGE_HEADER
#define SENDMESSAGE_HEADER

#include "src/CANApi/CANHelper.hpp"

class GPSData {
public:
  GPSData();
  CANHelper::CANHelperBuffer speedAngle;
  CANHelper::CANHelperBuffer latitude;
  CANHelper::CANHelperBuffer longitude;
  CANHelper::CANHelperBuffer altitudeSatellites;
};

void setupSending();
void sendMessage(CANHelper::CANHelperBuffer& msg);

#endif
