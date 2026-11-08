

"""Check the stock BIOS-UI entry path in the synthetic Unicorn fixture."""

from __future__ import annotations

import struct
from pathlib import Path

from inspect_image import ImageError
from probe_console_packets import probe


def main() -> None:
    image = (Path(__file__).resolve().parents[2] / "88.bin").read_bytes()
    request = bytearray(62)
    request[0] = 0xE0
    request[8:12] = bytes((0xE1, 0x10, 0x03, 0x01))
    request[12:16] = (0x0009C000).to_bytes(4, "little")
    result = probe(image, 0x1D, request, 62, ssd=True,
                   watch_ram_writes=(0x04000234,))
    if result["stop_reason"] != "instruction limit":
        raise ImageError(f"stock UI fixture stopped: {result['stop_reason']}")
    if "BIOS UI entered." not in result["uart"]:
        raise ImageError("stock UI callback did not reach its entry log")
    reply = bytes.fromhex(result["memory_snapshots"]["0x30065468"])
    if reply[0] != 0xE1 or reply[0x18] != 0:
        raise ImageError("stock UI entry did not return a successful reply")
    globals_ = bytes.fromhex(result["memory_snapshots"]["0x04000230"])
    resource_base = struct.unpack_from("<I", globals_, 4)[0]
    if not 0x30040000 <= resource_base < 0x30073000:
        raise ImageError(f"stock UI resource base was corrupted: {resource_base:08X}")
    if any(event["value"] == "0x0000000A"
           for event in result["watched_ram_writes"]):
        raise ImageError("frontend stack overlapped the UI resource pointer")
    port = bytes.fromhex(result["memory_snapshots"]["0x80002C80"])
    if struct.unpack_from("<I", port, 0x38)[0] & 1:
        raise ImageError("stock UI entry left the host command in slot zero")
    print("stock E1/10/03: BIOS UI entered, status 00, host slot retired")
    print(f"resource base: 0x{resource_base:08X}")


if __name__ == "__main__":
    main()
