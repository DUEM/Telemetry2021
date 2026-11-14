# Tools

Standalone Python scripts for working with the telemetry system outside the live receiver. Run them with `python3 tools/<script>.py` from the top of the repository (or `python3 <path to script>` from any directory), with the virtual environment active. File names you give them are relative to the directory you run them from. Every script prints its options with `-h`.

| Script | What it does | Documented in |
|---|---|---|
| [hex2csv.py](hex2csv.py) | Decodes an SD card log (`.BIN`) to a CSV file | [Receiver/README.md](../Receiver/README.md#offline-tools-sd-card-logs) |
| [hex2influx.py](hex2influx.py) | Decodes an SD card log into InfluxDB | [Receiver/README.md](../Receiver/README.md#offline-tools-sd-card-logs) |
| [batch_Read_Hex.py](batch_Read_Hex.py) | Runs `hex2influx.py` on every SD card log in a directory | [Receiver/README.md](../Receiver/README.md#offline-tools-sd-card-logs) |
| [dbc_to_markdown.py](dbc_to_markdown.py) | Regenerates [dbc/SIGNALS.md](../dbc/SIGNALS.md) from the DBC files | [dbc/README.md](../dbc/README.md#how-the-documentation-is-kept-up-to-date) |
| [check_xbee_settings.py](check_xbee_settings.py) | Reads and reports all the settings of an XBee radio | [below](#check_xbee_settingspy) |

## Requirements

* `hex2csv.py`, `hex2influx.py`, `batch_Read_Hex.py` and `dbc_to_markdown.py` use the receiver's packages: `pip install -r Receiver/requirements.txt` (see [Receiver/README.md](../Receiver/README.md)).
* `check_xbee_settings.py` only needs pyserial, which is in the receiver's requirements too. To use it on its own: `pip install -r tools/requirements.txt`.

## check_xbee_settings.py

Connects to an XBee radio on a serial port and lists its settings: firmware and serial number, network (channel, network ID, addresses), RF (power level, data rate, retries, signal strength), serial interface (baud rate, flow control, API mode), sleep and diagnostics (supply voltage, temperature). It also points out any setting that does not suit the telemetry link.

It **only reads** settings. It puts the XBee into AT command mode (`+++`), asks for each setting (e.g. `ATBD`), and leaves command mode (`ATCN`). It never changes or saves a setting, so it is safe to run on a working radio. To change settings, use Digi's XCTU program.

```shell
python3 tools/check_xbee_settings.py                       # the XBee on /dev/ttyUSB0 at 115200 baud
python3 tools/check_xbee_settings.py -p /dev/ttyUSB1       # a different port
python3 tools/check_xbee_settings.py --scan                # also try the other standard baud rates
python3 tools/check_xbee_settings.py --json > xbee.json    # save the settings, e.g. to compare two radios
```

| Option | Meaning |
|---|---|
| `-p`, `--port` | Serial port (default `/dev/ttyUSB0`; on Windows e.g. `COM8`) |
| `-b`, `--baud` | Baud rate (default 115200, as used by the telemetry board and the receiver) |
| `--scan` | If the XBee does not answer at `--baud`, try 9600, 57600 and the other standard rates. Useful for a radio straight from the box (factory setting 9600) |
| `--json` | Print the settings as JSON instead of a table |

Example (shortened):

```text
XBee on /dev/ttyUSB0 at 115200 baud

Identity
  VR  Firmware version                                           10EF
  HV  Hardware version                                           not supported
  SH  Serial number, high 32 bits                                13A200
  SL  Serial number, low 32 bits                                 41B2C3D4
  ...
Serial interface
  BD  Serial baud rate                                           7  (115200 baud)
  AP  API mode                                                   0  (transparent)
  D7  DIO7 / CTS flow control                                    0  (disabled)
  ...
Worth checking
  * D7 is not CTS flow control: if data arrives faster than the radio can send it, the XBee's buffer overflows and data is lost without the board knowing (the telemetry board does not use flow control either).
```

Values are shown as the XBee sends them (hexadecimal), with their meaning in brackets where the tool knows it. XBee families (802.15.4, Zigbee, DigiMesh, 900 MHz, 868 MHz) support different settings; the ones a module does not have are listed as `not supported`. Some settings mean different things on different families: look them up in the module's Digi user guide, using the firmware version (`VR`) and device type (`DD`) to find the right one. For example, the RF data rate `BR` on an XBee-PRO 900HP is 0 = 10 kbps and 1 = 200 kbps.

The "Worth checking" list flags settings that do not match what the telemetry link needs: transparent mode (`AP` = 0), 115200 baud (`BD`), no sleep (`SM` = 0), and CTS flow control (`D7`), which matters because the radio link loses most frames on the car (see Known limitations in the top-level [README](../README.md#known-limitations)).

**Before running it:**

* Nothing else may have the port open: stop `LiveTelemetry.py`, and close XCTU, the Arduino serial monitor and any other serial program.
* The XBee should be in transparent mode (`AP` = 0), as the telemetry radios are. A radio in API mode may not answer `+++`; read it with XCTU instead.
* The receiver's XBee can be read while the car is transmitting: radio data arriving at the same time is ignored. Reading it takes a few seconds, because the XBee needs about 1 s of silence before and after `+++`.
* To read the car's XBee, take it off the telemetry board and connect it to the laptop with an XBee USB adapter.

**If it says "No XBee answered":** check the port (`ls /dev/ttyUSB*`), try `--scan` in case the baud rate is not 115200, and check the XBee is in transparent mode. If it stops part way with "no reply", run it again: the XBee left command mode, which it does by itself after its command mode timeout (`CT`, 10 s by default) without a command.
