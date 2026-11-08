

"""Compare ARM open IDENTIFY slot builder with the stock backend slot."""

from __future__ import annotations

import argparse
import struct
import subprocess
from pathlib import Path

from build_c_stage import COMMON, FIRMWARE, ROOT
from emulate_stock import run
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary
from probe_host_rw import probe


def arm_slot(fetched: bytes, program: bytes, entry: int) -> tuple[int, bytes]:
    from unicorn import UC_ARCH_ARM, UC_MODE_ARM, Uc
    from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP

    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x1000, 0x1000)
    uc.mem_map(0x20000, 0x1000)
    uc.mem_map(0x30000, 0x1000)
    uc.mem_write(0x1000, program)
    uc.mem_write(0x20000, fetched)
    uc.mem_write(0x20100, b"\xCC" * 64)
    uc.reg_write(UC_ARM_REG_R0, 0x20000)
    uc.reg_write(UC_ARM_REG_R1, 0x20100)
    uc.reg_write(UC_ARM_REG_SP, 0x31000)
    uc.reg_write(UC_ARM_REG_LR, 0xF000)
    uc.emu_start(entry, 0xF000, count=2000)
    return uc.reg_read(UC_ARM_REG_R0), bytes(uc.mem_read(0x20100, 64))


def compile_builder(toolchain: Path) -> tuple[bytes, dict[str, int]]:
    bin_dir = toolchain / "bin"
    gcc = bin_dir / "arm-none-eabi-gcc.exe"
    objcopy = bin_dir / "arm-none-eabi-objcopy.exe"
    nm = bin_dir / "arm-none-eabi-nm.exe"
    out = ROOT / "build" / "host-command-test"
    out.mkdir(parents=True, exist_ok=True)
    elf = out / "host_command.elf"
    raw = out / "host_command.bin"
    commands = (
        [str(gcc), *COMMON, "-fno-tree-loop-distribute-patterns", "-std=c11",
         "-nostdlib", "-Wl,-Ttext=0x1000", "-Wl,-e,host_build_identify_slot",
         str(FIRMWARE / "host_command.c"), "-lgcc", "-o", str(elf)],
        [str(objcopy), "-O", "binary", str(elf), str(raw)],
    )
    try:
        for command in commands:
            subprocess.run(command, check=True, text=True, capture_output=True)
        symbols = subprocess.run([str(nm), "-n", str(elf)], check=True,
                                 text=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise ImageError(f"ARM host builder compilation failed: {detail}") from exc
    addresses = {line.split()[-1]: int(line.split()[0], 16)
                 for line in symbols.splitlines() if len(line.split()) == 3}
    for name in ("host_build_identify_slot", "host_build_basic_slot"):
        if name not in addresses:
            raise ImageError(f"ARM host builder symbol missing: {name}")
    return raw.read_bytes(), addresses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--toolchain", type=Path, default=ROOT / "build" / "toolchain")
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("this comparison requires the analyzed stock 88.bin")
        host_clb = 0x0000000110000000
        host_ctba = 0x0000000110002000
        header = struct.pack("<8I", 0x00010005, 0, host_ctba & 0xFFFFFFFF,
                             host_ctba >> 32, 0, 0, 0, 0)
        fis = bytes((0x27, 0x80, 0xEC, 0, 0, 0, 0, 0,
                     0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0))
        table = bytearray(0x90)
        table[:len(fis)] = fis
        struct.pack_into("<4I", table, 0x80, 0x10100000, 1, 0, 0x800001FF)
        result = run(
            image, 9_000_000,
            port0_sstatus=0x133, fast_delays=True, experimental_sata_io=True,
            synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
            synthetic_host_port_command_issue=1,
            synthetic_frontend_worker_once=True,
            synthetic_backend_task_drain_once=True,
            synthetic_host_command_list=(host_clb, header),
            synthetic_host_command_table=(host_ctba, bytes(table)),
            synthetic_host_prdt_buffer=(0x0000000110100000, b"\xA5" * 512),
        )
        issues = [event for event in result["port0_command_issues"]
                  if event.get("pc") == "0x00004BAC"]
        if len(issues) != 4 or issues[-1]["ata_command"] != "0xEC":
            raise ImageError("stock host IDENTIFY slot missing")
        expected = bytes.fromhex(issues[-1]["command_slot_raw"])
        fetched = bytearray(header)
        fetched[16:32] = fis[:16]
        program, entries = compile_builder(args.toolchain.resolve())
        status, actual = arm_slot(bytes(fetched), program, entries["host_build_identify_slot"])
        if status != 0 or actual != expected:
            raise ImageError("open ARM IDENTIFY slot differs from stock physical slot")
        for index, value, label in ((18, 0x35, "write opcode"),
                                    (8, 0x01, "unaligned CTBA"),
                                    (17, 0x00, "missing H2D command flag")):
            malformed = bytearray(fetched)
            malformed[index] = value
            status, output = arm_slot(bytes(malformed), program, entries["host_build_identify_slot"])
            if status != 0xFFFFFFFE or output != b"\xCC" * 64:
                raise ImageError(f"open ARM builder accepted {label}")
        read_fis = bytes((0x27, 0x80, 0x25, 0, 0, 0, 0, 0x40,
                          0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0))
        read_table = bytearray(table)
        read_table[:20] = read_fis
        read_result = run(
            image, 9_000_000,
            port0_sstatus=0x133, fast_delays=True, experimental_sata_io=True,
            synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
            synthetic_host_port_command_issue=1,
            synthetic_frontend_worker_once=True,
            synthetic_backend_task_drain_once=True,
            synthetic_host_command_list=(host_clb, header),
            synthetic_host_command_table=(host_ctba, bytes(read_table)),
            synthetic_host_prdt_buffer=(0x0000000110100000, b"\xA5" * 512),
        )
        read_issues = [event for event in read_result["port0_command_issues"]
                       if event.get("pc") == "0x00004BAC"]
        if len(read_issues) != 4 or read_issues[-1]["ata_command"] != "0x25":
            raise ImageError("stock host READ DMA EXT slot missing")
        read_fetched = bytearray(header)
        read_fetched[16:32] = read_fis[:16]
        status, actual = arm_slot(bytes(read_fetched), program,
                                  entries["host_build_basic_slot"])
        if status != 0 or actual != bytes.fromhex(read_issues[-1]["command_slot_raw"]):
            raise ImageError("open ARM READ DMA EXT slot differs from stock physical slot")
        for index, value in ((18, 0x35), (28, 0)):
            malformed = bytearray(read_fetched)
            malformed[index] = value
            status, output = arm_slot(bytes(malformed), program,
                                      entries["host_build_basic_slot"])
            if status != 0xFFFFFFFE or output != b"\xCC" * 64:
                raise ImageError("open ARM read-only builder accepted invalid input")
        feature_header = struct.pack("<8I", 5, 0, host_ctba & 0xFFFFFFFF,
                                     host_ctba >> 32, 0, 0, 0, 0)
        feature_fis = bytes((0x27, 0x80, 0xEF, 0x03)) + b"\x00" * 16
        feature_table = bytearray(table)
        feature_table[:20] = feature_fis
        feature_result = run(
            image, 9_000_000,
            port0_sstatus=0x133, fast_delays=True, experimental_sata_io=True,
            synthetic_host_ghc_sequence=(0x80000000, 0x80000001),
            synthetic_host_port_command_issue=1,
            synthetic_frontend_worker_once=True,
            synthetic_backend_task_drain_once=True,
            synthetic_host_command_list=(host_clb, feature_header),
            synthetic_host_command_table=(host_ctba, bytes(feature_table)),
        )
        feature_issues = [event for event in feature_result["port0_command_issues"]
                          if event.get("pc") == "0x00004BAC"]
        if len(feature_issues) != 4 or feature_issues[-1]["ata_command"] != "0xEF":
            raise ImageError("stock host SET FEATURES slot missing")
        feature_fetched = bytearray(feature_header)
        feature_fetched[16:32] = feature_fis[:16]
        status, actual = arm_slot(bytes(feature_fetched), program,
                                  entries["host_build_basic_slot"])
        if status != 0 or actual != bytes.fromhex(feature_issues[-1]["command_slot_raw"]):
            raise ImageError("open ARM SET FEATURES slot differs from stock physical slot")
        for opcode, write_bit, prdt_count in (
                (0x35, True, 1), (0xEA, False, 0),
                (0x25, False, 2), (0x35, True, 2),
                (0x06, True, 1), (0xB0, False, 1),
                (0xE7, False, 0), (0xC8, False, 1),
                (0xCA, True, 1), (0xF5, False, 0)):
            stock = probe(image, opcode, write_bit, prdt_count)
            issues = stock["stock_host_issues"]
            if len(issues) != 4 or issues[-1]["ata_command"] != f"0x{opcode:02X}":
                raise ImageError(f"stock host command {opcode:02X}/{prdt_count} slot missing")
            if opcode in (0xEA, 0xE7, 0xF5):
                port = struct.unpack("<12I", bytes.fromhex(
                    stock["host_registers"]["0x80002910"]))
                if (port[0], port[9], port[10]) != (8, 1, 0xFFFFFFFE):
                    raise ImageError(f"stock host {opcode:02X} completion changed")
            command_fetched = bytearray(header)
            flags = 5 | (0x40 if write_bit else 0) | (prdt_count << 16)
            struct.pack_into("<I", command_fetched, 0, flags)
            command_fis = bytearray(16)
            command_fis[0:3] = bytes((0x27, 0x80, opcode))
            command_fis[7] = 0x40
            command_fis[12] = 1
            command_fetched[16:32] = command_fis
            status, actual = arm_slot(bytes(command_fetched), program,
                                      entries["host_build_basic_slot"])
            if status != 0 or actual != bytes.fromhex(issues[-1]["command_slot_raw"]):
                raise ImageError(f"open ARM {opcode:02X}/{prdt_count} slot differs from stock physical slot")
            malformed = bytearray(command_fetched)
            malformed[0] ^= 0x40
            status, output = arm_slot(bytes(malformed), program,
                                      entries["host_build_basic_slot"])
            if status != 0xFFFFFFFE or output != b"\xCC" * 64:
                raise ImageError(f"open ARM {opcode:02X} accepted wrong write bit")
        print("open ARM IDENTIFY descriptor matches stock 64-byte backend slot")
        print("open ARM READ DMA EXT descriptor matches stock 64-byte backend slot")
        print("open ARM SET FEATURES 03 descriptor matches stock 64-byte backend slot")
        print("open ARM WRITE DMA EXT descriptor matches stock 64-byte backend slot")
        print("open ARM FLUSH CACHE EXT descriptor matches stock 64-byte backend slot")
        print("two-entry READ/WRITE PRDT headers match stock backend slots")
        print("DSM, SMART, legacy DMA, FLUSH and F5 descriptors match stock backend slots")
        print("write opcode, unaligned CTBA, and malformed FIS rejected without output")
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
