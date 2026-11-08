

"""Compare a bounded stock-firmware emulation with the owner's UART capture."""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path

from emulate_stock import run


ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "fixtures" / "stock-no-disk.uart.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--steps", type=int, default=2000000)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be positive")
    observed = BASELINE.read_text(encoding="utf-8").splitlines()
    emulated = run(args.image.read_bytes(), args.steps)["uart"].splitlines()
    matcher = difflib.SequenceMatcher(None, observed, emulated, autojunk=False)
    equal = sum(i2 - i1 for kind, i1, i2, _, _ in matcher.get_opcodes() if kind == "equal")
    print(f"matching UART lines: {equal}/{len(observed)}")
    for kind, i1, i2, j1, j2 in matcher.get_opcodes():
        if kind == "equal":
            continue
        print(f"{kind}: board lines {i1 + 1}-{i2}, emulator lines {j1 + 1}-{j2}")
        for line in observed[i1:i2]:
            print(f"  board: {line}")
        for line in emulated[j1:j2]:
            print(f"  model: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
