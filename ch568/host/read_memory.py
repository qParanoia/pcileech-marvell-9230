#!/usr/bin/env python3
"""Read 64 bytes at a Marvell runtime address through the CH568 SATA mailbox."""

import argparse
import re
import sys
import time

VID = 0x4348
PID = 0x5637
EP_OUT = 0x01
EP_IN = 0x81
DATA_REPLY = re.compile(r"^DATA ([0-9A-Fa-f]{128})\r?\n?$")


def parse_word(value: str) -> int:
    value = value.removeprefix("0x").removeprefix("0X")
    try:
        result = int(value, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a 32-bit hexadecimal word") from exc
    if not 0 <= result <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("word is outside the 32-bit range")
    return result


def parse_address(value: str) -> int:
    value = value.removeprefix("0x").removeprefix("0X")
    try:
        result = int(value, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a hexadecimal address") from exc
    if not 0 <= result <= 0xFFFFFFFFFFFFFFFF:
        raise argparse.ArgumentTypeError("address is outside the 64-bit range")
    return result



def load_usb_backend():
    """Resolve the pip-installed libusb-1.0 DLL for PyUSB on Windows."""
    import ctypes.util
    import glob
    import os
    import sysconfig

    if ctypes.util.find_library("libusb-1.0"):
        return None
    machine = {
        "AMD64": "x86_64", "ARM64": "arm64", "x86": "x86", "IA64": "*",
    }.get(os.environ.get("PROCESSOR_ARCHITEW6432")
          or os.environ.get("PROCESSOR_ARCHITECTURE"), "*")
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "libusb-1.0.dll"),
        os.path.join(sysconfig.get_paths()["purelib"], "libusb", "_platform",
                     "windows", machine, "libusb-1.0.dll"),
        os.path.join(sysconfig.get_paths()["purelib"], "libusb", "_platform",
                     "windows", "*", "libusb-1.0.dll"),
    ]
    for pattern in candidates:
        for path in sorted(glob.glob(pattern)):
            from usb.backend import libusb1
            return libusb1.get_backend(find_library=lambda name, _p=path: _p)
    print("libusb-1.0.dll not found: run  py -m pip install libusb", file=sys.stderr)
    raise SystemExit(2)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "address", nargs="*",
        help=(
            "one 64-bit hexadecimal address, or the legacy HIGH32 LOW32 pair "
            "(default: 0)"
        ),
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0,
        help="seconds to wait for the Marvell response (default: 30)",
    )
    args = parser.parse_args()

    if len(args.address) > 2:
        parser.error("use one 64-bit address or two HIGH32 LOW32 words")
    try:
        if len(args.address) == 2:
            address_high = parse_word(args.address[0])
            address_low = parse_word(args.address[1])
        else:
            address = parse_address(args.address[0]) if args.address else 0
            address_high = (address >> 32) & 0xFFFFFFFF
            address_low = address & 0xFFFFFFFF
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    try:
        import usb.core
        import usb.util
    except ModuleNotFoundError:
        print("PyUSB is required: py -m pip install pyusb", file=sys.stderr)
        return 2

    device = usb.core.find(idVendor=VID, idProduct=PID, backend=load_usb_backend())
    if device is None:
        print(f"CH568 mailbox {VID:04x}:{PID:04x} not found", file=sys.stderr)
        return 2

    device.set_configuration()
    usb.util.claim_interface(device, 0)
    try:
        request = f"{address_high:08X} {address_low:08X}\n".encode("ascii")
        device.write(EP_OUT, request, timeout=1000)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            try:
                response = bytes(device.read(EP_IN, 512, timeout=1000)).decode(
                    "ascii", errors="replace"
                )
            except usb.core.USBTimeoutError:
                continue
            match = DATA_REPLY.fullmatch(response)
            if match:
                data = bytes.fromhex(match.group(1))
                print(f"{address_high:08X} {address_low:08X}")
                for offset in range(0, len(data), 16):
                    row = data[offset : offset + 16]
                    hex_column = " ".join(f"{value:02X}" for value in row)
                    hex_column = f"{hex_column:<47}"
                    text_column = "".join(chr(value) if 32 <= value < 127 else "." for value in row)
                    print(f"{offset:05X}  {hex_column}  {text_column}")
                return 0
            print(response, end="" if response.endswith("\n") else "\n")
    finally:
        usb.util.release_interface(device, 0)

    print("timeout waiting for 64-byte SATA memory response", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
