#!/usr/bin/env python3
"""Run the 1337 SATA mailbox test, then read 64 bytes at address zero."""

import subprocess
import sys
from pathlib import Path


HOST_DIR = Path(__file__).resolve().parent


def run(script: str, *args: str) -> int:
    command = [sys.executable, str(HOST_DIR / script), *args]
    print(f"\n>>> {' '.join(command)}", flush=True)
    return subprocess.run(command, check=False).returncode


def main() -> int:
    result = run("send_1337.py")
    if result:
        print("1337 test failed; memory read was not started.", file=sys.stderr)
        return result

    # No address arguments means HIGH32=00000000, LOW32=00000000.
    return run("read_memory.py")


if __name__ == "__main__":
    raise SystemExit(main())
