

"""Verify the one-shot, command-free board diagnostic in Unicorn."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from build_c_stage import ROOT, compile_stage
from emulate_stock import run
from image_builder import replace_code1_entry
from inspect_image import ImageError


def require_log(result: dict, expected: tuple[str, ...], forbidden: tuple[str, ...] = ()) -> None:
    log = result["uart"]
    if any(line not in log for line in expected) or any(line in log for line in forbidden):
        raise ImageError(f"unexpected static UART output: {log[-1200:]!r}")
    if result["stop_reason"] != "instruction limit":
        raise ImageError(f"static stage stopped: {result['stop_reason']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("--toolchain", type=Path, default=ROOT / "build" / "toolchain")
    args = parser.parse_args()
    try:
        payload, symbols = compile_stage(
            args.toolchain.resolve(), ROOT / "build" / "c-stage-static-test-emulator",
            cflags=("-DOPEN9230_STATIC_BOARD_TEST=1", "-DSTATIC_TEST_POLL_BUDGET=128u"),
        )
        image, _ = replace_code1_entry(args.template.read_bytes(), payload)
        no_disk = run(image, 45000, allow_modified_image=True, code_limit=len(payload))
        require_log(no_disk, ("OPEN9230 STATIC V2", "HOST_RESET_PORTS=00000008",
                              "HOST_POST_INIT", "HOST_RESULT=NOT_READY",
                              "STATIC_TEST_END"),
                    ("MONITOR READY", "HOST_IDENTIFY_EVENT="))
        if no_disk["port0_command_issues"]:
            raise ImageError("static no-disk run issued a physical SATA command")

        host_clb = 0x0000000110000000
        host_ctba = 0x0000000110002000
        host_data_address = 0x0000000110100000
        header = struct.pack("<4I", 0x00010005, 0, host_ctba & 0xFFFFFFFF,
                             host_ctba >> 32)
        fis = bytes((0x27, 0x80, 0xEC, 0, 0, 0, 0, 0,
                     0, 0, 0, 0, 0, 0, 1, 0))
        table = bytearray(0x90)
        table[:16] = fis
        struct.pack_into("<4I", table, 0x80, host_data_address & 0xFFFFFFFF,
                         host_data_address >> 32, 0, 0x800001FF)
        common = dict(
            allow_modified_image=True, port0_sstatus=0x133,
            experimental_sata_io=True, synthetic_sata_polling=True,
            synthetic_irq_on_completion_index=2,
            synthetic_sata_idle_pc=symbols["stage_poll_marker"],
            code_limit=len(payload),
        )
        no_host_issue = run(image, 500000, **common)
        require_log(no_host_issue, ("P0_IRQTEST_IRQ PENDING=", "HOST_AUTOFETCH_INIT=0000001D",
                                    "HOST_RESULT=NOT_READY",
                                    "STATIC_TEST_END"),
                    ("MONITOR READY", "HOST_IDENTIFY_EVENT="))
        host_issue = run(
            image, 500000, capture_mmio=True, **common,
            synthetic_open_autofetch_at_enable=True,
            synthetic_host_command_list=(host_clb, header),
            synthetic_host_command_table=(host_ctba, bytes(table)),
            synthetic_host_prdt_buffer=(host_data_address, b"\xA5" * 512),
            initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                          0x80002900: host_clb & 0xFFFFFFFF,
                          0x80002904: host_clb >> 32, 0x80002918: 1},
        )
        require_log(host_issue, ("P0_IRQTEST_IRQ PENDING=", "HOST_AUTOFETCH_INIT=0000001D",
                                 "HOST_IDENTIFY_EVENT=00000001",
                                 "HOST_IDENTIFY_EVENT=00000002",
                                 "HOST_RESULT=COMPLETE", "STATIC_TEST_END"),
                    ("MONITOR READY",))
        if (len(host_issue["synthetic_host_auto_fetches"]) != 1 or
                len(host_issue["synthetic_host_data_transfers"]) != 1 or
                [item["ata_command"] for item in host_issue["port0_command_issues"]]
                != ["0xEC", "0x25", "0xEC", "0xEC"]):
            raise ImageError("static host command did not reach the modeled backend")
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print("static image: no-disk, linked SSD without host command, and host IDENTIFY modeled")
    print("all scenarios print STATIC_TEST_END without reading UART commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
