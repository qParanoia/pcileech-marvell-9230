

"""Build a local UART/MMIO diagnostic for the verified 88SE9230 image."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from arm_assemble import assemble_arm
from image_builder import replace_code1_entry
from inspect_image import ImageError


SOURCE_PATH = Path(__file__).resolve().parent.parent / "firmware" / "mmio_diag.s"


def assemble_diag() -> bytes:
    return assemble_arm(SOURCE_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.template.resolve() == args.output.resolve():
        parser.error("output must differ from template")
    try:
        payload = assemble_diag()
        image, start = replace_code1_entry(args.template.read_bytes(), payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(image)
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"output: {args.output.resolve()}")
    print(f"diagnostic: {len(payload)} bytes at SPI 0x{start:x}")
    print("UART: OPEN9230 DIAG, CHIP=, STRAP=, SPI0= (hex values)")
    print(f"SHA-256: {hashlib.sha256(image).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
