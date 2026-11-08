

"""Check the modeled SSD startup prefix against the owner's UART log."""

from __future__ import annotations

import argparse
from pathlib import Path

from emulate_stock import run
from inspect_image import ImageError


BASELINE = Path(__file__).resolve().parent.parent / "fixtures" / "stock-one-ssd-prefix.uart.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--experimental-sata-io", action="store_true", help="inject synthetic SSD data and SATA command completions")
    args = parser.parse_args()
    try:
        result = run(
            args.image.read_bytes(),
            1_000_000 if not args.experimental_sata_io else 5_000_000,
            port0_sstatus=0x133,
            fast_delays=True,
            experimental_sata_io=args.experimental_sata_io,
        )
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    expected = BASELINE.read_text(encoding="utf-8").splitlines()
    actual = result["uart"].splitlines()
    for index, line in enumerate(expected):
        if index >= len(actual) or actual[index] != line:
            print(f"mismatch at UART line {index + 1}: expected {line!r}")
            print(f"observed: {actual[index] if index < len(actual) else '<missing>'!r}")
            return 1
    identify_issued = any(event["pc"] == "0x00004BAC" for event in result["port0_command_issues"])
    if not identify_issued:
        print("matched UART prefix, but no IDENTIFY command issue observed")
        return 1
    print(f"matched {len(expected)} UART lines through device signature")
    if args.experimental_sata_io:
        tail = actual[len(expected):]
        expected_tail = [
            "the data in local SRAM.(Identify command)",
            "Device detected: ",
            "major version[07f8]",
            "Normal media rotation rate[0001]",
            "data set management[0001]",
            "Device 0 is SSD.",
            "port 0 pmp 0 arrived.",
            "AHCI controller started.",
            "PD0 supports TRIM",
            "DISK0, DDF not found.",
            "Set BGA Buffer to SRAM memory, 0x1000 bytes",
            "raid_init_work_queue, raid_bga_next_handler",
            "device: 0 mapping to vportid:0",
            "port 0 Auto-fetch enable",
            "port 7 Auto-fetch enable",
            "console device: 12 mapping to vportid: 7",
            "Backend device 0 mapping to ch: 0, dev: 0",
            "Console device 12 mapping to ch 1, dev:1",
        ]
        if len(tail) < len(expected_tail):
            print(f"expected {len(expected_tail)} more SSD lines, observed {len(tail)}")
            return 1
        for index, line in enumerate(expected_tail):
            matches = (
                tail[index].startswith(line) and tail[index].endswith(", sig = 00000101")
                if index == 1 else tail[index] == line
            )
            if not matches:
                print(f"mismatch at SSD line {index + 1}: {tail[index]!r}")
                return 1
        if result["irq_vector_visits"] < 2:
            print("synthetic SATA completion did not traverse the stock IRQ vector")
            return 1
        commands = [item["command"] for item in result["synthetic_completions"]]
        if commands != ["0xEC", "0x25", "0x25"]:
            print(f"unexpected synthetic SATA command sequence: {commands}")
            return 1
        print(f"matched {len(expected) + len(expected_tail)} UART checkpoints through backend/host mapping")
        print("IDENTIFY data and SATA completion IRQs are synthetic; READ DMA payload transfer is unmodeled")
    else:
        print("IDENTIFY command issue observed; use --experimental-sata-io to probe completion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
