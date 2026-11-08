

"""Exercise the stock Option ROM command set as one synthetic host sequence."""

from __future__ import annotations

import struct
from pathlib import Path

from inspect_image import ImageError
from probe_console_packets import probe


def control(subcommand: int, flags: int, address: int = 0) -> bytes:
    request = bytearray(62)
    request[0] = 0xE0
    request[8:12] = bytes((0xE1, 0x10, subcommand, flags))
    request[12:16] = address.to_bytes(4, "little")
    return bytes(request)


def build_packets() -> tuple[tuple[str, int, bytes, int, bytes], ...]:
    version = bytearray(control(9, 0))
    version[12:17] = bytes((1, 0, 0, 0xF4, 3))
    time_request = bytearray(99)
    time_request[0] = 0xE0
    time_request[8] = 0xFD
    time_request[0x38:0x3C] = (0x25).to_bytes(4, "little")
    time_request[0x3C] = 0xA4
    time_request[0x4C:0x4E] = (0x10).to_bytes(2, "little")
    time_request[0x56:0x58] = (0x6AC6).to_bytes(2, "little")
    time_request[0x58:0x5A] = (0xBD8B).to_bytes(2, "little")
    disk_query = bytearray(591)
    disk_query[0] = 0xE0
    disk_query[8:10] = bytes((0xF3, 3))
    disk_query[0x17] = 1
    disk_query[0x38:0x3C] = (0x211).to_bytes(4, "little")
    disk_query[0x3D] = 2
    disk_query[0x40:0x44] = (1).to_bytes(4, "little")
    return (
        ("version", 0x1D, bytes(version), 62, b""),
        ("time", 0x1D, bytes(time_request), 99, b""),
        ("host-address", 0x1D, control(7, 0, 0x9C000), 62, b""),
        ("physical-disk", 0x1D, bytes(disk_query), 591, b""),
        ("physical-reply", 0x1C, b"\xA5" * 591, 591, b"\x1C\x00\xE1"),
        ("bga-host-memory", 0x1D, control(6, 0, 0xA0000), 62, b""),
        ("ui-entry", 0x1D, control(3, 1, 0x9C000), 62, b""),
        ("ui-update", 0x1D, control(1, 1), 62, b""),
        ("ui-release", 0x1D, control(3, 0, 0x9C000), 62, b""),
    )


def main() -> None:
    image = (Path(__file__).resolve().parents[2] / "88.bin").read_bytes()
    packets = build_packets()
    first = packets[0]
    result = probe(
        image, first[1], first[2], first[3], ssd=True, cdb=first[4],
        followups=tuple((opcode, request, length, cdb)
                        for _, opcode, request, length, cdb in packets[1:]),
        max_steps=4_000_000,
    )
    snapshots = result["synthetic_stock_host_followup_snapshots"]
    if result["synthetic_stock_host_followups_delivered"] != len(packets) - 1:
        raise ImageError("not all synthetic Option ROM commands were delivered")
    for packet, snapshot in zip(packets[:-1], snapshots):
        reply = bytes.fromhex(snapshot["reply"])
        if reply[0] != 0xE1 or reply[0x18] != 0:
            raise ImageError(f"stock {packet[0]} command did not succeed")
        print(f"{packet[0]}: marker={reply[0]:02X} status={reply[0x18]:02X}")
    physical_reply = bytes.fromhex(snapshots[4]["host_data"])
    physical_management = bytes.fromhex(snapshots[3]["reply"])
    if physical_reply[:591] != physical_management[:591]:
        raise ImageError("F3/03 response was not delivered by CDB 1C")
    final_reply = bytes.fromhex(result["memory_snapshots"]["0x30065468"])
    if final_reply[0] != 0xE1 or final_reply[0x18] != 0:
        raise ImageError("stock UI release did not succeed")
    print(f"{packets[-1][0]}: marker={final_reply[0]:02X} status={final_reply[0x18]:02X}")
    port = bytes.fromhex(result["memory_snapshots"]["0x80002C80"])
    if struct.unpack_from("<I", port, 0x38)[0] & 1:
        raise ImageError("final host command was not retired")
    if result["code_visits"]["0x3007EA20"] != 6:
        raise ImageError("unexpected BIOS UI callback count")
    if not all(text in result["uart"] for text in (
            "BIOS ver from option rom : 1 0 0 3f4",
            "BIOS_UI set_host_address",
            "Set BGA Buffer to HOST memory",
            "BIOS UI entered.",
            "To release ui memory 30073000 50816 bytes")):
        raise ImageError("stock UI sequence omitted a required side effect")
    if result["stop_reason"] != "instruction limit" or result["last_pc"] != "0x000000E8":
        raise ImageError(f"stock sequence stopped unexpectedly: {result['stop_reason']}")
    print("callback visits:", result["code_visits"]["0x3007EA20"])
    print("result: all host commands retired; CPU idle")
    print("UART tail:")
    print(result["uart"][-500:])


if __name__ == "__main__":
    main()
