# Telemetry Parser & Storer Refactor - Architecture Documentation

## Overview

This document describes the refactored telemetry system architecture, which decouples message parsing from storage to enable modular, testable, and extensible code.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LiveTelemetry.py                         │
│              (Serial Reader - Entry Point)                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ bytearray (raw CAN message)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              StorerWrapper (Lazy Init)                       │
│         (Backward Compatibility Layer)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ store_data() call
                       ▼
┌─────────────────────────────────────────────────────────────┐
│            TelemetryStorer (Orchestrator)                    │
│       • Parses message using TelemetryParser                │
│       • Routes to all registered StorerExtensions           │
└──────┬──────────────────────────────────────────────────────┘
       │
       ├─────────────────────────────────────────────────────────────────┐
       │                                                                   │
       ▼                                                                   ▼
┌──────────────────────────────┐                        ┌─────────────────────────┐
│   TelemetryParser            │                        │  ReceiverConfig         │
│                              │                        │                         │
│ • Decodes raw bytes          │                        │ • DBC file paths        │
│ • Uses DbcDecoder            │  ◄─────── uses ────►   │ • Output file paths     │
│ • Validates CRC              │                        │ • Influx credentials    │
│ • Manages GPS time sync      │                        │ • CSV output path       │
└──────────┬───────────────────┘                        └─────────────────────────┘
           │
           │ (decoded message tuple)
           │ (msg_item, msg_source, msg_body, msg_time, msg_crc_status)
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│         StorerExtension (Abstract Interface)                │
└─────────────────────────────────────────────────────────────┘
      │                        │                        │
      │                        │                        │
      ▼                        ▼                        ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  ExcelStorer     │  │ Influx1Storer    │  │  CSVStorer       │
│                  │  │                  │  │                  │
│ • openpyxl       │  │ • influxdb-py    │  │ • csv module     │
│ • .xlsx files    │  │ • InfluxDB 1.x   │  │ • .csv files     │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

## Component Responsibilities

### 1. LiveTelemetry.py
**Role**: Serial reader and entry point

- Reads raw bytes from xBee serial connection
- Accumulates bytes into frames (terminated by `\x7E`)
- Calls `store_data(frame)` for each complete frame
- Graceful shutdown on Ctrl+C or exit

**Key Functions**:
- `store_data(bytearray)` - Forwards to StorerWrapper

### 2. StorerWrapper
**Role**: Lazy initialization & backward compatibility

- Initializes `TelemetryStorer` on first call (not at module import)
- Maintains global state for old code patterns (optional - can be refactored out)
- Provides `store_data()` and `end_session()` convenience functions

**Note**: Modern code should instantiate `TelemetryStorer` directly

### 3. TelemetryParser
**Role**: Decode raw CAN messages into structured data

```python
def translate_msg(msg_bytes: bytearray) -> tuple[
    str,                    # msg_item (e.g., "PackParameters")
    str,                    # msg_source (e.g., "Orion")
    dict,                   # msg_body (decoded fields)
    datetime,               # msg_time (GPS-synced timestamp)
    bool                    # msg_crc_status (validation result)
]:
```

**Responsibilities**:
- Extract timestamp from first 4 bytes (millisecond delta)
- Validate CRC of entire message
- Decode CAN ID and message body using DBC files
- Update GPS time when GPS message received
- Handle time overflow (2^32 ms wraparound)

**Dependencies**:
- `DbcDecoder()` - for CAN message decoding
- `ReceiverConfig.dbc_files` - DBC file paths
- `crccheck.crc.Crc16Modbus` - CRC validation

### 4. DbcDecoder
**Role**: Wrapper around cantools for DBC-based decoding

```python
def decode_can_msg(can_id: int, msg_bytes: bytes) -> tuple[
    str,        # message name
    str,        # sender (source)
    dict        # decoded fields
]:
```

**Responsibilities**:
- Load and manage cantools database
- Cache decoded messages by CAN ID
- Return human-readable message names and fields

### 5. TelemetryStorer
**Role**: Orchestration of parsing and multi-storage

```python
def __init__(self, parser: TelemetryParser, 
             storage_plugin_list: List[StorerExtension]):
    self.parser = parser
    self.storage_plugin_list = storage_plugin_list

def store_data(msg: bytearray):
    # 1. Parse message
    item, source, body, time, crc = parser.translate_msg(msg)
    # 2. Send to all registered storers
    for storer in storage_plugin_list:
        storer.store_data(item, source, body, time, crc)

def end_session():
    # Close all storers
    for storer in storage_plugin_list:
        storer.close()
```

**Key Features**:
- Pure dependency injection (list of storers passed in)
- No knowledge of specific storer implementations
- Supports any number of storage backends
- Supports multi-storage (write to Excel + CSV + Influx simultaneously)

### 6. StorerExtension (Abstract Base Class)
**Role**: Interface for storage implementations

```python
class StorerExtension(ABC):
    @abstractmethod
    def store_data(self, msg_item: str, msg_source: str, 
                   msg_body: dict, msg_time: datetime, 
                   msg_crc_status: bool) -> None:
        """Store decoded message data."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close any open resources."""
        pass
```

**Implementations**:

#### ExcelStorer
- Writes to `.xlsx` files using openpyxl
- Auto-creates sheet "Translated Messages"
- Headers: Date, Time, Source, Item, [Data...], CRC
- Appends to existing files with gap separator
- Saves to disk after every message (for durability)

