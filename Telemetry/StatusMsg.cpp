#include "StatusMsg.hpp"
#include "SendMessage.hpp"

CANHelper::CANHelperBuffer sysStatus;
#define SYS_STAT_BUF sysStatus.payloadBuffer.as_Telemetry_SystemStatusMessages

void setupStatusMsg(CANHelper::CANHandler canHandler) {
  canHandler.setCanMeta(sysStatus, CAN_META_Telemetry_SystemStatusMessages);
}

void updateStatus() {
  sendMessage(sysStatus);
}

void setPowerStatus(uint8_t s) {
  SYS_STAT_BUF.Power = s;
}
void setWritingSDStatus(uint8_t s) {
  SYS_STAT_BUF.WritingToSd = s;
}
void setGPSObtainedStatus(uint8_t s) {
  SYS_STAT_BUF.GpsTimeObtained = s;
}
void setLoadedConfigStatus(uint8_t s) {
  SYS_STAT_BUF.LoadedConfig = s;
}
void setMarkerFlagStatus(uint8_t s) {
  SYS_STAT_BUF.Flag = s;
}
