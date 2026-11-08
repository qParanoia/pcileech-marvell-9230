

"""Capture stock physical descriptors for basic host write/flush commands."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from emulate_stock import run
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary


def probe(image: bytes, opcode: int, write_bit: bool, prdt_count: int) -> dict:
    host_clb = 0x0000000110000000
    host_ctba = 0x0000000110002000
    host_data = 0x0000000110100000
    flags = 5 | (0x40 if write_bit else 0) | (prdt_count << 16)
    header = struct.pack("<8I", flags, 0, host_ctba & 0xFFFFFFFF,
                         host_ctba >> 32, 0, 0, 0, 0)
    fis = bytearray(20)
    fis[0:3] = bytes((0x27, 0x80, opcode))
    fis[7] = 0x40
    total_bytes = 512 if prdt_count <= 32 else 512 * prdt_count
    fis[12] = (total_bytes // 512) & 0xFF
    fis[13] = (total_bytes // 512) >> 8
    table = bytearray(0x80 + 0x10 * prdt_count)
    table[:20] = fis
    if prdt_count:
        if total_bytes % prdt_count:
            raise ImageError("test PRDT count must divide 512")
        entry_bytes = total_bytes // prdt_count
        for index in range(prdt_count):
            address = host_data + index * entry_bytes
            struct.pack_into("<4I", table, 0x80 + 0x10 * index,
                             address & 0xFFFFFFFF, address >> 32, 0,
                             0x80000000 | (entry_bytes - 1))
    kwargs = ({"synthetic_host_prdt_buffer": (host_data, b"\xA5" * total_bytes)}
              if prdt_count and total_bytes <= 4096 else {})
    received = bytearray(0x100)
    received[0x40:0x54] = bytes((0x34, 0x40, 0x50)) + bytes(17)
    result = run(
        image, 9_000_000, port0_sstatus=0x133, fast_delays=True,
        experimental_sata_io=True,
        synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
        synthetic_host_port_command_issue=1,
        synthetic_frontend_worker_once=True,
        synthetic_backend_task_drain_once=True,
        synthetic_host_command_list=(host_clb, header),
        synthetic_host_command_table=(host_ctba, bytes(table)),
        synthetic_backend_received_fis=bytes(received),
        report_memory_ranges=[(0x80002910, 0x30), (0x30003020, 0x20)],
        **kwargs,
    )
    host_issues = [event for event in result["port0_command_issues"]
                   if event.get("pc") == "0x00004BAC"]
    return {
        "opcode": f"0x{opcode:02X}", "flags": f"0x{flags:08X}",
        "stock_host_issues": [
            {key: event[key] for key in ("ata_command", "slot", "command_slot_raw")}
            for event in host_issues
        ],
        "completions": result["synthetic_completions"],
        "transfers": result["synthetic_host_data_transfers"],
        "host_registers": result["memory_snapshots"],
        "stop_reason": result["stop_reason"],
        "uart_tail": result["uart"][-800:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("expected analyzed stock 88.bin")
        for opcode, write_bit, count in ((0x35, True, 1), (0xEA, False, 0)):
            print(json.dumps(probe(image, opcode, write_bit, count), indent=2))
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
