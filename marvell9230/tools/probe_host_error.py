

"""Capture stock host-visible state after one synthetic backend ATA failure."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from emulate_stock import run
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("expected analyzed stock 88.bin")
        clb, ctba, data = 0x110000000, 0x110002000, 0x110100000
        header = struct.pack("<4I", 0x10005, 0, ctba & 0xFFFFFFFF, ctba >> 32)
        fis = bytes((0x27, 0x80, 0x25, 0, 0, 0, 0, 0x40,
                     0, 0, 0, 0, 1, 0, 0, 0))
        table = bytearray(0x90)
        table[:16] = fis
        struct.pack_into("<4I", table, 0x80, data & 0xFFFFFFFF,
                         data >> 32, 0, 0x800001FF)
        result = run(
            image, 9_000_000, port0_sstatus=0x133, fast_delays=True,
            experimental_sata_io=True,
            synthetic_sata_error_on_completion_index=3,
            synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
            synthetic_host_port_command_issue=1,
            synthetic_frontend_worker_once=True,
            synthetic_backend_task_drain_once=True,
            synthetic_host_command_list=(clb, header),
            synthetic_host_command_table=(ctba, bytes(table)),
            synthetic_host_prdt_buffer=(data, b"\xA5" * 512),
            report_memory_ranges=[(0x80002910, 0x30), (0x30003020, 0x20),
                                  (0x8000A910, 0x30)],
        )
        print(json.dumps({
            "issues": [e["ata_command"] for e in result["port0_command_issues"]
                       if e.get("pc") == "0x00004BAC"],
            "completions": result["synthetic_completions"],
            "host_memory": result["memory_snapshots"],
            "frontend_fis_snapshots": result["frontend_fis_snapshots"],
            "uart_tail": result["uart"][-600:],
        }, indent=2))
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
