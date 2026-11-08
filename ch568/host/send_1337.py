#!/usr/bin/env python3
"""Send command 1337 over USB and wait for the ACK emitted after a SATA FIS."""

import re
import sys
import time

import usb.core
import usb.util


VID = 0x4348
PID = 0x5637
EP_OUT = 0x01
EP_IN = 0x81
ADDRESS_REPLY = re.compile(r"^[0-9A-Fa-f]{8} [0-9A-Fa-f]{8}$")


def main() -> int:
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None:
        print(f"CH568 mailbox {VID:04x}:{PID:04x} not found", file=sys.stderr)
        return 2

    device.set_configuration()
    usb.util.claim_interface(device, 0)
    try:
        device.write(EP_OUT, b"1337\n", timeout=1000)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                response = bytes(device.read(EP_IN, 512, timeout=1000)).decode(
                    "ascii", errors="replace"
                )
            except usb.core.USBTimeoutError:
                continue
            print(response, end="" if response.endswith("\n") else "\n")
            if ADDRESS_REPLY.fullmatch(response.strip()):
                return 0
    finally:
        usb.util.release_interface(device, 0)

    print("timeout waiting for the Marvell ACK; inspect the last USB LOG line", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
