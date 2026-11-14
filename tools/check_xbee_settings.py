"""Read and report all the settings of an XBee radio on a serial port.

Puts the XBee into AT command mode (+++), asks it for each setting it knows,
prints them, and leaves command mode (ATCN). It only reads settings: it never
sends a command that changes or saves one (no WR, RE, FR or ATxx<value>).

The XBee must be in transparent mode (AP = 0), as the telemetry radios are.
XBee families support different commands; ones a module does not support are
listed as "not supported". Works with the radio on the telemetry laptop
(/dev/ttyUSB0) or, through a USB serial adapter, the one from the car.

Run it as a script, from any directory, with nothing else using the port
(stop LiveTelemetry, close XCTU and serial monitors).

usage:
    `python3 tools/check_xbee_settings.py [-h] [-p PORT] [-b BAUD] [--scan] [--json]`
example (from the top of the repository):
    `python3 tools/check_xbee_settings.py -p /dev/ttyUSB0 -b 115200`
"""

import argparse
import json
import re
import sys
import time

import serial

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200  # as used by the telemetry board and LiveTelemetry.py
SCAN_BAUDS = [115200, 9600, 57600, 38400, 19200, 230400, 4800, 2400, 1200]
GUARD_TIME = 1.1  # s of silence either side of +++ (XBee default GT = 1 s)
RESPONSE_TIMEOUT = 1.5  # s to wait for each reply

# (command, description, decoder name). Grouped as they are printed.
SETTINGS = {
    "Identity": [
        ("VR", "Firmware version", "hex"),
        ("HV", "Hardware version", "hex"),
        ("HS", "Hardware series", "hex"),
        ("DD", "Device type identifier", "hex"),
        ("SH", "Serial number, high 32 bits", "hex"),
        ("SL", "Serial number, low 32 bits", "hex"),
        ("NI", "Node identifier (name)", "text"),
        ("CK", "Configuration checksum", "hex"),
    ],
    "Network and addressing": [
        ("CH", "Operating channel", "hex"),
        ("ID", "Network (PAN) ID", "hex"),
        ("OP", "Operating extended PAN ID (Zigbee)", "hex"),
        ("OI", "Operating 16-bit PAN ID (Zigbee)", "hex"),
        ("MY", "16-bit source address", "hex"),
        ("DH", "Destination address, high 32 bits", "hex"),
        ("DL", "Destination address, low 32 bits", "hex"),
        ("CE", "Coordinator enable / routing mode", "hex"),
        ("A1", "End device association options (802.15.4)", "hex"),
        ("A2", "Coordinator association options (802.15.4)", "hex"),
        ("AI", "Association indication (0 = joined / OK)", "hex"),
        ("SC", "Scan channels bitmask", "hex"),
        ("SD", "Scan duration", "hex"),
        ("ZS", "Zigbee stack profile", "hex"),
        ("NJ", "Node join time", "hex"),
        ("MM", "MAC mode (802.15.4)", "hex"),
        ("HP", "Preamble ID (900 MHz / 868 MHz)", "hex"),
        ("CM", "Channel mask (900 MHz / 868 MHz)", "hex"),
        ("TO", "Transmit options", "hex"),
        ("MT", "Broadcast multi-transmits", "hex"),
        ("RR", "Unicast retries", "hex"),
        ("NH", "Maximum network hops", "hex"),
        ("BH", "Broadcast hops", "hex"),
        ("NP", "Maximum RF payload (bytes)", "int"),
        ("EE", "Encryption enable", "hex"),
    ],
    "RF": [
        ("PL", "Transmit power level (0 = lowest, 4 = highest)", "hex"),
        ("PM", "Power mode / boost", "hex"),
        ("BR", "RF data rate (meaning depends on the model)", "hex"),
        ("CA", "CCA threshold", "hex"),
        ("DB", "RSSI of the last packet received", "dbm"),
        ("EA", "ACK failures count", "int"),
        ("EC", "CCA failures count", "int"),
        ("ER", "Received packets with errors", "int"),
        ("GD", "Good packets received", "int"),
        ("TR", "Transmission failures", "int"),
    ],
    "Serial interface": [
        ("BD", "Serial baud rate", "baud"),
        ("NB", "Parity", "parity"),
        ("SB", "Stop bits", "hex"),
        ("RO", "Packetization timeout (character times)", "int"),
        ("FT", "Flow control threshold (bytes)", "int"),
        ("AP", "API mode", "api"),
        ("AO", "API options", "hex"),
        ("D6", "DIO6 / RTS flow control", "d6"),
        ("D7", "DIO7 / CTS flow control", "d7"),
    ],
    "Sleep": [
        ("SM", "Sleep mode (0 = no sleep)", "hex"),
        ("SP", "Cyclic sleep period", "hex"),
        ("ST", "Time before sleep", "hex"),
        ("SN", "Number of sleep periods", "hex"),
        ("SO", "Sleep options", "hex"),
    ],
    "Command mode": [
        ("CT", "Command mode timeout (x 100 ms)", "hex"),
        ("GT", "Guard time (ms)", "int"),
        ("CC", "Command sequence character", "char"),
    ],
    "Diagnostics": [
        ("%V", "Supply voltage", "mv"),
        ("TP", "Module temperature", "temp"),
    ],
}

