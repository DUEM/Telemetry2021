# Telemetry board firmware (on vehicle)

This Arduino firmware runs on the vehicle telemetry board. It is unchanged since BWSC 2023 (see branch [`nick-22Library`](https://github.com/DUEM/Telemetry2021/tree/nick-22Library)).

It relays every CAN message it receives (`PROCESS_ALL_MSG` in [UseMsgList.hpp](UseMsgList.hpp)) over the XBee radio and logs it to the SD card. It also:

* adds GPS messages (time and fix, speed and angle, latitude, longitude, altitude and satellites)
* adds a periodic system status message
* sends the MPPT poll requests onto the CAN bus

## Hardware

| Item | Connection |
|---|---|
| Board | Arduino **Mega 2560** |
| CAN controller | MCP2515, SPI chip select pin **10** (CAN bus runs at **125 kbps**) |
| SD card | SPI chip select pin **12** |
| GPS (Adafruit) | `Serial1` |
| XBee radio | `Serial2` @ **115200** baud |
| USB debug serial | `Serial` @ **230400** baud |
| Status LEDs | pins 35, 37, 39 (3-bit setup progress code, all off when setup is complete) |
| Sleep / flag inputs | pins 33 / 22 (input pull-up) |

## Building and uploading

1. Get the code **including the CANApi submodule**:
   ```shell
   git switch ESC-CODE
   git pull origin ESC-CODE
   git submodule update --init
   ```
   If `src/CANApi/` is empty, the build fails because `CanApiv04.hpp` cannot be found.
2. In the Arduino IDE, install these libraries (Library Manager):
   * **Adafruit GPS Library**
   * **ArduinoJson**, version **6.x** (the code uses the v6 `DynamicJsonDocument` API)
   * **SD** (bundled with the IDE)
   * any libraries required by [CANApi](https://github.com/DUEM/CANApi) for the MCP2515 (see its README)
3. Open `Telemetry2021/Telemetry/Telemetry.ino`.
4. Select **Tools → Board → Arduino Mega or Mega 2560**, then the board's port.
5. Connect the board by USB and click **Upload**.
6. Optional: open the Serial Monitor at 230400 baud to see the debug output and a hex copy of every transmitted frame (`LOG_TO_SERIAL` in [SendMessage.cpp](SendMessage.cpp)).

## SD card

Copy [config.txt](config.txt) to the **root** of the SD card. It is JSON, and all times are in milliseconds:

| Key | Meaning | Default if the file can't be read |
|---|---|---|
| `gps_update` | Interval between GPS CAN messages | 2000 |
| `sd_update` | Interval between SD card flushes | 2000 |
| `status_update` | Interval between system status messages | 500 |
| `mppt_update` | Interval between MPPT polls | 1000 |
| `time_fix` | Maximum time to wait for a GPS time fix at start-up | 20000 |
| `serialCanMsg` | Read but currently unused | 1 |
| `spare` | Array of two spare values, read but unused | -1, -1 |

If the file is present, any key missing from it is read as **0**. The current `config.txt` has no `serialCanMsg` or `spare` keys, and its `speedtype`, `mode` and `somevalues` keys are ignored.

Each power-up creates a new log file `YYMMDDNN.bin` (GPS date, plus a counter `NN` from 00 to 99). It uses the same binary frame format as the radio link.

## Radio frame format

```
[millis 4B, little-endian][CAN ID 2B, big-endian][DLC 1B][data, DLC bytes][CRC16 2B, big-endian][0x7E]
```

The CRC is AVR `_crc16_update` with initial value `0xFFFF`, calculated over the millis, CAN ID, DLC and data bytes. `0x7E` is not escaped inside frames. See [SendMessage.cpp](SendMessage.cpp) and [Receiver/README.md](../Receiver/README.md).

## System status message (CAN ID 0x111)

The bytes are, in order: Power, Writing to SD, GPS Time Obtained, Loaded Config, Flag. They use these values:

* `0xFF`: good
* `0xAA`: bad
* `0xBB`: using defaults
* `0x00`: unknown

"Loaded Config" is overwritten with `100 + NN` once the SD log file is opened, or with `90` if the file could not be opened (see [SD.cpp](SD.cpp)).
