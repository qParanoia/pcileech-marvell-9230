

"""Exercise stock AHCI host-control branches with synthetic MMIO + IRQ8."""

from __future__ import annotations

import argparse
from pathlib import Path

from emulate_stock import run
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary


CASES = (
    ("disabled", 0x00000000, ("AHCI mode disabled by host.",)),
    ("enabled", 0x80000000, ("AHCI mode enabled by host.", "free IDE block: 3fe8")),
    ("reset", 0x80000001, ("AHCI host reset started.", "AHCI host reset done.")),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("this comparison requires the analyzed stock 88.bin")
        for label, ghc, expected in CASES:
            sample = run(
                image, 3_000_000,
                capture_mmio=(label == "reset"),
                inject_irq_at_pc=0xE8,
                injected_irq_pending=0x100,
                initial_mmio={0x80002808: 2},
                host_ghc_on_debug_irq=ghc,
                report_memory_ranges=[(0x80002804, 4)],
            )
            lines = sample["uart"].splitlines()
            if (not sample["debug_irq_injected"] or sample["irq_vector_visits"] < 2
                    or any(line not in lines for line in expected)):
                raise ImageError(f"{label}: host branch did not run: {lines[-5:]!r}")
            if label == "reset":
                writes = [event for event in sample["mmio_trace"]
                          if event["op"] == "write" and event["addr"] == "0x80002804"]
                if not writes or writes[-1]["value"] != "0x00000000":
                    raise ImageError("reset branch did not clear GHC")
                if sample["memory_snapshots"]["0x80002804"] != "00000000":
                    raise ImageError("reset branch left GHC set")
            print(f"{label}: GHC=0x{ghc:08X} -> " + " | ".join(expected))
        sequence = run(
            image, 6_000_000,
            synthetic_host_ghc_sequence=(0x00000000, 0x80000000, 0x80000001),
        )
        expected_sequence = [line for _, _, lines in CASES for line in lines]
        observed = [line for line in sequence["uart"].splitlines()
                    if line in expected_sequence]
        if (sequence["synthetic_host_events_delivered"] != 3 or
                observed != expected_sequence or sequence["irq_vector_visits"] != 6):
            raise ImageError(f"host event sequence differs: {observed!r}")
        print("sequence: " + " | ".join(observed))
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print("stock host-control branches reproduced with synthetic register writes and IRQ bit 8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