BAUD_CODES = {0: 1200, 1: 2400, 2: 4800, 3: 9600, 4: 19200, 5: 38400, 6: 57600, 7: 115200, 8: 230400}
DECODERS = {
    "hex": lambda v: None,
    "text": lambda v: None,
    "int": lambda v: str(int(v, 16)),
    "dbm": lambda v: f"-{int(v, 16)} dBm",
    "mv": lambda v: f"{int(v, 16) / 1000:.2f} V",
    "temp": lambda v: f"{(int(v, 16) ^ 0x8000) - 0x8000} °C",  # 16-bit two's complement
    "char": lambda v: repr(chr(int(v, 16))),
    "baud": lambda v: f"{BAUD_CODES[int(v, 16)]} baud" if int(v, 16) in BAUD_CODES else f"{int(v, 16)} baud",
    "parity": lambda v: {0: "none", 1: "even", 2: "odd", 3: "mark", 4: "space"}.get(int(v, 16)),
    "api": lambda v: {0: "transparent", 1: "API", 2: "API with escaping"}.get(int(v, 16)),
    "d6": lambda v: {0: "disabled", 1: "RTS flow control", 3: "digital input",
                     4: "digital output low", 5: "digital output high"}.get(int(v, 16)),
    "d7": lambda v: {0: "disabled", 1: "CTS flow control", 3: "digital input",
                     4: "digital output low", 5: "digital output high",
                     6: "RS-485 enable low", 7: "RS-485 enable high"}.get(int(v, 16)),
}


class XBeeError(Exception):
    pass


class XBee:
    """AT command mode access to an XBee on an open serial port."""

    def __init__(self, port, guard_time=GUARD_TIME, timeout=RESPONSE_TIMEOUT):
        self.port, self.guard_time, self.timeout = port, guard_time, timeout
        self.port.timeout = timeout

    def enter_command_mode(self) -> bool:
        """Send +++ with the guard times; True if the XBee answers OK.

        Data received over the radio may arrive before the OK, so look for OK
        at the end of whatever comes back.
        """
        time.sleep(self.guard_time)
        self.port.reset_input_buffer()
        self.port.write(b"+++")
        self.port.flush()
        time.sleep(self.guard_time)
        received = bytearray()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            received += self.port.read(self.port.in_waiting or 1)
            if received.endswith(b"OK\r"):
                return True
        return False

    def command(self, cmd: str):
        """Send AT<cmd>; return the reply text, or None if the module does not support it."""
        self.port.reset_input_buffer()
        self.port.write(f"AT{cmd}\r".encode("ascii"))
        raw = self.port.read_until(b"\r")
        if not raw.endswith(b"\r"):
            raise XBeeError(f"no reply to AT{cmd}: the XBee may have left command mode")
        # Replies are printable ASCII. Radio data from the car arriving just
        # before a reply is binary: keep only the printable text before the \r.
        reply = re.split(rb"[^\x20-\x7e]", raw[:-1])[-1].decode("ascii").strip()
        if reply == "":
            raise XBeeError(f"no reply to AT{cmd}: the XBee may have left command mode")
        return None if reply == "ERROR" else reply

    def exit_command_mode(self):
        self.port.write(b"ATCN\r")
        self.port.read_until(b"\r")

    def read_settings(self) -> dict:
        """{group: [(command, description, raw value or None, meaning or None)]}"""
        result = {}
        for group, settings in SETTINGS.items():
            rows = []
            for cmd, description, decoder in settings:
                raw = self.command(cmd)
                meaning = None
                if raw is not None:
                    try:
                        meaning = DECODERS[decoder](raw)
                    except (ValueError, KeyError):
                        meaning = None
                rows.append((cmd, description, raw, meaning))
            result[group] = rows
        return result


