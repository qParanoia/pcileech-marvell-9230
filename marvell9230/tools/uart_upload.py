

"""Upload a checked ARM payload to the resident 88SE9230 UART monitor."""

from __future__ import annotations

import argparse
import sys
import time
import zlib
from pathlib import Path


def wait_line(port: object, expected: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    line = bytearray()
    while time.monotonic() < deadline:
        byte = port.read(1)
        if not byte:
            continue
        if byte == b"\n":
            message = line.decode("ascii", errors="replace").strip("\r")
            print(message, flush=True)
            if expected in message:
                return
            if message.startswith("ERR ") or message == "UPLOAD_BAD_CRC":
                raise RuntimeError(f"monitor refused command: {message}")
            line.clear()
        elif len(line) < 512:
            line.extend(byte)
        else:
            line.clear()
    raise TimeoutError(f"timed out waiting for {expected!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Windows COM port, e.g. COM4")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--no-execute", action="store_true")
    args = parser.parse_args()
    try:
        import serial
    except ImportError:
        parser.exit(2, "install pyserial: py -m pip install -r requirements-uart.txt\n")
    try:
        data = args.image.read_bytes()
        if not 4 <= len(data) <= 0x10000 or len(data) & 3:
            raise ValueError("payload size must be a multiple of four in [4, 65536]")
        crc = zlib.crc32(data)
        print(f"payload bytes={len(data)} CRC32={crc:08X}", flush=True)
        with serial.Serial(args.port, args.baud, timeout=0.25, write_timeout=args.timeout) as port:


            port.write(b"?\n")
            wait_line(port, "COMMANDS ?", args.timeout)
            port.write(f"U{len(data):08X}{crc:08X}\n".encode("ascii"))
            wait_line(port, f"UPLOAD_READY {len(data):08X}", args.timeout)
            for offset in range(0, len(data), 512):
                port.write(data[offset:offset + 512])
            port.flush()
            wait_line(port, "UPLOAD_OK", args.timeout)
            if not args.no_execute:
                port.write(b"X\n")
                wait_line(port, "EXEC_RETURN", args.timeout)
    except (OSError, RuntimeError, TimeoutError, ValueError, serial.SerialException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
