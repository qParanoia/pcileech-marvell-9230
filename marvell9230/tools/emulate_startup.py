

"""Verify the open ARM stage, UART, IRQ vector, and IRQ return offline."""

from __future__ import annotations

import argparse
from pathlib import Path

from arm_assemble import assemble_arm
from emulate_stock import run
from image_builder import replace_code1_entry
from inspect_image import ImageError


SOURCE = Path(__file__).resolve().parent.parent / "firmware" / "startup.s"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    args = parser.parse_args()
    try:
        payload = assemble_arm(SOURCE)
        idle = payload.find(bytes.fromhex("feffffea"))
        if idle < 0 or idle % 4:
            raise ImageError("open stage idle loop not found")
        image, _ = replace_code1_entry(args.template.read_bytes(), payload)
        result = run(
            image,
            20000,
            allow_modified_image=True,
            inject_irq_at_pc=idle,
            injected_irq_pending=0xA5,
            code_limit=len(payload),
        )
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    expected_uart = "OPEN9230 STAGE0\r\nCHIP=92301B4B\r\n"
    expected_markers = {
        "boot": "0x9230C001",
        "irq_count": 1,
        "irq_last": "0x000000A5",
    }
    if result["uart"] != expected_uart:
        print(f"unexpected UART: {result['uart']!r}")
        return 1
    if any(result["stage_markers"][key] != value for key, value in expected_markers.items()):
        print(f"unexpected IRQ markers: {result['stage_markers']!r}")
        return 1
    if result["last_pc"] != f"0x{idle:08X}" or result["sp"] != "0x04004000":
        print(f"IRQ did not return to the idle loop: {result['last_pc']}, SP={result['sp']}")
        return 1
    print(result["uart"], end="")
    print("open stage: UART, IRQ vector, counter, and return verified offline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
