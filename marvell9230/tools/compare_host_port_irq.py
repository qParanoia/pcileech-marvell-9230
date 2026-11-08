

"""Map stock frontend port-0 IRQ branches with synthetic status bits."""

from __future__ import annotations

import argparse
from pathlib import Path

from emulate_stock import run
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary


CASES = (
    (0x0001, (0x80002900, 0x80002904), "CLB"),
    (0x0002, (0x80002900, 0x80002904), "CLB"),
    (0x0004, (0x80002908, 0x8000290C), "FB"),
    (0x0008, (0x80002908, 0x8000290C), "FB"),
    (0x0040, (0x80002918,), "CMD"),
    (0x1000, (0x8000292C,), "SSTS"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("this comparison requires the analyzed stock 88.bin")
        for status, expected_reads, label in CASES:
            sample = run(
                image, 3_000_000, capture_mmio=True,
                inject_irq_at_pc=0xE8, injected_irq_pending=0x200,
                debug_mmio_writes={0x80003010: status},
            )
            frontend = [event for event in sample["mmio_trace"]
                        if 0x8000 <= int(event["pc"], 16) < 0x8500]
            reads = {int(event["addr"], 16) for event in frontend if event["op"] == "read"}
            ack = [event for event in frontend if event["op"] == "write"
                   and event["addr"] == "0x80003010"]
            if (not sample["debug_irq_injected"] or sample["irq_vector_visits"] < 2 or
                    any(address not in reads for address in expected_reads) or
                    not ack or int(ack[-1]["value"], 16) != status):
                raise ImageError(f"frontend status 0x{status:04X} did not reach {label} branch")
            print(f"port0 IRQ status=0x{status:04X}: ack; read {label} " +
                  ", ".join(f"0x{address:08X}" for address in expected_reads))
        baseline = run(image, 3_000_000, capture_mmio=True)
        auto_fetch = [event for event in baseline["mmio_trace"]
                      if event["op"] == "write" and event["addr"] == "0x8000C044"]
        if not auto_fetch or auto_fetch[-1]["value"] != "0x0000080D":
            raise ImageError("stock console auto-fetch write missing")
        print("auto-fetch control: 0x8000C044 -> 0x0000080D after console port 7")
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
