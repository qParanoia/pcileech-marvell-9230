

"""Probe the stock virtual console IDENTIFY PACKET DEVICE path in Unicorn."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from build_c_stage import ROOT, compile_stage
from emulate_stock import run
from image_builder import replace_code1_entry
from inspect_image import ImageError


def main() -> None:
    image = Path(__file__).resolve().parents[2] / "88.bin"
    host_clb = 0x000000000009C000
    host_ctba = 0x000000000009C200
    host_data = 0x000000000009C400
    header = struct.pack("<8I", 0x00010005, 0, host_ctba, 0, 0, 0, 0, 0)
    table = bytearray(0x90)
    table[0:20] = bytes((0x27, 0x80, 0xA1, 0, 0, 0, 0, 0,
                         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    struct.pack_into("<4I", table, 0x80, host_data, 0, 0, 0x800001FF)
    result = run(
        image.read_bytes(), 9_000_000, capture_mmio=True,
        fast_delays=True,
        synthetic_host_ghc_sequence=(0x80000000,),
        synthetic_host_port_command_issue=1,
        synthetic_host_port_index=7,
        synthetic_frontend_worker_once=True,
        synthetic_frontend_consumer_once=True,
        synthetic_backend_task_drain_once=True,
        synthetic_host_command_list=(host_clb, header),
        synthetic_host_command_table=(host_ctba, bytes(table)),
        synthetic_host_prdt_buffer=(host_data, b"\xA5" * 512),
        synthetic_host_cpu_window=True,
        code_visit_addresses=(0x7A60, 0x7C1C, 0x1D6C, 0x1E38,
                              0x3688, 0x3C64, 0x854C, 0x88B4),
        report_memory_ranges=[(0x04000620, 0x80),
                              (0x00014944, 0x200),
                              (0x30060EF4, 0xC0),
                              (0x300031C0, 0x80),
                              (0x04005218, 0x300),
                              (0x04004898, 0x10),
                              (0x30001C00, 0x100),
                              (0x80002C80, 0x80),
                              (0x8000C07C, 4)],
    )
    mmio = [e for e in result.pop("mmio_trace")
            if e["op"] == "write" and (
                e["addr"].startswith("0x80002C") or
                e["addr"].startswith("0x8000C0") or
                e["addr"] == "0x80002808")]
    stock_data = bytes.fromhex(result["memory_snapshots"]["0x00014944"])
    if bytes.fromhex(result["synthetic_host_prdt_data"]) != stock_data:
        raise ImageError("stock A1 did not transfer its 512-byte identify packet")
    for address, value in (("0x80002CB4", "0x00000001"),
                           ("0x8000C084", "0x00000080"),
                           ("0x80002CB8", "0xFFFFFFFE"),
                           ("0x80002C90", "0x00000008"),
                           ("0x80002808", "0x00000080")):
        if not any(e["addr"] == address and e["value"] == value for e in mmio):
            raise ImageError(f"stock A1 completion missing {address}={value}")

    payload, symbols = compile_stage(
        ROOT / "build" / "toolchain", ROOT / "build" / "c-stage-console-compare",
        cflags=("-DOPEN9230_STATIC_BOARD_TEST=1", "-DOPEN9230_STATIC_BOOT_TEST=1",
                "-DSTATIC_TEST_POLL_BUDGET=128u"),
    )
    open_image, _ = replace_code1_entry(image.read_bytes(), payload)
    port0_clb = 0x0000000110000000
    port0_ctba = 0x0000000110002000
    port0_data = 0x0000000110100000
    port0_header = struct.pack("<4I", 0x00010005, 0, port0_ctba & 0xFFFFFFFF,
                               port0_ctba >> 32)
    port0_table = bytearray(0x90)
    port0_table[:16] = bytes((0x27, 0x80, 0xEC, 0)) + bytes(10) + b"\x01\x00"
    struct.pack_into("<4I", port0_table, 0x80, port0_data & 0xFFFFFFFF,
                     port0_data >> 32, 0, 0x800001FF)
    ef_fetched = (struct.pack("<4I", 5, 0, port0_ctba & 0xFFFFFFFF,
                              port0_ctba >> 32)
                  + bytes((0x27, 0x80, 0xEF, 0x03)) + bytes(12))
    received_fis = bytearray(0x100)
    received_fis[0x40:0x50] = bytes((0x34, 0x40, 0x50)) + bytes(13)
    console_fetched = bytearray(0x100)
    console_fetched[:len(header)] = header
    console_fetched[0x10:0x20] = table[:16]
    open_kwargs = dict(
        allow_modified_image=True,
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_open_autofetch_at_enable=True,
        synthetic_open_followup_fetched=ef_fetched,
        synthetic_open_console_fetched=bytes(console_fetched),
        synthetic_open_console_command_table=(host_ctba, bytes(table)),
        synthetic_open_console_prdt_buffer=(host_data, b"\xA5" * 512),
        synthetic_host_command_list=(port0_clb, port0_header),
        synthetic_host_command_table=(port0_ctba, bytes(port0_table)),
        synthetic_host_prdt_buffer=(port0_data, b"\xA5" * 512),
        synthetic_backend_received_fis=bytes(received_fis),
        initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                      0x80002900: port0_clb & 0xFFFFFFFF,
                      0x80002904: port0_clb >> 32, 0x80002918: 1,
                      0x80002938: 1},
        report_memory_ranges=[(0x80002C80, 0x40), (0x8000C07C, 4)],
    )
    for label, test_image, test_payload, test_symbols, steps in (
            ("short loop", open_image, payload, symbols, 700000),
            ("final image", None, None, None, 1200000)):
        if test_image is None:
            final_payload, final_symbols = compile_stage(
                ROOT / "build" / "toolchain", ROOT / "build" / "c-stage-static-boot-test",
                cflags=("-DOPEN9230_STATIC_BOARD_TEST=1",
                        "-DOPEN9230_STATIC_BOOT_TEST=1"),
            )
            test_image, _ = replace_code1_entry(image.read_bytes(), final_payload)
            final_image = ROOT / "build" / "static-boot-dev.bin"
            if final_image.read_bytes() != test_image:
                raise ImageError("development image differs from compiled source")
            test_payload, test_symbols = final_payload, final_symbols
        opened = run(
            test_image, steps, code_limit=len(test_payload),
            synthetic_sata_idle_pc=test_symbols["stage_poll_marker"],
            **open_kwargs,
        )
        if (not opened["synthetic_open_console_delivered"] or
                "HOST_CONSOLE OP=000000A1 CODE=00000000 STATUS=00000000 EVENT=00000001" not in opened["uart"]):
            raise ImageError(f"{label}: open A1 did not run after EC and EF/03: {opened['uart'][-1000:]}")
        open_data = bytes.fromhex(opened["synthetic_open_console_prdt_data"])
        if open_data != stock_data:
            differing = [i for i, (a, b) in enumerate(zip(open_data, stock_data)) if a != b]
            raise ImageError(f"{label}: open A1 PRDT differs at {differing[:16]}")
        port = bytes.fromhex(opened["memory_snapshots"]["0x80002C80"])
        if struct.unpack_from("<I", port, 0x10)[0] != 8 or \
                struct.unpack_from("<I", port, 0x34)[0] != 1 or \
                struct.unpack_from("<I", port, 0x38)[0] != 0:
            raise ImageError(f"{label}: A1 completion registers differ from stock")
    print("stock and open A1: same 512-byte host PRDT response")
    print("SHA-256:", hashlib.sha256(stock_data).hexdigest())
    print("stock and open: port-7 SACT=1, CI clear, IS=8")
    print("open EC + EF/03 + console A1 completed in Unicorn, including final image")


if __name__ == "__main__":
    main()
