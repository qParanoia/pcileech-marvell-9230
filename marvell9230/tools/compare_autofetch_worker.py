

"""Confirm the stock host worker's auto-fetch command-list branch offline."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from emulate_stock import run
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("this comparison requires the analyzed stock 88.bin")
        result = run(
            image, 8_000_000, capture_mmio=True,
            port0_sstatus=0x133, fast_delays=True, experimental_sata_io=True,
            synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
            synthetic_host_port_command_issue=1,
            synthetic_frontend_worker_once=True,
            code_visit_addresses=(0x7A60, 0x7B18, 0x7B40, 0x1005C),
            report_memory_ranges=[(0x04004400, 4), (0x04005298, 4),
                                  (0x30000000, 0x40)],
        )
        visits = result["code_visits"]
        if not result["synthetic_frontend_worker_called"] or visits["0x00007A60"] != 1:
            raise ImageError("stock frontend worker not reached")
        if visits["0x00007B18"] != 1 or visits["0x00007B40"] or visits["0x0001005C"]:
            raise ImageError("stock worker did not select the auto-fetch branch")
        reads = [event for event in result["mmio_trace"] if event["op"] == "read"
                 and event["addr"] == "0x8000C060"]
        if not reads or int(reads[-1]["value"], 16) != 1:
            raise ImageError("worker did not observe injected host command issue")
        snapshots = result["memory_snapshots"]
        flags = int.from_bytes(bytes.fromhex(snapshots["0x04004400"]), "little")
        issued = int.from_bytes(bytes.fromhex(snapshots["0x04005298"]), "little")
        if flags & 0x20 == 0 or issued != 1:
            raise ImageError("auto-fetch flag or issued-mask state mismatch")
        if any(bytes.fromhex(snapshots["0x30000000"])):
            raise ImageError("auto-fetch SRAM window unexpectedly populated by fixture")
        print("stock worker read host CI=1 and selected auto-fetch SRAM path")
        print(f"auto-fetch flag=0x{flags:08X}, issued mask=0x{issued:08X}")
        print("host command-list SRAM is empty: hardware auto-fetch remains unmodeled")
        header = struct.pack("<8I", 0x00010005, 0, 0x30002000, 0, 0, 0, 0, 0)
        parsed = run(
            image, 8_000_000,
            port0_sstatus=0x133, fast_delays=True, experimental_sata_io=True,
            synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
            synthetic_host_port_command_issue=1,
            synthetic_frontend_worker_once=True,
            synthetic_host_autofetch_header=header,
            code_visit_addresses=(0x7C1C, 0x7C2C, 0x7C3C),
            report_memory_ranges=[(0x04000620, 0x34)],
        )
        samples = parsed["code_visit_samples"]
        if any(samples.get(f"0x{pc:08X}", [{}])[0].get("r4") != "0x04000620"
               for pc in (0x7C1C, 0x7C2C, 0x7C3C)):
            raise ImageError("stock worker did not allocate the expected command object")
        command = bytes.fromhex(parsed["memory_snapshots"]["0x04000620"])
        fields = struct.unpack_from("<9I", command, 0x10)
        if fields[0] != 0x00010005 or fields[2] != 0x30002000 or fields[3] != 0 or fields[8] != 0x30000010:
            raise ImageError("stock worker did not parse the synthetic AHCI header")
        print("synthetic AHCI header: flags=0x00010005, CTBA=0x30002000, local header=0x30000010")
        host_address = 0x0000000110000000
        fetched = run(
            image, 8_000_000,
            port0_sstatus=0x133, fast_delays=True, experimental_sata_io=True,
            synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
            synthetic_host_port_command_issue=1,
            synthetic_frontend_worker_once=True,
            synthetic_host_command_list=(host_address, header),
            report_memory_ranges=[(0x04000620, 0x34), (0x040052A8, 8),
                                  (0x30000000, 0x40)],
        )
        if fetched["synthetic_host_auto_fetches"] != [{
            "bus_address": f"0x{host_address:016X}",
            "sram_address": "0x30000000", "size": 0x400,
        }]:
            raise ImageError("modeled host-memory auto-fetch did not run")
        snapshots = fetched["memory_snapshots"]
        clb_low, clb_high = struct.unpack("<2I", bytes.fromhex(snapshots["0x040052A8"]))
        fetched_command = bytes.fromhex(snapshots["0x04000620"])
        if (clb_low, clb_high) != (0x10000000, 1) or fetched_command[0x10:0x34] != command[0x10:0x34]:
            raise ImageError("host-memory fetch differs from direct SRAM header parse")
        if bytes.fromhex(snapshots["0x30000000"])[:len(header)] != header:
            raise ImageError("host command list did not reach auto-fetch SRAM")
        print("modeled 64-bit host CLB -> 1 KiB SRAM auto-fetch -> same stock command object")
        fis = bytes((0x27, 0x80, 0xEC, 0, 0, 0, 0, 0,
                     0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0))
        table_address = 0x0000000110002000
        host_header = struct.pack("<8I", 0x00010005, 0, 0x10002000, 1,
                                  0, 0, 0, 0)
        decoded = run(
            image, 9_000_000,
            port0_sstatus=0x133, fast_delays=True, experimental_sata_io=True,
            synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
            synthetic_host_port_command_issue=1,
            synthetic_frontend_worker_once=True,
            synthetic_host_command_list=(host_address, host_header),
            synthetic_host_command_table=(table_address, fis),
            code_visit_addresses=(0x1DCC, 0x1E38, 0x1B3C, 0x3688),
            report_memory_ranges=[(0x30000010, 16)],
        )
        if decoded["synthetic_host_fis_fetches"] != [{
            "bus_address": f"0x{table_address:016X}",
            "sram_address": "0x30000010", "size": 16,
        }]:
            raise ImageError("modeled FIS auto-fetch did not run")
        if bytes.fromhex(decoded["memory_snapshots"]["0x30000010"]) != fis[:16]:
            raise ImageError("FIS prefix missing from auto-fetch SRAM")
        opcode_samples = decoded["code_visit_samples"].get("0x00001E38", [])
        if not any(item["r0"] == "0x000000EC" and item["r4"] == "0x04000620"
                   and item["after_host_worker"]
                   for item in opcode_samples):
            raise ImageError("stock frontend did not decode ATA IDENTIFY opcode")
        queue_samples = decoded["code_visit_samples"].get("0x00003688", [])
        if not any(item["r4"] == "0x04000620" and item["after_host_worker"]
                   for item in queue_samples):
            raise ImageError("decoded host command did not enter the stock request queue")
        print("modeled FIS prefix -> stock decoded ATA IDENTIFY (0xEC) and queued its request")
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
