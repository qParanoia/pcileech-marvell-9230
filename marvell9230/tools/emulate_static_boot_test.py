

"""Verify the automatic V7 diagnostic or V8 basic boot image in Unicorn."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

from build_c_stage import ROOT, compile_stage
from emulate_loader_copy import verify_loader_copy
from emulate_stock import run as stock_run
from image_builder import replace_code1_entry, disable_option_rom
from inspect_image import ImageError, image_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("--basic-boot", action="store_true")
    parser.add_argument("--no-option-rom", action="store_true")
    parser.add_argument("--ch568-diagnostics", action="store_true")
    parser.add_argument("--basic-boot-probe", "--basic-boot-v13",
                        action="store_true")
    parser.add_argument("--frozen-v13-image", action="store_true",
                        help="test the immutable delivered V13 SPI image without rebuilding")
    parser.add_argument("--stripped-stock-runtime", action="store_true",
                        help="zero the unused stock CODE1 tail, CODE2/3, DATA1 and Option ROM in memory before emulation")
    args = parser.parse_args()
    if args.ch568_diagnostics and (not args.basic_boot_probe or args.frozen_v13_image):
        parser.error("--ch568-diagnostics requires rebuilt --basic-boot-probe")
    if args.no_option_rom and (not args.basic_boot_probe or args.frozen_v13_image):
        parser.error("--no-option-rom requires rebuilt --basic-boot-probe")
    if args.stripped_stock_runtime and not args.basic_boot_probe:
        parser.error("--stripped-stock-runtime requires --basic-boot-v13")
    if args.frozen_v13_image and not args.basic_boot_probe:
        parser.error("--frozen-v13-image requires --basic-boot-v13")
    def run(image: bytes, max_steps: int, **kwargs: object) -> dict:
        result = stock_run(image, max_steps, **kwargs)
        if result["stop_reason"] != "instruction limit":
            raise ImageError(f"open-stage run stopped unexpectedly: {result['stop_reason']}")
        return result
    basic_boot = args.basic_boot or args.basic_boot_probe
    label = ("delivered V13 artifact" if args.frozen_v13_image else
             "V20 working-tree rebuild" if args.basic_boot_probe
             else "V8" if basic_boot else "V7")
    marker = (("OPEN9230 BASIC BOOT V13" if args.frozen_v13_image else
               "OPEN9230 BASIC BOOT V20") if args.basic_boot_probe else
              "OPEN9230 BASIC BOOT V8" if basic_boot else
              "OPEN9230 STATIC BOOT V7")
    if args.ch568_diagnostics:
        label = "V22 CH568 diagnostics working-tree rebuild"
        marker = "OPEN9230 BASIC BOOT V22 CH568=DIAGNOSTICS"
    backend_prefix = ["0xEC"] if basic_boot else ["0xEC", "0x25", "0xEC"]
    cflags = ["-DOPEN9230_STATIC_BOARD_TEST=1", "-DOPEN9230_STATIC_BOOT_TEST=1",
              "-DSTATIC_TEST_POLL_BUDGET=128u"]
    if basic_boot:
        cflags.append("-DOPEN9230_BASIC_BOOT=1")
    if args.basic_boot_probe:
        cflags.append("-DOPEN9230_DMA_PROBE=1")
    if args.no_option_rom:
        cflags.append("-DOPEN9230_NO_OPTION_ROM=1")
    if args.ch568_diagnostics:
        cflags.append("-DOPEN9230_CH568_DIAGNOSTICS=1")
    template = args.template.read_bytes()
    if args.frozen_v13_image:
        image = (ROOT / "build" / "basic-boot-v13.bin").read_bytes()
        expected_hash = "701d2a6c2fd62ac1344d794cb38f08135f417556b96f8c580d738fc65f09b318"
        if hashlib.sha256(image).hexdigest() != expected_hash:
            raise ImageError("delivered V13 SPI image SHA-256 changed")
        code1_start = int(image_summary(template)["segments"][0]["spi_source"], 16)


        payload = image[code1_start:code1_start + 34380]
        marker_signature = bytes.fromhex("0000a0e11eff2fe1")
        marker_addresses = [offset for offset in range(0, len(payload) - 7, 4)
                            if payload[offset:offset + 8] == marker_signature]
        if marker_addresses != [0x2500]:
            raise ImageError(f"delivered V13 idle hook changed: {marker_addresses!r}")
        symbols = {"stage_poll_marker": marker_addresses[0]}
    else:
        payload, symbols = compile_stage(
            ROOT / "build" / "toolchain",
            ROOT / "build" / ("c-stage-basic-boot-probe-emulator" if args.basic_boot_probe
                               else "c-stage-basic-boot-emulator" if args.basic_boot
                               else "c-stage-static-boot-emulator"),
            cflags=tuple(cflags),
        )
        image, code1_start = replace_code1_entry(template, payload)
    if args.no_option_rom:
        before = image
        image = disable_option_rom(image)
        if image[:0x20000] != before[:0x20000] or image[0x30000:] != before[0x30000:]:
            raise ImageError("Option ROM removal modified another SPI region")
        if image[0x20000:0x30000] != b'\xFF' * 0x10000:
            raise ImageError("Option ROM region not erased")
        verify_loader_copy(image)
    if args.stripped_stock_runtime:
        layout = image_summary(template)
        stripped = bytearray(image)
        for segment in layout["segments"]:
            start = int(segment["spi_source"], 16)

            size = int(segment["size"], 16)
            end = start + ((size + 7) & ~7)
            if segment["index"] == 0:
                if start != code1_start:
                    raise ImageError("open stage does not begin at stock CODE1 source")
                start += len(payload)
            stripped[start:end] = b"\x00" * (end - start)
        stripped[0x20000:0x30000] = b"\x00" * 0x10000
        image = bytes(stripped)
        verify_loader_copy(image)
    no_disk = run(image, 45000, allow_modified_image=True, code_limit=len(payload))
    if (marker not in no_disk["uart"] or
            "HOST_CONSOLE_AUTOFETCH=0000080D" not in no_disk["uart"] or
            "HOST_RESULT=NOT_READY" not in no_disk["uart"] or
            "HOST_SERVICE_CONTINUES" not in no_disk["uart"] or
            no_disk["port0_command_issues"]):
        raise ImageError(f"{label} no-disk path differs")

    if args.basic_boot_probe and not args.frozen_v13_image:
        liveness = run(image, 70000, allow_modified_image=True,
                       code_limit=len(payload), uart_input=b'?')
        if ("HOST_ALIVE POLLS=" not in liveness["uart"] or
                "ISSUED=00000000 DONE=00000000 ERR=00000000" not in liveness["uart"] or
                liveness["port0_command_issues"]):
            raise ImageError("read-only UART liveness query failed or issued SATA I/O")
        print("UART '?' reports liveness and zero I/O counters with no disk/host")


    host_clb = 0x00000001100080C0
    host_ctba = 0x0000000110002000
    host_data = 0x0000000110100000
    host_rfis = 0x0000000110004000
    header = struct.pack("<4I", 0x00010005, 0, host_ctba & 0xFFFFFFFF,
                         host_ctba >> 32)
    for opcode in (0xEC, 0x25, 0x35, 0xEA, 0x06, 0xB0,
                   0xE7, 0xC8, 0xCA, 0xF5):
        has_data = opcode not in (0xEA, 0xE7, 0xF5)
        is_write = opcode in (0x35, 0x06, 0xCA)
        command_header = struct.pack(
            "<4I", 5 | (0x40 if is_write else 0)
            | (0x10000 if has_data else 0),
            0, host_ctba & 0xFFFFFFFF, host_ctba >> 32)
        fis = bytes((0x27, 0x80, opcode, 0, 0, 0, 0,
                     0x40 if opcode != 0xEC else 0,
                     0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0))
        table = bytearray(0x90 if has_data else 0x80)
        table[:20] = fis
        if has_data:
            struct.pack_into("<4I", table, 0x80, host_data & 0xFFFFFFFF,
                             host_data >> 32, 0, 0x800001FF)
        if opcode == 0x25:
            read_table = bytes(table)
        result = run(
            image, 500000, allow_modified_image=True, code_limit=len(payload),
            port0_sstatus=0x133, experimental_sata_io=True,
            synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
            synthetic_sata_idle_pc=symbols["stage_poll_marker"],
            synthetic_open_autofetch_at_enable=True,
            synthetic_host_cpu_window=args.basic_boot_probe,
            synthetic_host_command_list=(host_clb, command_header),
            synthetic_host_command_table=(host_ctba, bytes(table)),
            synthetic_host_prdt_buffer=(host_data, b"\xA5" * 512)
            if has_data else None,
            synthetic_host_rfis_buffer=(host_rfis, b"\xA5" * 0x100)
            if args.basic_boot_probe else None,
            initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                          0x80002900: host_clb & 0xFFFFFFFF,
                          0x80002904: host_clb >> 32, 0x80002918: 1,
                          0x80002938: 1, 0x8000A920: 0x50},
        )
        uart = result["uart"]
        for line in (marker, "HOST_CONSOLE_AUTOFETCH=0000081D",
                     f"HOST_IO OP=000000{opcode:02X} EVENT=00000001",
                     f"HOST_IO OP=000000{opcode:02X} EVENT=00000002", "HOST_COMPLETION IS=",
                     "HOST_RESULT=COMPLETE", "HOST_SERVICE_CONTINUES"):
            if line not in uart:
                raise ImageError(f"{label} opcode {opcode:02X} missing {line}: {uart[-1200:]!r}")
        if opcode == 0xF5 and ("P0IS=00000008" not in uart or
                               "P0SACT=00000001" not in uart):
            raise ImageError("F5 host completion does not match stock port status")
        if args.basic_boot_probe:
            rfis = bytes.fromhex(result["synthetic_host_rfis_data"])
            if ("HOST_RFIS STATUS=00000000" not in uart or
                    rfis[0x40:0x44] != b"\x34\x40\x50\x00" or
                    rfis[0x58:0x60] != b"\xA1\x40\x50\x00\x00\x00\x00\x00" or
                    (opcode == 0xEC and rfis[0x20:0x24] !=
                     b"\x5F\x40\x58\x00")):
                raise ImageError(f"{label} opcode {opcode:02X} did not publish host RFIS: "
                                 f"rfis={rfis[0x20:0x60].hex()} tail={uart[-1200:]!r}")
            host_list = bytes.fromhex(result["synthetic_host_command_list_data"])
            prdbc = struct.unpack_from("<I", host_list, 4)[0]
            expected_prdbc = 512 if opcode in (0xEC, 0x25, 0x35, 0x06,
                                                 0xC8, 0xCA) else 0
            if prdbc != expected_prdbc or (
                    expected_prdbc and
                    ("HOST_PRDBC STATUS=00000000" not in uart or
                     f" VALUE={expected_prdbc:08X}" not in uart)):
                raise ImageError(f"{label} opcode {opcode:02X} bad host PRDBC: "
                                 f"{prdbc:08X} tail={uart[-1200:]!r}")
        if opcode == 0xEC and args.basic_boot_probe:
            if ("HOST_DMA STATUS=00000000" not in uart or
                    "MATCH=00000200" not in uart or
                    "MODEL H=" not in uart):
                raise ImageError(f"{label} did not read the modeled host IDENTIFY buffer: {uart[-1600:]!r}")
        if ([event["ata_command"] for event in result["port0_command_issues"]]
                != backend_prefix + [f"0x{opcode:02X}"]):
            raise ImageError(f"{label} did not forward host opcode {opcode:02X}")
        if opcode in (0xEC, 0x25, 0xC8):
            if result["synthetic_host_data_transfers"] != [{
                    "bus_address": f"0x{host_data:016X}", "bytes": 512,
                    "source": "synthetic LBA-0 sector" if opcode != 0xEC
                              else "synthetic IDENTIFY sector"}]:
                raise ImageError("modeled host PRDT did not receive response data")
            data = bytes.fromhex(result["synthetic_host_prdt_data"])
            if opcode in (0x25, 0xC8) and (data[:2] != b"\x5A\x5A" or data[-2:] != b"\x55\xAA"):
                raise ImageError("modeled host READ data differs")
            if opcode == 0xEC and data[:2] != b"\x40\x00":
                raise ImageError("modeled host IDENTIFY data differs")
            if opcode == 0xEC and args.basic_boot_probe:
                words = struct.unpack("<256H", data)
                model = b"".join(bytes((word >> 8, word & 0xFF))
                                 for word in words[27:47]).decode("ascii").strip()
                sectors = sum(words[100 + i] << (16 * i) for i in range(4))
                if (not model or sectors == 0 or not (words[49] & (1 << 9)) or
                        not (words[83] & (1 << 10)) or
                        prdbc != len(data) or
                        rfis[0x58:0x5C] != b"\xA1\x40\x50\x00"):
                    raise ImageError("synthetic host discovery rejected IDENTIFY")
        elif opcode in (0x35, 0xCA):
            transfers = result["synthetic_host_data_transfers"]
            if (len(transfers) != 1 or transfers[0]["bytes"] != 512 or
                    transfers[0]["source"] != "synthetic WRITE sector"):
                raise ImageError("modeled host WRITE did not transfer 512 bytes")
        elif result["synthetic_host_data_transfers"]:
            raise ImageError("FLUSH unexpectedly transferred host data")
    if args.basic_boot_probe:
        identify_table = bytearray(0x90)
        identify_table[:16] = bytes((0x27, 0x80, 0xEC)) + bytes(13)
        struct.pack_into("<4I", identify_table, 0x80,
                         host_data & 0xFFFFFFFF, host_data >> 32, 0,
                         0x800001FF)
        header_check_args = dict(
            allow_modified_image=True, code_limit=len(payload),
            port0_sstatus=0x133, experimental_sata_io=True,
            synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
            synthetic_sata_idle_pc=symbols["stage_poll_marker"],
            synthetic_open_autofetch_at_enable=True,
            synthetic_host_cpu_window=True,
            synthetic_host_command_list=(host_clb, header),
            synthetic_host_command_table=(host_ctba, bytes(identify_table)),
            synthetic_host_prdt_buffer=(host_data, b"\xA5" * 512),
            initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                          0x80002900: host_clb & 0xFFFFFFFF,
                          0x80002904: host_clb >> 32, 0x80002918: 1,
                          0x80002938: 1},
        )
        damaged = run(image, 500000, synthetic_host_cpu_header_corrupt=True,
                      **header_check_args)
        damaged_header = bytes.fromhex(damaged["synthetic_host_command_list_data"])
        if ("HOST_PRDBC STATUS=00000005" not in damaged["uart"] or
                struct.unpack_from("<I", damaged_header, 4)[0] != 0 or
                "HOST_IO OP=000000EC EVENT=00000002" not in damaged["uart"]):
            raise ImageError("mismatched host header was modified or stalled")
        aligned = run(
            image, 500000, synthetic_host_cpu_header_at_aligned_base=True,
            report_memory_ranges=[(0x50008000, 32)], **header_check_args)
        aligned_direct = bytes.fromhex(aligned["synthetic_host_command_list_data"])
        aligned_base = bytes.fromhex(aligned["memory_snapshots"]["0x50008000"])
        if ("HOST_PRDBC STATUS=00000000" not in aligned["uart"] or
                " FALLBACK=00000001" not in aligned["uart"] or
                struct.unpack_from("<I", aligned_direct, 4)[0] != 0 or
                struct.unpack_from("<I", aligned_base, 4)[0] != 512):
            raise ImageError("aligned host-header fallback failed")
    write_header = struct.pack("<4I", 0x00010045, 0,
                               host_ctba & 0xFFFFFFFF, host_ctba >> 32)
    read_header = struct.pack("<4I", 0x00010005, 0,
                              host_ctba & 0xFFFFFFFF, host_ctba >> 32)
    write_fis = bytes((0x27, 0x80, 0x35, 0, 1, 0, 0, 0x40,
                       0, 0, 0, 0, 1, 0, 0, 0))
    read_fis = bytes((0x27, 0x80, 0x25, 0, 1, 0, 0, 0x40,
                      0, 0, 0, 0, 1, 0, 0, 0))
    write_table = bytearray(0x90)
    readback_table = bytearray(0x90)
    for target, fis in ((write_table, write_fis), (readback_table, read_fis)):
        target[:16] = fis
        struct.pack_into("<4I", target, 0x80, host_data & 0xFFFFFFFF,
                         host_data >> 32, 0, 0x800001FF)
    pattern = bytes(range(256)) * 2
    readback = run(
        image, 600000, allow_modified_image=True, code_limit=len(payload),
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_sata_idle_pc=symbols["stage_poll_marker"],
        synthetic_open_autofetch_at_enable=True,
        synthetic_open_followup_fetched=read_header + read_fis,
        synthetic_open_followup_table=bytes(readback_table),
        synthetic_disk_model=True, synthetic_clear_prdt_on_followup=True,
        synthetic_host_command_list=(host_clb, write_header),
        synthetic_host_command_table=(host_ctba, bytes(write_table)),
        synthetic_host_prdt_buffer=(host_data, pattern),
        initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                      0x80002900: host_clb & 0xFFFFFFFF,
                      0x80002904: host_clb >> 32, 0x80002918: 1,
                      0x80002938: 1, 0x8000A920: 0x50},
    )
    transfers = readback["synthetic_host_data_transfers"]
    if (not readback["synthetic_open_followup_delivered"] or
            [event["ata_command"] for event in readback["port0_command_issues"]]
            != backend_prefix + ["0x35", "0x25"] or
            [transfer["source"] for transfer in transfers]
            != ["synthetic WRITE sector", "synthetic disk sector"] or
            [transfer["lba"] for transfer in transfers] != [1, 1] or
            bytes.fromhex(readback["synthetic_host_prdt_data"]) != pattern or
            readback["synthetic_disk_sector_hashes"].get("1")
            != hashlib.sha256(pattern).hexdigest()):
        raise ImageError(f"modeled WRITE/READBACK failed: {readback['uart'][-1800:]!r}")


    legacy_lba = 0x01234567
    legacy_write_fis = bytearray(write_fis)
    legacy_read_fis = bytearray(read_fis)
    for fis, opcode in ((legacy_write_fis, 0xCA), (legacy_read_fis, 0xC8)):
        fis[2] = opcode
        fis[4:7] = legacy_lba.to_bytes(4, "little")[:3]
        fis[7] = 0x40 | (legacy_lba >> 24)
        fis[8:11] = b"\x00" * 3
    legacy_write_table = bytearray(write_table)
    legacy_read_table = bytearray(readback_table)
    legacy_write_table[:16] = legacy_write_fis
    legacy_read_table[:16] = legacy_read_fis
    legacy_pattern = bytes((value * 73 + 19) & 0xFF for value in range(512))
    legacy = run(
        image, 600000, allow_modified_image=True, code_limit=len(payload),
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_sata_idle_pc=symbols["stage_poll_marker"],
        synthetic_open_autofetch_at_enable=True,
        synthetic_open_followup_fetched=read_header + bytes(legacy_read_fis),
        synthetic_open_followup_table=bytes(legacy_read_table),
        synthetic_disk_model=True, synthetic_clear_prdt_on_followup=True,
        synthetic_host_command_list=(host_clb, write_header),
        synthetic_host_command_table=(host_ctba, bytes(legacy_write_table)),
        synthetic_host_prdt_buffer=(host_data, legacy_pattern),
        synthetic_host_cpu_window=args.basic_boot_probe,
        initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                      0x80002900: host_clb & 0xFFFFFFFF,
                      0x80002904: host_clb >> 32, 0x80002918: 1,
                      0x80002938: 1},
    )
    if ([event["ata_command"] for event in legacy["port0_command_issues"]]
            != backend_prefix + ["0xCA", "0xC8"] or
            [transfer["lba"] for transfer in legacy["synthetic_host_data_transfers"]]
            != [legacy_lba, legacy_lba] or
            bytes.fromhex(legacy["synthetic_host_prdt_data"]) != legacy_pattern or
            legacy["synthetic_disk_sector_hashes"].get(str(legacy_lba))
            != hashlib.sha256(legacy_pattern).hexdigest()):
        raise ImageError("modeled 28-bit high-LBA WRITE/READBACK failed")
    if args.basic_boot_probe:
        legacy_list = bytes.fromhex(legacy["synthetic_host_command_list_data"])
        if struct.unpack_from("<I", legacy_list, 4)[0] != 512:
            raise ImageError("28-bit high-LBA command did not publish PRDBC")
    write_4k_fis = bytearray(write_fis)
    read_4k_fis = bytearray(read_fis)
    for fis in (write_4k_fis, read_4k_fis):
        fis[4] = 8
        fis[12] = 8
    write_4k_table = bytearray(write_table)
    read_4k_table = bytearray(readback_table)
    for table, fis in ((write_4k_table, write_4k_fis),
                       (read_4k_table, read_4k_fis)):
        table[:16] = fis
        struct.pack_into("<I", table, 0x8C, 0x80000FFF)
    pattern_4k = bytes((index * 17 + (index >> 9) * 31) & 0xFF
                       for index in range(4096))
    readback_4k = run(
        image, 600000, allow_modified_image=True, code_limit=len(payload),
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_sata_idle_pc=symbols["stage_poll_marker"],
        synthetic_open_autofetch_at_enable=True,
        synthetic_open_followup_fetched=read_header + bytes(read_4k_fis),
        synthetic_open_followup_table=bytes(read_4k_table),
        synthetic_disk_model=True, synthetic_clear_prdt_on_followup=True,
        synthetic_host_command_list=(host_clb, write_header),
        synthetic_host_command_table=(host_ctba, bytes(write_4k_table)),
        synthetic_host_prdt_buffer=(host_data, pattern_4k),
        synthetic_host_cpu_window=args.basic_boot_probe,
        synthetic_host_rfis_buffer=(host_rfis, b"\xA5" * 0x100)
        if args.basic_boot_probe else None,
        initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                      0x80002900: host_clb & 0xFFFFFFFF,
                      0x80002904: host_clb >> 32, 0x80002918: 1,
                      0x80002938: 1},
    )
    transfers_4k = readback_4k["synthetic_host_data_transfers"]
    if ([event["ata_command"] for event in readback_4k["port0_command_issues"]]
            != backend_prefix + ["0x35", "0x25"] or
            [transfer["bytes"] for transfer in transfers_4k] != [4096, 4096] or
            [transfer["sectors"] for transfer in transfers_4k] != [8, 8] or
            bytes.fromhex(readback_4k["synthetic_host_prdt_data"]) != pattern_4k or
            len(readback_4k["synthetic_disk_sector_hashes"]) != 8):
        raise ImageError("modeled 4-KiB WRITE/READBACK failed")
    if args.basic_boot_probe:
        host_list_4k = bytes.fromhex(readback_4k["synthetic_host_command_list_data"])
        if (struct.unpack_from("<I", host_list_4k, 4)[0] != 4096 or
                "HOST_PRDBC STATUS=00000000" not in readback_4k["uart"] or
                " VALUE=00001000" not in readback_4k["uart"]):
            raise ImageError("modeled 4-KiB WRITE/READBACK did not update PRDBC")
    if args.basic_boot_probe and not args.frozen_v13_image:


        write_4kn_table = bytearray(write_table)
        read_4kn_table = bytearray(readback_table)
        for table in (write_4kn_table, read_4kn_table):
            struct.pack_into("<I", table, 0x8C, 0x80000FFF)
        native_4k = run(
            image, 600000, allow_modified_image=True, code_limit=len(payload),
            port0_sstatus=0x133, experimental_sata_io=True,
            synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
            synthetic_sata_idle_pc=symbols["stage_poll_marker"],
            synthetic_open_autofetch_at_enable=True,
            synthetic_open_followup_fetched=read_header + read_fis,
            synthetic_open_followup_table=bytes(read_4kn_table),
            synthetic_disk_model=True, synthetic_clear_prdt_on_followup=True,
            synthetic_logical_sector_bytes=4096,
            synthetic_host_command_list=(host_clb, write_header),
            synthetic_host_command_table=(host_ctba, bytes(write_4kn_table)),
            synthetic_host_prdt_buffer=(host_data, pattern_4k),
            synthetic_host_cpu_window=True,
            initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                          0x80002900: host_clb & 0xFFFFFFFF,
                          0x80002904: host_clb >> 32, 0x80002918: 1,
                          0x80002938: 1},
        )
        native_4k_list = bytes.fromhex(native_4k["synthetic_host_command_list_data"])
        if ([event["ata_command"] for event in native_4k["port0_command_issues"]]
                != backend_prefix + ["0x35", "0x25"] or
                [transfer["bytes"] for transfer in native_4k["synthetic_host_data_transfers"]]
                != [4096, 4096] or
                bytes.fromhex(native_4k["synthetic_host_prdt_data"]) != pattern_4k or
                len(native_4k["synthetic_disk_sector_hashes"]) != 1 or
                struct.unpack_from("<I", native_4k_list, 4)[0] != 4096 or
                "HOST_PRDBC STATUS=00000000" not in native_4k["uart"] or
                " VALUE=00001000" not in native_4k["uart"]):
            raise ImageError("modeled native-4K WRITE/READBACK or PRDBC failed")
        print("native-4K logical sector: one-sector WRITE/READ and 4096-byte PRDBC verified")


    large_bytes = 128 * 1024
    large_entries = 257
    large_write_header = struct.pack("<4I", 5 | 0x40 | (large_entries << 16),
                                     0, host_ctba & 0xFFFFFFFF, host_ctba >> 32)
    large_read_header = struct.pack("<4I", 5 | (large_entries << 16),
                                    0, host_ctba & 0xFFFFFFFF, host_ctba >> 32)
    large_write_fis = bytearray(write_fis)
    large_read_fis = bytearray(read_fis)
    for fis in (large_write_fis, large_read_fis):
        fis[4] = 0x20
        fis[12] = 0
        fis[13] = 1
    large_write_table = bytearray(0x80 + 16 * large_entries)
    large_read_table = bytearray(0x80 + 16 * large_entries)
    large_layout = tuple((host_data + index * 0x1000,
                          512 if index < 255 else 256)
                         for index in range(large_entries))
    for table, fis in ((large_write_table, large_write_fis),
                       (large_read_table, large_read_fis)):
        table[:16] = fis
        offset = 0
        for index, (address, length) in enumerate(large_layout):
            struct.pack_into("<4I", table, 0x80 + 16 * index,
                             address & 0xFFFFFFFF, address >> 32, 0,
                             0x80000000 | (length - 1))
            offset += length
        if offset != large_bytes:
            raise ImageError("large PRDT fixture has wrong size")
    large_pattern = bytes((index * 17 + (index >> 9) * 31) & 0xFF
                          for index in range(large_bytes))
    large = run(
        image, 650000, allow_modified_image=True, code_limit=len(payload),
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_sata_idle_pc=symbols["stage_poll_marker"],
        synthetic_open_autofetch_at_enable=True,
        synthetic_open_followup_fetched=large_read_header + bytes(large_read_fis),
        synthetic_open_followup_table=bytes(large_read_table),
        synthetic_disk_model=True, synthetic_clear_prdt_on_followup=True,
        synthetic_host_command_list=(host_clb, large_write_header),
        synthetic_host_command_table=(host_ctba, bytes(large_write_table)),
        synthetic_host_prdt_buffer=(host_data, large_pattern),
        synthetic_host_prdt_layout=large_layout,
        synthetic_host_cpu_window=args.basic_boot_probe,
        initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                      0x80002900: host_clb & 0xFFFFFFFF,
                      0x80002904: host_clb >> 32, 0x80002918: 1,
                      0x80002938: 1},
    )
    if (not large["synthetic_open_followup_delivered"] or
            [event["ata_command"] for event in large["port0_command_issues"]]
            != backend_prefix + ["0x35", "0x25"] or
            [transfer["bytes"] for transfer in large["synthetic_host_data_transfers"]]
            != [large_bytes, large_bytes] or
            bytes.fromhex(large["synthetic_host_prdt_data"]) != large_pattern or
            len(large["synthetic_disk_sector_hashes"]) != 256):
        raise ImageError("modeled 257-PRD 128-KiB WRITE/READBACK failed")
    if args.basic_boot_probe:
        large_host_list = bytes.fromhex(large["synthetic_host_command_list_data"])
        if (struct.unpack_from("<I", large_host_list, 4)[0] != large_bytes or
                "HOST_PRDBC STATUS=00000000" not in large["uart"] or
                " VALUE=00020000" not in large["uart"]):
            raise ImageError("modeled 257-PRD command did not publish PRDBC")
    repeated_read = run(
        image, 600000, allow_modified_image=True, code_limit=len(payload),
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_sata_idle_pc=symbols["stage_poll_marker"],
        synthetic_open_autofetch_at_enable=True,
        synthetic_open_followup_fetched=read_header + read_fis,
        synthetic_open_followup_table=bytes(readback_table),
        synthetic_disk_model=True,
        synthetic_host_command_list=(host_clb, read_header),
        synthetic_host_command_table=(host_ctba, bytes(readback_table)),
        synthetic_host_prdt_buffer=(host_data, b"\xA5" * 512),
        initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                      0x80002900: host_clb & 0xFFFFFFFF,
                      0x80002904: host_clb >> 32, 0x80002918: 1,
                      0x80002938: 1},
    )
    if (not repeated_read["synthetic_open_followup_delivered"] or
            [event["ata_command"] for event in repeated_read["port0_command_issues"]]
            != backend_prefix + ["0x25", "0x25"] or
            len(repeated_read["synthetic_host_data_transfers"]) != 2):
        raise ImageError("identical consecutive READ commands did not both complete")
    failed_read = run(
        image, 500000, allow_modified_image=True, code_limit=len(payload),
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_sata_error_on_completion_index=1 if basic_boot else 3,
        synthetic_sata_idle_pc=symbols["stage_poll_marker"],
        synthetic_open_autofetch_at_enable=True,
        synthetic_host_command_list=(host_clb, read_header),
        synthetic_host_command_table=(host_ctba, read_table),
        synthetic_host_prdt_buffer=(host_data, b"\xA5" * 512),
        synthetic_host_rfis_buffer=(host_rfis, b"\xA5" * 0x100)
        if args.basic_boot_probe else None,
        synthetic_host_cpu_window=args.basic_boot_probe,
        initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                      0x80002900: host_clb & 0xFFFFFFFF,
                      0x80002904: host_clb >> 32, 0x80002918: 1,
                      0x80002938: 1},
    )
    if ("HOST_IO OP=00000025 EVENT=FFFFFFFD" not in failed_read["uart"] or
            "P0IS=40000000" not in failed_read["uart"] or
            "P0CI=FFFFFFFE" not in failed_read["uart"]):
        raise ImageError("backend ATA error did not retire host slot")
    if args.basic_boot_probe:
        error_rfis = bytes.fromhex(failed_read["synthetic_host_rfis_data"])
        if ("HOST_RFIS STATUS=00000000" not in failed_read["uart"] or
                error_rfis[0x40:0x44] != b"\x34\x40\x51\x04" or
                error_rfis[0x58:0x5C] != b"\xA1\x40\x51\x04" or
                failed_read["synthetic_host_data_transfers"] or
                bytes.fromhex(failed_read["synthetic_host_prdt_data"]) != b"\xA5" * 512 or
                struct.unpack_from("<I", bytes.fromhex(
                    failed_read["synthetic_host_command_list_data"]), 4)[0] != 0):
            raise ImageError("backend ATA error did not publish error RFIS")
        failed_write = run(
            image, 500000, allow_modified_image=True, code_limit=len(payload),
            port0_sstatus=0x133, experimental_sata_io=True,
            synthetic_sata_polling=True,
            synthetic_sata_error_on_completion_index=1,
            synthetic_sata_idle_pc=symbols["stage_poll_marker"],
            synthetic_open_autofetch_at_enable=True,
            synthetic_disk_model=True,
            synthetic_host_command_list=(host_clb, write_header),
            synthetic_host_command_table=(host_ctba, bytes(write_table)),
            synthetic_host_prdt_buffer=(host_data, pattern),
            synthetic_host_cpu_window=True,
            initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                          0x80002900: host_clb & 0xFFFFFFFF,
                          0x80002904: host_clb >> 32, 0x80002918: 1,
                          0x80002938: 1},
        )
        if ("HOST_IO OP=00000035 EVENT=FFFFFFFD" not in failed_write["uart"] or
                "P0IS=40000000" not in failed_write["uart"] or
                failed_write["synthetic_host_data_transfers"] or
                failed_write["synthetic_disk_sector_hashes"] or
                struct.unpack_from("<I", bytes.fromhex(
                    failed_write["synthetic_host_command_list_data"]), 4)[0] != 0):
            raise ImageError("failed WRITE altered synthetic disk or reported full transfer")
    late = run(
        image, 500000, allow_modified_image=True, code_limit=len(payload),
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_sata_idle_pc=symbols["stage_poll_marker"],
        synthetic_open_host_issue_after_marker=True,
        synthetic_host_command_list=(host_clb, header),
        synthetic_host_command_table=(host_ctba, read_table),
        synthetic_host_prdt_buffer=(host_data, b"\xA5" * 512),
        report_memory_ranges=[(0x80002800, 0x140), (0x8000C060, 0x10),
                              (0x30000000, 0x40)],
    )
    if (not late["synthetic_late_host_delivered"] or
            "HOST_RESULT=NOT_READY" not in late["uart"] or
            late["uart"].find("HOST_IO OP=00000025 EVENT=00000002") <
            late["uart"].find("HOST_SERVICE_CONTINUES") or
            len(late["synthetic_host_data_transfers"]) != 1):
        host_regs = bytes.fromhex(late["memory_snapshots"]["0x80002800"])
        raise ImageError(f"{label} did not continue servicing a host READ after summary: "
                         f"delivered={late['synthetic_late_host_delivered']} "
                         f"transfers={late['synthetic_host_data_transfers']!r} "
                         f"stop={late['stop_reason']} "
                         f"ghc={struct.unpack_from('<I', host_regs, 4)[0]:08X} "
                         f"cmd={struct.unpack_from('<I', host_regs, 0x118)[0]:08X} "
                         f"ci={struct.unpack_from('<I', host_regs, 0x138)[0]:08X} "
                         f"shadow={late['memory_snapshots']['0x8000C060']} "
                         f"tail={late['uart'][-1200:]!r}")
    if args.basic_boot_probe:
        reset = run(
            image, 300000, allow_modified_image=True, code_limit=len(payload),
            port0_sstatus=0x133, experimental_sata_io=True,
            synthetic_sata_polling=True,
            synthetic_sata_idle_pc=symbols["stage_poll_marker"],
            synthetic_open_port_reset_after_marker=True,
            initial_mmio={0x8000A920: 0x50},
        )
        if (reset["synthetic_open_port_reset_phase"] != 2 or
                "HOST_PORT0_RESET_DONE SSTS=00000133 SIG=00000101 TFD=00000050"
                not in reset["uart"]):
            raise ImageError(f"{label} full-image COMRESET recovery failed: {reset['uart'][-1200:]!r}")
    identify_fis = bytes((0x27, 0x80, 0xEC, 0)) + b"\x00" * 10 + b"\x01\x00"
    identify_table = bytearray(0x90)
    identify_table[:16] = identify_fis
    struct.pack_into("<4I", identify_table, 0x80, host_data & 0xFFFFFFFF,
                     host_data >> 32, 0, 0x800001FF)
    feature_fetched = (struct.pack("<4I", 5, 0, host_ctba & 0xFFFFFFFF,
                                   host_ctba >> 32)
                       + bytes((0x27, 0x80, 0xEF, 0x03)) + b"\x00" * 12)
    received_fis = bytearray(0x100)
    received_fis[0x40:0x50] = bytes((0x34, 0x40, 0x50)) + bytes(13)
    console_fetched = bytearray(0x100)
    struct.pack_into("<I", console_fetched, 0, 0x00010025)
    console_fetched[0x10:0x14] = bytes((0x27, 0x80, 0xA0, 0))
    console_fetched[0x50:0x54] = bytes((0xE1, 0x10, 0x01, 0x01))
    followup = run(
        image, 550000, allow_modified_image=True, code_limit=len(payload),
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_sata_idle_pc=symbols["stage_poll_marker"],
        synthetic_open_autofetch_at_enable=True,
        synthetic_open_followup_fetched=feature_fetched,
        synthetic_open_console_fetched=bytes(console_fetched),
        synthetic_host_command_list=(host_clb, header),
        synthetic_host_command_table=(host_ctba, bytes(identify_table)),
        synthetic_host_prdt_buffer=(host_data, b"\xA5" * 512),
        synthetic_backend_received_fis=bytes(received_fis),
        initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                      0x80002900: host_clb & 0xFFFFFFFF,
                      0x80002904: host_clb >> 32, 0x80002918: 1,
                      0x80002938: 1, 0x8000A920: 0x50},
    )
    if (not followup["synthetic_open_followup_delivered"] or
            "HOST_IO OP=000000EF EVENT=00000001" not in followup["uart"] or
            "HOST_IO OP=000000EF EVENT=00000002" not in followup["uart"] or
            [event["ata_command"] for event in followup["port0_command_issues"]]
            != backend_prefix + ["0xEC", "0xEF"]):
        raise ImageError(f"{label} back-to-back EF/03 failed: {followup['uart'][-1500:]!r}")
    if ("HOST_20=00000000" not in followup["uart"] or
            "P0IS=00000008" not in followup["uart"] or
            not followup["frontend_fis_snapshots"] or
            bytes.fromhex(followup["frontend_fis_snapshots"][-1]["host_fis_sram"])[0x20:0x24]
            != b"\x00\x00\x00\x00"):
        raise ImageError(f"{label} EF/03 completion differs from stock: "
                         f"fis={followup['frontend_fis_snapshots']!r} "
                         f"tail={followup['uart'][-1500:]!r}")
    if (not followup["synthetic_open_console_delivered"] or
            "HOST_VPORT PORT=00000007" not in followup["uart"] or
            "HOST_CONSOLE_SRAM=00000000 00010025" not in followup["uart"] or
            "010110E1" not in followup["uart"]):
        raise ImageError(f"{label} did not record a synthetic console-port request: "
                         f"delivered={followup['synthetic_open_console_delivered']} "
                         f"tail={followup['uart'][-1800:]!r}")
    print(f"{label} static image: no-disk and ten basic host ATA opcode paths verified")
    if args.stripped_stock_runtime:
        print("stock loader copied four stripped segments; open runtime needs no stock CODE1 tail, CODE2/3, DATA1 or Option ROM bytes")
    if args.basic_boot_probe:
        print("synthetic host discovery accepted 512-byte IDENTIFY, PRDBC, model, capacity and response FIS")
        print("mismatched host command header rejected without changing PRDBC")
        print("non-1-KiB CLB fallback updates only the matching aligned header")
    print("serialized LBA-1 WRITE followed by READ returns the same 512 bytes in disk model")
    print("28-bit DMA high-LBA WRITE/READ returns the same 512 bytes in disk model")
    print("serialized eight-sector WRITE/READ returns the same 4096 bytes in disk model")
    print("257 non-contiguous PRDT entries: 128-KiB WRITE/READ returns identical data in disk model")
    print("two identical consecutive READ commands each retire their host slot")
    print("synthetic backend ATA error retires host slot with PxIS.TFES")
    if args.basic_boot_probe:
        print("pre-transfer READ/WRITE errors leave host PRDBC zero and disk data unchanged")
    print("post-summary host READ and modeled 512-byte PRDT transfer verified")
    print("stock-style EF/03 completion and passive console-port capture verified")
    if args.basic_boot_probe:
        print("full-image virtual port COMRESET release restores SSD link and signature")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
