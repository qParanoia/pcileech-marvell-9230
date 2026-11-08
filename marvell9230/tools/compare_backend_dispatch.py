

"""Trace synthetic host IDENTIFY through stock backend and frontend completion."""

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
        host_clb = 0x0000000110000000
        host_ctba = 0x0000000110002000
        header = struct.pack("<8I", 0x00010005, 0, 0x10002000, 1,
                             0, 0, 0, 0)
        fis = bytes((0x27, 0x80, 0xEC, 0, 0, 0, 0, 0,
                     0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0))
        host_data_address = 0x0000000110100000
        table = bytearray(0x90)
        table[:len(fis)] = fis
        struct.pack_into("<4I", table, 0x80, host_data_address & 0xFFFFFFFF,
                         host_data_address >> 32, 0, 0x800001FF)
        physical_fis = bytearray(0x100)
        physical_fis[0x20:0x28] = bytes((0x5F, 0x60, 0x58, 0, 0, 0, 0, 0))
        physical_fis[0x40:0x50] = bytes((0x34, 0x40, 0x50)) + bytes(13)
        result = run(
            image, 9_000_000, capture_mmio=True,
            port0_sstatus=0x133, fast_delays=True, experimental_sata_io=True,
            synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
            synthetic_host_port_command_issue=1,
            synthetic_frontend_worker_once=True,
            synthetic_backend_task_drain_once=True,
            synthetic_host_command_list=(host_clb, header),
            synthetic_host_command_table=(host_ctba, bytes(table)),
            synthetic_host_prdt_buffer=(host_data_address, b"\xA5" * 512),
            synthetic_backend_received_fis=bytes(physical_fis),
            code_visit_addresses=(0x1E38, 0x3688, 0x3C64, 0x4844,
                                  0x4BAC, 0x4224, 0x1A44, 0x88B4, 0x854C,
                                  0x8618, 0x86B0, 0x86FC),
            report_memory_ranges=[(0x04003690, 8), (0x04000060, 8),
                                  (0x8000C060, 4)],
        )
        samples = result["code_visit_samples"]
        if not any(item["r0"] == "0x000000EC" and item["after_host_worker"]
                   for item in samples.get("0x00001E38", [])):
            raise ImageError("stock host callback did not decode IDENTIFY")
        if not any(item["after_host_worker"] and not item["after_backend_drain"]
                   for item in samples.get("0x00003688", [])):
            raise ImageError("host request did not enter the backend request list")
        if not result["synthetic_backend_task_drain_called"]:
            raise ImageError("backend task queue was not drained")
        if not any(item["r0"] == "0x04004988" and item["after_backend_drain"]
                   for item in samples.get("0x00003C64", [])):
            raise ImageError("stock backend scheduler did not invoke request dispatcher")
        if not any(item["after_backend_drain"] and item["r2"] == "0x00000000"
                   for item in samples.get("0x00004844", [])):
            raise ImageError("stock backend did not prepare host IDENTIFY")
        if not any(item["after_backend_drain"] and item["r0"] == "0x00000001"
                   for item in samples.get("0x00004BAC", [])):
            raise ImageError("stock backend did not issue the physical SATA command")
        issues = [event for event in result["port0_command_issues"]
                  if event.get("pc") == "0x00004BAC"]
        if len(issues) != 4 or issues[-1]["ata_command"] != "0xEC":
            raise ImageError("final physical SATA command differs from IDENTIFY")
        memory = result["memory_snapshots"]
        if struct.unpack("<2I", bytes.fromhex(memory["0x04003690"])) != (0x04003690,) * 2:
            raise ImageError("backend task queue remains linked")
        if struct.unpack("<2I", bytes.fromhex(memory["0x04000060"])) != (0x04000060,) * 2:
            raise ImageError("backend request queue remains linked")
        issue_shadow = int.from_bytes(bytes.fromhex(memory["0x8000C060"]), "little")
        if issue_shadow != 1:
            raise ImageError("unexpected host command-issue shadow")
        if not any(item["r1"] == "0x00000001" and item["after_backend_drain"]
                   for item in samples.get("0x00004224", [])):
            raise ImageError("stock backend did not retire the physical host command")
        if not any(item["r0"] == "0x04000620" and item["after_backend_drain"]
                   for item in samples.get("0x000088B4", [])):
            raise ImageError("stock backend did not invoke host completion callback")
        if result["code_visits"]["0x0000854C"] != 1:
            raise ImageError("stock frontend did not consume host completion")
        if (not samples.get("0x00008618") or
                samples["0x00008618"][0]["r4_flags"] != "0x00001002" or
                result["code_visits"]["0x000086B0"] or
                result["code_visits"]["0x000086FC"]):
            raise ImageError("stock IDENTIFY completion unexpectedly updated PRDBC")
        writes = {(event["addr"], event["value"])
                  for event in result["mmio_trace"] if event["op"] == "write"}
        for address, value in (("0x80002938", "0xFFFFFFFE"),
                               ("0x80002910", "0x00000008"),
                               ("0x8000C084", "0x00000001")):
            if (address, value) not in writes:
                raise ImageError(f"missing stock host completion write {address}={value}")
        if result["synthetic_host_data_transfers"] != [{
            "bus_address": f"0x{host_data_address:016X}",
            "bytes": 512, "source": "synthetic IDENTIFY sector",
        }]:
            raise ImageError("modeled host PRDT did not receive IDENTIFY sector")
        data = bytes.fromhex(result["synthetic_host_prdt_data"])
        if (len(data) != 512 or struct.unpack_from("<H", data, 0)[0] != 0x0040
                or struct.unpack_from("<H", data, 160)[0] != 0x07F8
                or struct.unpack_from("<H", data, 434)[0] != 1):
            raise ImageError("modeled host IDENTIFY data is invalid")
        print("host issue shadow=1 -> stock frontend decoded 0xEC -> backend request queued")
        print("backend task callback 0x3C64 -> physical SATA issue 0xEC, slot 0")
        print("physical completion -> stock callback -> frontend completion consumer")
        print("host PxCI clear-mask and PxIS interrupt writes observed")
        print("stock IDENTIFY completion leaves PRDBC unchanged")
        print("synthetic 64-bit host PRDT received 512 IDENTIFY bytes; PCIe DMA remains unverified")
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
