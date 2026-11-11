# CAN database (DBC) files

The receiver decodes the vehicle's CAN messages using the `.dbc` files in this directory. They are the single place where the meaning of every message and signal is written down.

**Looking for what a value means, or what to query in Grafana? See the generated [CAN signal reference (SIGNALS.md)](SIGNALS.md).**

| File | Device(s) |
|---|---|
| [Telemetry.dbc](Telemetry.dbc) | The DUSC telemetry board itself: GPS and board status |
| [Orion.dbc](Orion.dbc) | Orion BMS (battery management system) |
| [MPPT.dbc](MPPT.dbc) | The two MPPTs (solar charge controllers), and the telemetry board's requests to them |
| [wavesculptor_22.dbc](wavesculptor_22.dbc) | Tritium WaveSculptor motor controller and the driver controls |

## CAN in a few paragraphs

The devices in the car (battery management system, motor controller, solar charge controllers, telemetry board) are connected by a two-wire network called the **CAN bus**. Each device broadcasts short **messages** onto the bus, and any device can listen.

Each message has:

* a **CAN ID**, a number that says which message it is (e.g. `0x700` is the BMS's battery pack summary). Lower IDs win if two devices send at the same time.
* up to **8 bytes of data**. The number of bytes is the message's **length** (or DLC).

The data bytes hold several **signals**, which are the actual values (e.g. pack voltage, state of charge). A signal can be a single bit (an on/off flag), a few bits, or several bytes.

To save space, devices usually send whole numbers, not decimals. The **scaling** turns this raw number into a real value: *value = raw × scale + offset*. For example, the MPPTs send their input voltage in steps of 0.15049 V, so a raw value of 586 means 586 × 0.15049 = 88.19 V. Some devices (the motor controller, the GPS) send decimal (floating point) numbers directly, which need no scaling.

A **DBC file** is the standard text file that lists, for every message: its CAN ID, name and sender, and for every signal: where it sits in the data bytes, its scaling, its unit and what it means. Every CAN tool can read DBC files.

## Reading a DBC file

A message and one of its signals look like this (from [MPPT.dbc](MPPT.dbc)):

```
BO_ 1905 Javed: 7 Mppt
 SG_ VoltageIn : 1|10@0+ (0.15049,0) [0|153.95127] "V" Vector__XXX
```

| Part | Meaning |
|---|---|
| `BO_ 1905` | A message ("board object") with CAN ID 1905 (`0x771` in hexadecimal) |
| `Javed` | The message name. The receiver stores it as the InfluxDB measurement's **Item** |
| `7` | Length: 7 data bytes |
| `Mppt` | The device that sends it. The receiver stores it as the **Source** |
| `SG_ VoltageIn` | A signal called `VoltageIn`, which becomes the InfluxDB **field** name |
| `1\|10` | It starts at bit 1 and is 10 bits long |
| `@0` | Byte order: `0` = big-endian (Motorola), `1` = little-endian (Intel) |
| `+` | Unsigned (`-` would be signed) |
| `(0.15049,0)` | Scaling: value = raw × 0.15049 + 0 |
| `[0\|153.95127]` | The range of possible values (`[0\|0]` means not set) |
| `"V"` | The unit |
| `Vector__XXX` | Which devices receive it (not used here) |

The descriptions live further down the file:

```
CM_ BO_ 1905 "Status of the MPPT named Javed, ...";
CM_ SG_ 1905 VoltageIn "Voltage from the solar array into this MPPT ...";
VAL_ 1905 NoCharge 0 "No" 1 "Yes" ;
BA_ "GenMsgCycleTime" BO_ 1905 1000;
```

| Line | Meaning |
|---|---|
| `CM_ BU_` / `CM_ BO_` / `CM_ SG_` | A comment (description) for a device, a message or a signal |
| `VAL_` | A value table: what particular values of a signal mean (here 1 means "Yes"). The receiver still stores the number; the table is documentation |
| `BA_ "GenMsgCycleTime"` | How often the message is sent, in milliseconds |
| `SIG_VALTYPE_ ... : 1` | The signal is a 32-bit floating point (decimal) number |

## From the CAN bus to Grafana

Following one value all the way through:

1. The MPPT named Javed sends message `0x771` with the raw value 586 in the `VoltageIn` bits.
2. The telemetry board relays the message over the radio (and logs it to its SD card).
3. The receiver looks up CAN ID `0x771` in the DBC files, finds message `Javed` from device `Mppt`, and decodes `VoltageIn` = 586 × 0.15049 = **88.19 V**.
4. It writes the value to InfluxDB as field `VoltageIn` in measurement `"Mppt/Javed"`, i.e. `<Source>/<Item>`.
5. In Grafana, the query is:
   ```
   SELECT "VoltageIn" FROM "Mppt/Javed" WHERE $timeFilter
   ```
   The double quotes are needed because the measurement name contains `/`.

[SIGNALS.md](SIGNALS.md) gives the measurement name and an example query for every message.

## How the documentation is kept up to date

* The **DBC files** hold all the facts: names, positions, scaling, units, ranges, value tables, how often each message is sent, and a plain-English comment for every device, message and signal.
* **[SIGNALS.md](SIGNALS.md)** is generated from them by [tools/dbc_to_markdown.py](../tools/dbc_to_markdown.py). Never edit it by hand.
* **[Tests/test_dbc_docs.py](../Tests/test_dbc_docs.py)**, run by `pytest` and in GitHub Actions, checks that:
  * SIGNALS.md matches the DBC files
  * every device, message and signal has a comment
  * the number of `TODO` comments only ever goes down (`MAX_TODOS`)
  * value tables do not change the values the receiver stores

Where something is not known yet, the comment says so with **`TODO: add ...`**, naming what is missing and where to find it (e.g. the Orion BMS profile, or the MPPT datasheet). All of them are listed at the end of [SIGNALS.md](SIGNALS.md#still-to-be-documented).

## Changing or adding a message or signal

1. Edit the `.dbc` file, either in a text editor or a DBC editor (e.g. Vector CANdb++, Kvaser Database Editor, or [cantools](https://cantools.readthedocs.io/) from Python). A new message or signal needs a `CM_` comment: describe what it means in plain English, and give the unit, scaling and range.
2. Check the file loads: `python3 -c "import cantools; cantools.database.load_file('dbc/<file>.dbc', strict=True)"`.
3. Regenerate the reference from the top of the repository: `python3 tools/dbc_to_markdown.py`.
4. If you filled in a TODO, lower `MAX_TODOS` in [Tests/test_dbc_docs.py](../Tests/test_dbc_docs.py).
5. Run `pytest`. If you changed scaling or a name that appears in a test capture, update the expected output in `Tests/data/*.csv` (calculate the new expected values from the old ones by hand rather than copying the new output).
6. If the board should forward a new message, check [../Telemetry/UseMsgList.hpp](../Telemetry/UseMsgList.hpp). By default it forwards every message.

**Changes that affect InfluxDB and Grafana.** Message, sender and signal names become InfluxDB measurement and field names, so:

* **Renaming** a message, a sender or a signal starts a new measurement or field. Older data stays under the old name, and Grafana panels using the old name must be updated.
* **Adding scaling** to a signal changes its stored values from that point on (older data stays raw), and usually changes the field from a whole number to a decimal. InfluxDB 1.x **rejects** writes that change a field's type within the same shard (by default, the same week), and the receiver logs them as errors. After changing scaling, either start a new database or drop the old measurement first (`DROP MEASUREMENT "Mppt/Javed"`, which deletes its data).

## Changes made in November 2026

So that you can match older data:

| Change | Before | After |
|---|---|---|
| MPPT `VoltageIn` and `CurrentIn` scaled to V and A | raw (multiply by 0.15049 V and 0.00872 A) | V and A |
| Motor controller status message renamed | `"Tritium/StausInformation"` | `"Tritium/StatusInformation"` |
| Motor controller moved to Ortus-T/Peri's CAN IDs | base address 0x600 (0x600 to 0x617) | base address 0x300 (0x300 to 0x317), same message and signal names |
| Driver controls moved to Ortus-T/Peri's CAN IDs | 0x501, 0x502 | 0x101, 0x102, same names |
| Current dial message added | | `"DriverControls/DialCurrent"` (0x500) |
| Old two-motor set-up removed (`Left_*`, `Right_*`, senders `WaveSculptor20_Right` / `Tritium_Right`, `DriverControls_Right`) | 0x23, 0x41 to 0x43, 0x80 to 0x8E, 0x101 | removed: not on Peri, and 0x080 and 0x101 are used by other devices |
| Orion messages: 8 bytes, with the checksum in byte 7 | 7 bytes | 8 bytes, new `Checksum` field |
| Comments, units, ranges, value tables and message periods added | | see [SIGNALS.md](SIGNALS.md) |

The CAN IDs now match Ortus-T as recorded at iESC 2026 (the qualifying capture, a section of which is [Tests/data/NRT.BIN](../Tests/data/NRT.BIN)). Data recorded from the 2024 car, with its controller at 0x600, no longer decodes with these files: use the DBC files from git history (before these changes) for it.

The Orion BMS signals and the MPPT `VoltageOut` and `AmbientTemperature` are **still raw values**: their scaling has to come from the Orion BMS profile and the MPPT datasheet (see the TODOs).

## CAN IDs seen but not decoded

These appear in the iESC 2026 qualifying capture, but are in no DBC file, so the receiver stores them as `ERROR/ID UNRECOGNISED`. Together they are most of the traffic on Ortus-T's CAN bus.

| ID as received | Data bytes | Period | Notes |
|---|---|---|---|
| 0x080 | 4 | 100 ms | e.g. `06 16 00 a0` |
| 0xF380 | 8 | about 90 ms | e.g. `00 0d 16 13 28 0f 07 b5` |
| 0xFF80 | 8 | 200 ms | e.g. `f3 00 80 f3 00 40 1e 90` |

0xF380 and 0xFF80 are larger than the largest standard (11-bit) CAN ID, 0x7FF. They are almost certainly 29-bit extended IDs: the telemetry board only sends the lowest 16 bits of the ID (see `SendMessage.cpp`), so the rest of the ID is lost. Both end in `80`, which in J1939-style addressing is the sender's address, so they probably come from one device.

TODO: identify the device that sends these (possibly MPPTs, since the MPPT status messages 0x771 and 0x772 are not in the capture). Decoding extended IDs reliably needs the firmware to send the full 29-bit ID, which changes the radio frame format for the receiver too.

## Glossary

| Term | Meaning |
|---|---|
| BMS | Battery management system. Here the Orion BMS: monitors the cells and switches the battery contactors |
| MPPT | Maximum power point tracker: a solar charge controller that gets the most power from part of the solar array and charges the battery |
| Motor controller | The Tritium WaveSculptor: turns battery power into drive for the motor |
| Driver controls | The unit that sends the driver's accelerator and mode commands to the motor controller |
| SOC | State of charge: how full the battery is, in % |
| DCL | Discharge current limit: the most current the BMS allows to be drawn from the battery right now |
| DC bus | The battery-side power connection of the motor controller |
| Back-EMF | The voltage the motor generates as it spins |
| CAN ID | The number identifying a CAN message (often written in hexadecimal, e.g. `0x700` = 1792) |
| DLC | Data length code: the number of data bytes in a CAN message (0 to 8) |
| Signal | One value inside a CAN message |
| Scaling | How to turn a signal's raw number into a real value: raw × scale + offset |
| Big-endian / little-endian | Which order the bytes of a multi-byte value are sent in |
| Measurement / field | InfluxDB's names for a table (one per CAN message here) and a column in it (one per signal) |
| NMEA `ddmm.mmmm` | The GPS's own position format: degrees × 100 + minutes, e.g. 5446.5 = 54° 46.5′ |