def hints(settings: dict) -> list:
    """Points worth checking for the telemetry link, from the settings read."""
    value = {cmd: raw for rows in settings.values() for cmd, _, raw, _ in rows}
    out = []
    if value.get("AP") not in (None, "0"):
        out.append("AP is not 0: the telemetry link expects transparent mode.")
    bd = value.get("BD")
    if bd is not None and int(bd, 16) not in (7, 115200):
        out.append("BD is not 115200 baud, the rate the telemetry board and LiveTelemetry.py use.")
    if value.get("D7") not in (None, "1"):
        out.append("D7 is not CTS flow control: if data arrives faster than the radio can send it, "
                   "the XBee's buffer overflows and data is lost without the board knowing "
                   "(the telemetry board does not use flow control either).")
    if value.get("SM") not in (None, "0"):
        out.append("SM is not 0: the XBee may sleep and miss data.")
    return out


def find_xbee(port_name, bauds, open_port=serial.Serial):
    """Open the port at each baud rate in turn until the XBee answers +++.

    Returns (XBee in command mode, baud), or (None, None).
    """
    for baud in bauds:
        port = open_port(port_name, baud)
        xbee = XBee(port)
        if xbee.enter_command_mode():
            return xbee, baud
        port.close()
    return None, None


def report(settings: dict, port_name: str, baud: int) -> str:
    lines = [f"XBee on {port_name} at {baud} baud", ""]
    for group, rows in settings.items():
        lines.append(group)
        for cmd, description, raw, meaning in rows:
            shown = "not supported" if raw is None else raw + (f"  ({meaning})" if meaning else "")
            lines.append(f"  {cmd:3} {description:58} {shown}")
        lines.append("")
    found = hints(settings)
    if found:
        lines.append("Worth checking")
        lines += [f"  * {h}" for h in found]
    return "\n".join(lines)


def main(argv=None, open_port=serial.Serial) -> int:
    parser = argparse.ArgumentParser(description="Report all the settings of an XBee radio")
    parser.add_argument("-p", "--port", default=DEFAULT_PORT, help=f"serial port (default {DEFAULT_PORT})")
    parser.add_argument("-b", "--baud", type=int, default=DEFAULT_BAUD,
                        help=f"serial baud rate (default {DEFAULT_BAUD})")
    parser.add_argument("--scan", action="store_true",
                        help="if the XBee does not answer at --baud, try the other standard rates")
    parser.add_argument("--json", action="store_true", help="print the settings as JSON")
    args = parser.parse_args(argv)

    bauds = [args.baud] + ([b for b in SCAN_BAUDS if b != args.baud] if args.scan else [])
    try:
        xbee, baud = find_xbee(args.port, bauds, open_port)
    except serial.SerialException as e:
        print(f"Could not open {args.port}: {e}", file=sys.stderr)
        return 2
    if xbee is None:
        print(f"No XBee answered on {args.port} at {', '.join(map(str, bauds))} baud. "
              "Check the port, try --scan, and check the XBee is in transparent mode (AP = 0).",
              file=sys.stderr)
        return 1
    try:
        settings = xbee.read_settings()
    except XBeeError as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        xbee.exit_command_mode()
        xbee.port.close()

    if args.json:
        print(json.dumps({"port": args.port, "baud": baud, "settings": {
            group: [{"command": c, "description": d, "raw": r, "meaning": m} for c, d, r, m in rows]
            for group, rows in settings.items()}}, indent=2, ensure_ascii=False))
    else:
        print(report(settings, args.port, baud))
    return 0


if __name__ == "__main__":
    sys.exit(main())
