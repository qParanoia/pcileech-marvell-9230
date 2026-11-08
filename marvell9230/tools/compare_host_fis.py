

"""Inspect stock host response-FIS propagation with a synthetic SSD response."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from emulate_stock import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--opcode", choices=("EC", "EF"), default="EC")
    args = parser.parse_args()
    host_clb = 0x0000000110000000
    host_ctba = 0x0000000110002000
    host_data = 0x0000000110100000
    header = struct.pack("<8I", 0x00010005 if args.opcode == "EC" else 5,
                         0, host_ctba & 0xFFFFFFFF,
                         host_ctba >> 32, 0, 0, 0, 0)
    table = bytearray(0x90)
    table[:20] = bytes((0x27, 0x80, int(args.opcode, 16),
                        0x03 if args.opcode == "EF" else 0)) + bytes(16)
    struct.pack_into("<4I", table, 0x80, host_data & 0xFFFFFFFF,
                     host_data >> 32, 0, 0x800001FF)
    received = bytearray(0x100)
    received[0x20:0x34] = bytes((0x5F, 0x60, 0x58)) + bytes(17)
    received[0x40:0x54] = bytes((0x34, 0x40, 0x50)) + bytes(17)
    result = run(
        args.image.read_bytes(), 9_000_000, capture_mmio=True,
        port0_sstatus=0x133, fast_delays=True, experimental_sata_io=True,
        synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
        synthetic_host_port_command_issue=1,
        synthetic_frontend_worker_once=True,
        synthetic_backend_task_drain_once=True,
        synthetic_host_command_list=(host_clb, header),
        synthetic_host_command_table=(host_ctba, bytes(table)),
        synthetic_host_prdt_buffer=(host_data, b"\xA5" * 512)
        if args.opcode == "EC" else None,
        synthetic_backend_received_fis=bytes(received),
        code_visit_addresses=(0x4720, 0x854C, 0x867C, 0x86C0, 0x86D0),
        report_memory_ranges=[(0x30003000, 0x60), (0x30067000, 0x60),
                              (0x040054FC, 4)],
    )
    print(json.dumps({
        "snapshots": result["frontend_fis_snapshots"],
        "fis_memory": {key: value for key, value in result["memory_snapshots"].items()
                       if key.startswith("0x3000")},
        "host_base_pointer": result["memory_snapshots"].get("0x040054FC"),
        "consumer": result["code_visit_samples"],
        "completions": result["synthetic_completions"],
        "backend_fis_accesses": result["backend_fis_accesses"],
        "host_completion_mmio": [event for event in result["mmio_trace"]
                                 if event["op"] == "write" and
                                 event["addr"] in ("0x8000C984", "0x80002984", "0x8000C084",
                                                    "0x80002910", "0x80002920",
                                                    "0x80002934", "0x80002938")],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