#### Influx1Storer
- Sends to InfluxDB 1.x using influxdb-py library
- Measurement name: `{source}/{item}`
- Fields: all decoded message values
- Skips messages with failed CRC
- Graceful connection handling

#### CSVStorer (NEW)
- Writes to `.csv` files using Python csv module
- Headers: Timestamp, Source, Item, Data (as comma-separated key=value), CRC
- Auto-creates file if missing
- Appends without duplicating headers
- Simple, portable format

### 7. ReceiverConfig
**Role**: Centralized configuration management

```python
# Output file paths (set to "" to disable)
xlsxOutputFile: str = ''        # Excel output
csvOutputFile: str = ''         # CSV output (NEW)

# Influx connection info
class InfluxCredentials(NamedTuple):
    username: str = "admin"
    password: str = "password"
    db: str = "Test22DB"
    host: str = "localhost"
    port: int = 8086
    enabled: bool = True

ifCredentials = InfluxCredentials()

# DBC file paths
dbc_files = [
    "../0/wavesculptor_22.dbc",
    "../0/MPPT.dbc",
    "../0/Telemetry.dbc",
    "../0/Orion.dbc",
]
```

## Data Flow Example

### Message Flow for Battery Pack Status

```
Raw Serial Data:
  [00 00 00 00] [01 05] [08] [00 00 00 50 19 80 5B]
  └─ Time ─┘  └─ ID ─┘ └─┘  └─ Payload ──────────┘

                ↓ (stored as bytearray)

LiveTelemetry.store_data(bytearray(...))
                ↓

StorerWrapper lazy-init → TelemetryStorer instantiated
                ↓

TelemetryParser.translate_msg():
  • Extract time: 00 00 00 00 = 0ms delta
  • Validate CRC: ✓
  • Decode CAN ID: 01 05 = 0x0105 = 261 decimal (Orion PackParameters)
  • Lookup DBC → "Orion", "PackParameters"
  • Decode fields: {
      "PackCurrent": 0,
      "PackInstVoltage": 1305,
      "PackSoc": 159,
      "RelayState": 32843
    }
  • Return (time, msg_item, msg_source, msg_body, crc_status)
                ↓

TelemetryStorer routes to all configured storers:

  ExcelStorer:
    • Opens/creates ExcelOutput/telemetry.xlsx
    • Writes row: [1970-01-01 03:00, Orion, PackParameters, ...]
    • Saves immediately

  CSVStorer (if enabled):
    • Opens/appends Output/telemetry.csv
    • Writes CSV line: [1970-01-01T03:00:00Z, Orion, PackParameters, ...]
    • Flushes buffer

  Influx1Storer (if enabled):
    • Sends to InfluxDB:
      measurement: "Orion/PackParameters"
      fields: {PackCurrent: 0, PackInstVoltage: 1305, ...}
      time: 1970-01-01T03:00:00Z
```

## Design Principles

### 1. **Separation of Concerns**
- Parser knows only about decoding; doesn't know about storage
- Storer knows only about storing; doesn't know about CAN/DBC
- Orchestrator (TelemetryStorer) knows both but couples via interfaces only

### 2. **Dependency Injection**
- Storage backends are passed to TelemetryStorer, not hard-coded
- Enables testing with mock storers
- Enables swapping backends at runtime

### 3. **No Global State** (except backward-compat wrapper)
- TelemetryParser has no module-level globals
- TelemetryStorer has no module-level globals
- Tests can instantiate multiple independent instances

### 4. **Plugin Architecture**
- Custom storers can be added by subclassing StorerExtension
- No modification to core code needed
- Example: CSVStorer added in 2024 without touching parser/storer

### 5. **Extensibility**
- New storage formats: Create StorerExtension subclass
- New message decoders: Create alternative decoder or extend DbcDecoder
- New input sources: Use TelemetryStorer with different source

## Testing Strategy

### Unit Tests
- **test_parser_unit.py**: Time calculation, CRC checks, GPS updates (isolated)
- **test_telemetry_storer.py**: Parser+Storer integration with mocks

### Integration Tests
- **test_hex2csv.py**: Full pipeline with real binary data
- **test_xlsx_storer.py**: Excel output validation
- **test_influx_storer.py**: Influx mock validation
- **test_csv_storer.py**: CSV output validation

### Multi-Storage Tests
- **test_integration_multi_storage.py**: Simultaneous writes to 2+ backends

### Fixtures (fixtures.py)
- Auto-patch config with test DBC files
- Auto-load binary test data (NRT.BIN, MPPT.BIN)
- Auto-clear module cache for isolation

## Migration Notes

### For Receiver Laptop Deployment
TODO: complete this section

### For Custom Storage
See the `StorerExtension` docstring in `storer_extension.py` for how to create a
custom storer, and `CSVStorer` in the same file for a working example.

## Performance Considerations

### Throughput
- Parser: ~1ms per message (depends on DBC complexity)
- ExcelStorer: ~50ms per write (openpyxl save overhead)
- Influx: ~10ms (network dependent)
- CSV: ~5ms (buffered writes)

### Recommendations
- **For high-frequency data**: Use CSV or Influx (avoid Excel saves every msg)
- **For multiple backends**: Consider async writes if latency matters
- **For archival**: Batch writes or use buffered CSV

### Memory
- TelemetryParser: ~500KB (DBC database)
- Message buffer: ~100 bytes (per message)
- ExcelStorer: Workbook cached in memory (~1MB for typical session)
- CSVStorer: Minimal (file handle + writer)
- Influx: Connection pool (~100KB)
