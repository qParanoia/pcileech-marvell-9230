

"""Run a local experimental image in the same Unicorn fixture as stock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from emulate_stock import run
from inspect_image import ImageError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--steps", type=int, default=20000)
    args = parser.parse_args()
    if not 1 <= args.steps <= 10_000_000:
        parser.error("--steps must be between 1 and 10000000")
    try:
        result = run(args.image.read_bytes(), args.steps, allow_modified_image=True)
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
