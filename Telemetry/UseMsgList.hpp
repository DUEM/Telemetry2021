//Values for macros: 2 bits: MSB is read enable, LSB is write enable
#define USE_MSG_Telemetry_SystemStatusMessages 0b01 //0b01 because not actually reading from can bus, just sending them over radio, so write only
#define USE_MSG_Telemetry_TimeAndFix 0b01
#define USE_MSG_Telemetry_SpeedAndAngle 0b01
#define USE_MSG_Telemetry_Latitude 0b01
#define USE_MSG_Telemetry_Longitude 0b01
#define USE_MSG_Telemetry_AltitudeAndSatellites 0b01

#define USE_MSG_DriverControls_SpeedValCurrVal 0b10 //for running a small test function for validating CanAPI

#define USE_MSG_Telemetry_MpptPollJaved 0b01
#define USE_MSG_Telemetry_MpptPollWoof 0b01

#define PROCESS_ALL_MSG
