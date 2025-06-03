#define DEBUG

#ifdef DEBUG
  #include "HardwareSerial.h"
  #define DEBUG_PRINT(x)  Serial.print (x)
  #define DEBUG_PRINTLN(x)  Serial.println (x)
  #define DEBUG_WRITE(x)  Serial.write (x)
  #define DEBUG_PRINTHEX(x) Serial.print (x, HEX)
#else
  #define DEBUG_PRINT(x)
  #define DEBUG_PRINTLN(x)
  #define DEBUG_WRITE(x)
  #define DEBUG_PRINTHEX(x)
#endif
