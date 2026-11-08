

"""Exercise the opt-in open host IDENTIFY path with synthetic host memory."""

from __future__ import annotations

import argparse
import struct
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
    host_clb = 0x0000000110000000
    host_ctba = 0x0000000110002000
    host_data_address = 0x0000000110100000
    header = struct.pack("<4I", 0x00010005, 0, host_ctba & 0xFFFFFFFF, host_ctba >> 32)
    fis = bytes((0x27, 0x80, 0xEC, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0))
    table = bytearray(0x90)
    table[:len(fis)] = fis
    struct.pack_into("<4I", table, 0x80, host_data_address & 0xFFFFFFFF,
                     host_data_address >> 32, 0, 0x800001FF)
    try:
        payload, symbols = compile_stage(
            args.toolchain.resolve(), ROOT / "build" / "c-stage-experimental-frontend",
            cflags=("-DOPEN9230_EXPERIMENTAL_FRONTEND=1",),
        )
        image, _ = replace_code1_entry(args.template.read_bytes(), payload)
        disarmed = run(
            image, 30000, allow_modified_image=True,
            initial_mmio={0x8000C060: 1},
            initial_ram={0x30000000: header + fis},
            code_limit=len(payload),
        )
        if ("OPEN9230 MONITOR READY" not in disarmed["uart"] or
                "HOST_FRONTEND_PORTS=" in disarmed["uart"] or
                "HOST_IDENTIFY_EVENT=" in disarmed["uart"]):
            raise ImageError("experimental frontend ran before UART arming")
        host_probe = build_host_probe(args.toolchain.resolve(),
                                      ROOT / "build" / "host-probe.payload.bin")
        upload = (f"U{len(host_probe):08X}{zlib.crc32(host_probe):08X}\n".encode("ascii")
                  + host_probe + b"X\n")
        monitor = run(
            image, 600000, allow_modified_image=True,
            uart_input=b"?\nH\nR8000C044\n" + upload,
        )
        if ("COMMANDS ? H Rxxxxxxxx Ullllllllcccccccc X F" not in monitor["uart"] or
                "HOST_BEGIN" not in monitor["uart"] or
                "R 8000C044=" not in monitor["uart"] or
                "UPLOAD_OK" not in monitor["uart"] or
                "HOST-PROBE DONE" not in monitor["uart"] or
                "EXEC_RETURN" not in monitor["uart"] or
                "HOST_EXPERIMENT_ARMED" in monitor["uart"]):
            raise ImageError(f"disarmed UART monitor or RAM payload failed: {monitor['uart'][-1000:]!r}")
        result = run(
            image, 450000, capture_mmio=True, allow_modified_image=True,
            port0_sstatus=0x133, experimental_sata_io=True,
            synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
            synthetic_sata_idle_pc=symbols["stage_poll_marker"],
            synthetic_open_autofetch_at_enable=True,
            synthetic_host_command_list=(host_clb, header),
            synthetic_host_command_table=(host_ctba, bytes(table)),
            synthetic_host_prdt_buffer=(host_data_address, b"\xA5" * 512),
            initial_mmio={0x8000C060: 1, 0x80002900: host_clb & 0xFFFFFFFF,
                          0x80002904: host_clb >> 32, 0x80002918: 1},
            uart_input=b"F\n",
            report_memory_ranges=[(0x30000000, 32), (0x3006B000, 64)],
            code_limit=len(payload),
        )
        events = [line for line in result["uart"].splitlines()
                  if line.startswith("HOST_IDENTIFY_EVENT=")]
        if events != ["HOST_IDENTIFY_EVENT=00000001", "HOST_IDENTIFY_EVENT=00000002"]:
            raise ImageError(f"unexpected host event sequence: {events!r}")
        if "HOST_FRONTEND_PORTS=00000008" not in result["uart"]:
            raise ImageError("open frontend IRQ setup did not run")
        if "HOST_EXPERIMENT_ARMED" not in result["uart"]:
            raise ImageError("UART command did not arm host experiment")
        if "HOST_AUTOFETCH=0000001D" not in result["uart"]:
            raise ImageError("port-0 auto-fetch was not enabled")
        if result["synthetic_host_auto_fetches"] != [{
            "bus_address": f"0x{host_clb:016X}",
            "sram_address": "0x30000000", "size": 0x400,
        }] or result["synthetic_host_fis_fetches"] != [{
            "bus_address": f"0x{host_ctba:016X}",
            "sram_address": "0x30000010", "size": 16,
        }]:
            raise ImageError("host command list and FIS were not modeled from host memory")
        if bytes.fromhex(result["memory_snapshots"]["0x30000000"]) != header + fis:
            raise ImageError("auto-fetch SRAM window differs from host header/FIS")
        slot = bytes.fromhex(result["memory_snapshots"]["0x3006B000"])
        if slot[:4] != header[:4] or struct.unpack_from("<2I", slot, 8) != (0x10002004, 1) or slot[0x20:0x30] != fis:
            raise ImageError("backend host descriptor differs from requested IDENTIFY")
        if [event["ata_command"] for event in result["port0_command_issues"]] != ["0xEC", "0x25", "0xEC", "0xEC"]:
            raise ImageError("unexpected physical SATA issue sequence")
        if len(result["synthetic_host_data_transfers"]) != 1:
            raise ImageError("modeled host buffer did not receive IDENTIFY data")
        data = bytes.fromhex(result["synthetic_host_prdt_data"])
        if struct.unpack_from("<H", data)[0] != 0x40 or struct.unpack_from("<H", data, 160)[0] != 0x7F8:
            raise ImageError("modeled host IDENTIFY sector is invalid")
        writes = [(event["addr"], event["value"]) for event in result["mmio_trace"]
                  if event["op"] == "write"]
        for pair in (("0x80002938", "0xFFFFFFFE"),
                     ("0x80002910", "0x00000008"),
                     ("0x8000C084", "0x00000001")):
            if pair not in writes:
                raise ImageError(f"host completion MMIO write missing: {pair}")
        if result["stop_reason"] != "instruction limit":
            raise ImageError(f"experimental stage halted: {result['stop_reason']}")
        invalid = run(
            image, 300000, allow_modified_image=True, port0_sstatus=0x133,
            experimental_sata_io=True, synthetic_sata_polling=True,
            synthetic_irq_on_completion_index=2,
            synthetic_sata_idle_pc=symbols["stage_poll_marker"],
            initial_mmio={0x8000C060: 1},
            initial_ram={0x30000000: header + fis[:2] + b"\x25" + fis[3:]},
            uart_input=b"F\n",
            code_limit=len(payload),
        )
        invalid_events = [line for line in invalid["uart"].splitlines()
                          if line.startswith("HOST_IDENTIFY_EVENT=")]
        if invalid_events != ["HOST_IDENTIFY_EVENT=FFFFFFFE"] or len(invalid["port0_command_issues"]) != 3:
            raise ImageError("unsupported host opcode was issued or retried")
        no_disk = run(
            image, 30000, allow_modified_image=True,
            initial_mmio={0x8000C060: 1},
            initial_ram={0x30000000: header + fis},
            uart_input=b"F\n",
            code_limit=len(payload),
        )
        if ("HOST_IDENTIFY_EVENT=FFFFFFFF" not in no_disk["uart"] or
                no_disk["port0_command_issues"]):
            raise ImageError("host request with no backend disk was issued")
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print("opt-in open frontend: modeled host CLB/table auto-fetch -> IDENTIFY issue/retirement")
    print("disarmed boot stays in the UART monitor until F command")
    print("64-byte backend slot and three frontend completion writes verified")
    print("unsupported host opcode rejected without a fourth physical issue")
    print("host request with no backend disk rejected without physical issue")
    print("synthetic 64-bit host PRDT received 512 bytes; hardware DMA remains unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
