

"""Build and verify the freestanding C stage with one synthetic IRQ."""

from __future__ import annotations

import argparse
import zlib
from pathlib import Path

from build_c_stage import ROOT, compile_stage
from build_host_probe import build as build_host_probe
from emulate_stock import run
from image_builder import replace_code1_entry
from inspect_image import ImageError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("--toolchain", type=Path, default=ROOT / "build" / "toolchain")
    args = parser.parse_args()
    try:
        payload, symbols = compile_stage(args.toolchain.resolve(), ROOT / "build" / "c-stage")
        image, _ = replace_code1_entry(args.template.read_bytes(), payload)
        host_payload = build_host_probe(args.toolchain.resolve(), ROOT / "build" / "host-probe.payload.bin")
        upload = (f"U{len(host_payload):08X}{zlib.crc32(host_payload):08X}\n".encode("ascii")
                  + host_payload + b"X\n")
        monitor_result = run(
            image, 300000, allow_modified_image=True,
            uart_input=b"?\nH\nR80002800\nRFFFFFFFF\n" + upload,
            report_memory_ranges=[(0x30070000, 16)],
        )
        bad_crc_result = run(
            image, 100000, allow_modified_image=True,
            uart_input=b"U0000000400000000\n\x1e\xff\x2f\xe1X\n",
        )
        result = run(
            image,
            20000,
            capture_mmio=True,
            allow_modified_image=True,
            inject_irq_at_pc=symbols["stage_idle"],
            injected_irq_pending=0xA5,
            report_memory_ranges=[(symbols["startup_probe"], 4)],
            code_limit=len(payload),
        )
        linked_result = run(
            image, 20000, allow_modified_image=True, port0_sstatus=0x133,
            report_memory_ranges=[(0x3006B000, 0x40), (0x3006D400, 0xA0)],
            code_limit=len(payload),
        )
        passive_result = run(
            image, 20000, allow_modified_image=True, code_limit=len(payload),
            initial_mmio={
                0x8000A9A8: 0x133, 0x8000A9A4: 0x101,
                0x8000AA28: 0x120, 0x8000AAA8: 0x100,
                0xD0020114: 4,
                0xD0020300: 0xF, 0xD0020318: 0x01C9C380,
            },
        )
        completed_result = run(
            image, 250000, allow_modified_image=True, port0_sstatus=0x133,
            experimental_sata_io=True, synthetic_sata_polling=True,
            synthetic_irq_on_completion_index=2,
            synthetic_sata_idle_pc=symbols["stage_poll_marker"],
            report_memory_ranges=[(0x04001004, 4), (symbols["identify_completed"], 4), (0xD0020204, 4)],
            code_limit=len(payload),
        )
        timeout_payload, _ = compile_stage(
            args.toolchain.resolve(), ROOT / "build" / "c-stage-timeout",
            cflags=("-DIDENTIFY_TIMEOUT_POLLS=256u",),
        )
        timeout_image, _ = replace_code1_entry(args.template.read_bytes(), timeout_payload)
        timeout_result = run(
            timeout_image, 30000, allow_modified_image=True, port0_sstatus=0x133,
            code_limit=len(timeout_payload),
        )
        reference = run(args.template.read_bytes(), 1_000_000, port0_sstatus=0x133, fast_delays=True, capture_mmio=True)
        reference_ssd = run(
            args.template.read_bytes(), 2_000_000, port0_sstatus=0x133,
            fast_delays=True, experimental_sata_io=True,
        )
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    expected_prefix = (
        "OPEN9230 C-STAGE V6\r\nCHIP=92301B4B\r\nSTRAP=0000002F\r\n"
        "BSS=00000000\r\nPORTS=00000004\r\nPORTMAP=0000000F\r\n"
    )
    passive_snapshot = (
        "P1_SSTS=00000000\r\nP1_SIG=FFFFFFFF\r\n"
        "P2_SSTS=00000000\r\nP2_SIG=FFFFFFFF\r\n"
        "P3_SSTS=00000000\r\nP3_SIG=FFFFFFFF\r\n"
        "PUNIT_110=00000000\r\nPUNIT_114=00000000\r\n"
        "PUNIT_300=00000000\r\nPUNIT_318=00000000\r\n"
    )
    initialized_snapshot = (
        "PUNIT_POST_110=00000000\r\nPUNIT_POST_114=00000004\r\n"
        "PUNIT_POST_300=0000000F\r\nPUNIT_POST_318=01C9C380\r\n"
        "BECTL_BEFORE=00000000\r\nBECTL_AFTER=80000002\r\n"
    )
    expected_uart = expected_prefix + "P0_SSTS=00000000\r\nP0_SIG=FFFFFFFF\r\n" + passive_snapshot + initialized_snapshot + "P0_POST_SSTS=00000000\r\nP0_POST_SIG=FFFFFFFF\r\nP0_DESC=00000000\r\nOPEN9230 MONITOR READY\r\n"
    expected_linked_uart = expected_prefix + "P0_SSTS=00000133\r\nP0_SIG=00000101\r\n" + passive_snapshot + initialized_snapshot + "P0_POST_SSTS=00000133\r\nP0_POST_SIG=00000101\r\nP0_DESC=00000001\r\nP0_IDENTIFY_START\r\nP0_IDENTIFY_ISSUED CI=00000001 CMD=10000011\r\n"
    expected_passive_uart = expected_prefix + (
        "P0_SSTS=00000000\r\nP0_SIG=FFFFFFFF\r\n"
        "P1_SSTS=00000133\r\nP1_SIG=00000101\r\n"
        "P2_SSTS=00000120\r\nP2_SIG=FFFFFFFF\r\n"
        "P3_SSTS=00000100\r\nP3_SIG=FFFFFFFF\r\n"
        "PUNIT_110=00000000\r\nPUNIT_114=00000004\r\n"
        "PUNIT_300=0000000F\r\nPUNIT_318=01C9C380\r\n"
        "PUNIT_POST_110=00000000\r\nPUNIT_POST_114=00000004\r\n"
        "PUNIT_POST_300=0000000F\r\nPUNIT_POST_318=01C9C380\r\n"
        "BECTL_BEFORE=00000000\r\nBECTL_AFTER=80000002\r\n"
        "P0_POST_SSTS=00000000\r\nP0_POST_SIG=FFFFFFFF\r\nP0_DESC=00000000\r\nOPEN9230 MONITOR READY\r\n"
    )
    expected_completed_uart = expected_linked_uart + (
        "P0_IDENTIFY_POLL_DONE IS=00000002 TFD=00000000 IRQST=FFFFFFFF\r\n"
        "P0_W0=00000040\r\nP0_MAJOR=000007F8\r\n"
        "P0_ROTATION=00000001\r\nP0_DSM=00000001\r\n"
        "P0_READ0_START\r\nP0_READ0_ISSUED CI=00000002\r\n"
        "P0_READ0_POLL_DONE IS=00000001 TFD=00000000 IRQST=FFFFFFFF\r\n"
        "P0_READ0_W0=00005A5A\r\nP0_READ0_LAST=0000AA55\r\n"
        "P0_READ0_CHANGED=00000200\r\n"
        "P0_READ0_PRE=A5A5A5A5\r\nP0_READ0_POST=5A5A5A5A\r\n"
        "P0_IRQTEST_MASKED_START\r\n"
        "P0_IRQTEST_ISSUED CI=00000001 IS=FFFFFFFF IRQST=FFFFFFFF\r\n"
        "P0_IRQTEST_MASKED_DONE IS=00000002 IE=FDC000DB IRQST=00000001 VEC_IN=00C50078 SCTLR=00C50078 W0=00000040\r\n"
        "P0_IRQTEST_CPU_START\r\n"
        "P0_IRQTEST_IRQ PENDING=00000001 PORTIS=00000002 CI=00000000 ACK=00000001\r\n"
        "P0_IRQTEST_W0=00000040\r\n"
        "OPEN9230 MONITOR READY\r\n"
    )
    expected_markers = {
        "boot": "0x9230C002",
        "irq_count": 1,
        "irq_last": "0x000000A5",
    }
    if result["uart"] != expected_uart:
        print(f"unexpected UART: {result['uart']!r}")
        return 1
    for label, sample, fixture in (
        ("no disk", result, "open-c-stage-v1-no-disk.uart.txt"),
        ("one disk", linked_result, "open-c-stage-v1-one-disk.uart.txt"),
    ):
        measured = (ROOT / "fixtures" / fixture).read_text(encoding="utf-8").splitlines()
        before_init = measured[:measured.index("PUNIT_318=00000000") + 1]
        if sample["uart"].splitlines()[1:len(before_init)] != before_init[1:]:
            print(f"open {label} entry snapshot differs from the board capture")
            return 1
    if linked_result["uart"] != expected_linked_uart:
        print(f"unexpected link-present UART: {linked_result['uart']!r}")
        return 1
    if passive_result["uart"] != expected_passive_uart or passive_result["stop_reason"] != "instruction limit":
        print(f"unexpected passive MMIO snapshot: {passive_result['uart']!r}; {passive_result['stop_reason']}")
        return 1
    if completed_result["uart"] != expected_completed_uart:
        print(f"unexpected IDENTIFY completion UART: {completed_result['uart']!r}")
        return 1
    if (monitor_result["stop_reason"] != "instruction limit" or
        monitor_result["uart_rx_remaining"] or
        "COMMANDS ? H Rxxxxxxxx Ullllllllcccccccc X\r\n" not in monitor_result["uart"] or
        "HOST_BEGIN\r\nR 80002800=00000007\r\n" not in monitor_result["uart"] or
        "HOST_END\r\n" not in monitor_result["uart"] or
        "R 80002800=00000007\r\nERR ADDRESS\r\n" not in monitor_result["uart"] or
        "UPLOAD_OK\r\nEXEC_START\r\nOPEN9230 HOST-PROBE V1\r\n" not in monitor_result["uart"] or
        "HOST-PROBE DONE\r\nEXEC_RETURN\r\n" not in monitor_result["uart"] or
        monitor_result["memory_snapshots"]["0x30070000"] != host_payload[:16].hex()):
        print(f"UART monitor upload or RAM execution failed: {monitor_result['uart']!r}")
        return 1
    if ("UPLOAD_BAD_CRC\r\nERR NO_PAYLOAD\r\n" not in bad_crc_result["uart"] or
        "EXEC_START" in bad_crc_result["uart"] or bad_crc_result["uart_rx_remaining"]):
        print(f"UART monitor CRC rejection failed: {bad_crc_result['uart']!r}")
        return 1
    for label, sample in (("no disk", result), ("linked disk", linked_result)):
        if sample["stop_reason"] != "instruction limit":
            print(f"open {label} path stopped: {sample['stop_reason']}")
            return 1
    if completed_result["stop_reason"] != "instruction limit":
        print(f"open IDENTIFY path stopped: {completed_result['stop_reason']}")
        return 1
    if timeout_result["stop_reason"] != "instruction limit" or "P0_IDENTIFY_TIMEOUT CI=" not in timeout_result["uart"]:
        print(f"open timeout path failed: {timeout_result['stop_reason']}; {timeout_result['uart']!r}")
        return 1
    if completed_result["synthetic_completions"] != [
        {"command": "0xEC", "slot": 0, "buffer": "0x3006E080"},
        {"command": "0x25", "slot": 1, "buffer": "0x3006E0D8"},
        {"command": "0xEC", "slot": 0, "buffer": "0x3006E080"},
    ]:
        print(f"unexpected SATA completion: {completed_result['synthetic_completions']!r}")
        return 1
    if completed_result["memory_snapshots"]["0x04001004"] != "01000000":
        print("one-shot IRQ test did not enter the open IRQ handler once")
        return 1
    if completed_result["memory_snapshots"]["0xD0020204"] != "00000000":
        print("one-shot IRQ handler did not mask the global source")
        return 1
    if completed_result["irq_vector_visits"] != 1 or linked_result["irq_vector_visits"]:
        print("unexpected IRQ-vector count in the staged command path")
        return 1
    stock_identify = next(
        (event for event in reference["port0_command_issues"]
         if event["pc"] == "0x00004BAC" and event["value"] == "0x00000001"), None,
    )
    if stock_identify is None:
        print("reference image did not issue IDENTIFY")
        return 1
    expected_descriptor = {
        "0x3006B000": stock_identify["command_slot_raw"],
        "0x3006D400": stock_identify["request_raw"],
    }
    if linked_result["memory_snapshots"] != expected_descriptor:
        print("open IDENTIFY descriptor differs from the reference image")
        return 1
    stock_read0 = next(
        (event for event in reference_ssd["port0_command_issues"]
         if event.get("ata_command") == "0x25" and event.get("slot") == 1), None,
    )
    open_read0 = next(
        (event for event in completed_result["port0_command_issues"]
         if event.get("ata_command") == "0x25" and event.get("slot") == 1), None,
    )
    if stock_read0 is None or open_read0 is None or any(
        open_read0[key] != stock_read0[key] for key in ("command_slot_raw", "request_raw")
    ):
        print("open READ DMA EXT descriptor differs from the reference image")
        return 1
    open_identify = next(
        (event for event in linked_result["port0_command_issues"]
         if event.get("ata_command") == "0xEC"), None,
    )
    observed_registers = {key for key in stock_identify["controller_registers"] if key != "0xD0020110"}
    if open_identify is None or any(
        open_identify["controller_registers"][key] != stock_identify["controller_registers"][key]
        for key in observed_registers
    ):
        print("open IDENTIFY controller state differs from the reference image")
        print(f"open: {open_identify and open_identify['controller_registers']!r}")
        print(f"stock: {stock_identify['controller_registers']!r}")
        return 1
    if open_identify["irq_enable"] != "0x00000000" or open_identify["port0_ie"] != "0x00000000":
        print("polling-only IDENTIFY unexpectedly enabled an IRQ")
        return 1
    punit_addresses = {
        "0x80003818", "0xD0020114", "0xD0020110", "0xD0020300",
        "0xD0020000", "0xD0020010", "0xD0020310", "0xD0020318",
        "0xD002031C", "0xD0071058", "0xD0071028", "0xD0071024",
    }
    def punit_writes(sample: dict) -> list[tuple[str, str]]:
        return [(event["addr"], event["value"]) for event in sample["mmio_trace"]
                if event["op"] == "write" and event["addr"] in punit_addresses]
    if punit_writes(result) != punit_writes(reference)[:len(punit_writes(result))]:
        print("open PUNIT write sequence differs from the reference image")
        print(f"open: {punit_writes(result)!r}")
        print(f"stock: {punit_writes(reference)!r}")
        return 1
    if any(result["stage_markers"][key] != value for key, value in expected_markers.items()):
        print(f"unexpected stage markers: {result['stage_markers']!r}")
        return 1
    if result["memory_snapshots"][f"0x{symbols['startup_probe']:08X}"] != "0100dec0":
        print("BSS variable did not retain the expected value")
        return 1
    if not result["debug_irq_injected"] or result["irq_vector_visits"] < 1:
        print("synthetic IRQ did not traverse the open vector")
        return 1
    if not (symbols["stage_idle"] <= int(result["last_pc"], 16) < symbols["stage_main"]
            or int(result["last_pc"], 16) == symbols["stage_poll_marker"]):
        print(f"IRQ did not return to the idle loop: {result['last_pc']}")
        return 1
    print(result["uart"], end="")
    print("open C stage: board-calibrated SATA/IRQ, UART command monitor, CRC-checked RAM upload and return verified offline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
