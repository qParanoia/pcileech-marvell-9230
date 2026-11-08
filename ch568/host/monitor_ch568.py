#!/usr/bin/env python3
"""Passively print CH568 USB diagnostic logs without queuing SATA commands."""

import sys

import usb.core
import usb.util


VID = 0x4348
PID = 0x5637
EP_IN = 0x81


def main() -> int:
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None:
        print(f"CH568 mailbox {VID:04x}:{PID:04x} not found", file=sys.stderr)
        return 2

    device.set_configuration()
    usb.util.claim_interface(device, 0)
    try:
        print("Listening for CH568 logs; Ctrl+C to stop.", flush=True)
        while True:
            try:
                response = bytes(device.read(EP_IN, 512, timeout=1000)).decode(
                    "ascii", errors="replace"
                )
            except usb.core.USBTimeoutError:
                continue
            print(response, end="" if response.endswith("\n") else "\n", flush=True)
    except KeyboardInterrupt:
        return 0
    finally:
        usb.util.release_interface(device, 0)


if __name__ == "__main__":
    raise SystemExit(main())
