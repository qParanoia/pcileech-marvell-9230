

"""Check large scatter/gather descriptors against the stock ARM firmware."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from compare_open_host_descriptor import arm_slot, compile_builder
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary
from probe_host_rw import probe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--toolchain", type=Path,
                        default=Path(__file__).resolve().parent.parent /
                        "build" / "toolchain")
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("expected analyzed stock 88.bin")
        program, entries = compile_builder(args.toolchain.resolve())
        for count in (33, 257):
            stock = probe(image, 0x25, False, count)
            issues = stock["stock_host_issues"]
            if len(issues) != 4 or issues[-1]["ata_command"] != "0x25":
                raise ImageError(f"stock did not forward {count}-entry PRDT")
            fetched = bytearray(32)
            struct.pack_into("<I", fetched, 0, 5 | (count << 16))
            struct.pack_into("<I", fetched, 8, 0x10002000)
            struct.pack_into("<I", fetched, 12, 1)
            fetched[16:19] = b"\x27\x80\x25"
            fetched[23] = 0x40
            fetched[28] = count & 0xFF
            fetched[29] = count >> 8
            status, actual = arm_slot(bytes(fetched), program,
                                      entries["host_build_basic_slot"])
            if status != 0 or actual != bytes.fromhex(issues[-1]["command_slot_raw"]):
                raise ImageError(f"open {count}-entry descriptor differs from stock")
            print(f"{count}-entry PRDT descriptor matches stock backend slot")
        fetched[0:4] = struct.pack("<I", 5 | (258 << 16))
        status, _ = arm_slot(bytes(fetched), program, entries["host_build_basic_slot"])
        if status != 0xFFFFFFFE:
            raise ImageError("258-entry PRDT exceeded deliberate open limit")
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
