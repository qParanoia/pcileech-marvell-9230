

"""Compare open ARM frontend IRQ setup with stock 88SE9230 MMIO writes."""

from __future__ import annotations

import argparse
import struct
import subprocess
from pathlib import Path

from build_c_stage import COMMON, FIRMWARE, ROOT
from emulate_stock import run
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary


def compile_function(toolchain: Path) -> tuple[bytes, dict[str, int]]:
    bin_dir = toolchain / "bin"
    gcc = bin_dir / "arm-none-eabi-gcc.exe"
    objcopy = bin_dir / "arm-none-eabi-objcopy.exe"
    nm = bin_dir / "arm-none-eabi-nm.exe"
    out = ROOT / "build" / "host-frontend-test"
    out.mkdir(parents=True, exist_ok=True)
    elf = out / "host_frontend.elf"
    raw = out / "host_frontend.bin"
    try:
        subprocess.run([str(gcc), *COMMON, "-std=c11", "-nostdlib",
                        "-Wl,-Ttext=0x1000", "-Wl,-e,host_frontend_enable_irqs",
                        str(FIRMWARE / "host_frontend.c"),
                        str(FIRMWARE / "host_command.c"), "-lgcc", "-o", str(elf)],
                       check=True, text=True, capture_output=True)
        subprocess.run([str(objcopy), "-O", "binary", str(elf), str(raw)],
                       check=True, text=True, capture_output=True)
        symbols = subprocess.run([str(nm), "-n", str(elf)], check=True,
                                 text=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise ImageError(f"ARM frontend compilation failed: {detail}") from exc
    addresses = {fields[2]: int(fields[0], 16) for line in symbols.splitlines()
                 if len(fields := line.split()) == 3}
    required = ("host_frontend_enable_irqs", "host_frontend_init_dma_registers",
                "host_frontend_enable_autofetch")
    if any(name not in addresses for name in required):
        raise ImageError("ARM frontend function symbol missing")
    return raw.read_bytes(), addresses


def open_writes(program: bytes, entry: int, reported_count: int) -> tuple[int, list[tuple[int, int]]]:
    from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
    from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_SP

    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x1000, 0x1000)
    uc.mem_map(0x30000, 0x1000)
    uc.mem_map(0x80002000, 0x2000)
    uc.mem_write(0x1000, program)
    uc.mem_write(0x80002800, struct.pack("<I", reported_count))
    uc.reg_write(UC_ARM_REG_SP, 0x31000)
    uc.reg_write(UC_ARM_REG_LR, 0xF000)
    writes: list[tuple[int, int]] = []

    def record(_uc: Uc, _access: int, address: int, size: int,
               value: int, _user: object) -> None:
        if size == 4 and 0x80003008 <= address < 0x80003050:
            writes.append((address, value & 0xFFFFFFFF))

    uc.hook_add(UC_HOOK_MEM_WRITE, record)
    uc.emu_start(entry, 0xF000, count=2000)
    return uc.reg_read(UC_ARM_REG_R0), writes


def open_dma_writes(program: bytes, dma_entry: int, auto_entry: int,
                    ports: tuple[int, ...]) -> list[tuple[int, int]]:
    from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
    from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_SP

    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x1000, 0x1000)
    uc.mem_map(0x30000, 0x1000)
    uc.mem_map(0x8000C000, 0x1000)
    uc.mem_write(0x1000, program)
    uc.reg_write(UC_ARM_REG_SP, 0x31000)
    writes: list[tuple[int, int]] = []

    def record(_uc: Uc, _access: int, address: int, size: int,
               value: int, _user: object) -> None:
        if size == 4 and 0x8000C000 <= address < 0x8000C060:
            writes.append((address, value & 0xFFFFFFFF))

    uc.hook_add(UC_HOOK_MEM_WRITE, record)
    uc.reg_write(UC_ARM_REG_LR, 0xF000)
    uc.emu_start(dma_entry, 0xF000, count=2000)
    for port in ports:
        uc.reg_write(UC_ARM_REG_R0, port)
        uc.reg_write(UC_ARM_REG_LR, 0xF000)
        uc.emu_start(auto_entry, 0xF000, count=2000)
    return writes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--toolchain", type=Path, default=ROOT / "build" / "toolchain")
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("this comparison requires the analyzed stock 88.bin")
        stock = run(image, 2_000_000, capture_mmio=True)
        expected = [(int(event["addr"], 16), int(event["value"], 16))
                    for event in stock["mmio_trace"]
                    if event["op"] == "write" and
                    0x80003008 <= int(event["addr"], 16) < 0x80003050]
        if len(expected) != 18:
            raise ImageError("stock frontend IRQ sequence has changed")
        program, symbols = compile_function(args.toolchain.resolve())
        entry = symbols["host_frontend_enable_irqs"]
        count, actual = open_writes(program, entry, 7)
        if count != 8 or actual != expected:
            raise ImageError("open ARM frontend IRQ writes differ from stock")
        capped_count, capped_writes = open_writes(program, entry, 31)
        if capped_count != 8 or capped_writes != expected:
            raise ImageError("open ARM frontend did not bound the virtual-port count")
        dma_expected = [(int(event["addr"], 16), int(event["value"], 16))
                        for event in stock["mmio_trace"]
                        if event["op"] == "write" and
                        0x300437E4 <= int(event["pc"], 16) <= 0x30043870]
        if len(dma_expected) != 18 or dma_expected[-1] != (0x8000C044, 0xD):
            raise ImageError("stock DMA initialization trace has changed")
        dma_entry = symbols["host_frontend_init_dma_registers"]
        auto_entry = symbols["host_frontend_enable_autofetch"]
        dma_actual = open_dma_writes(program, dma_entry, auto_entry, (7,))
        if dma_actual != dma_expected + [(0x8000C044, 0x80D)]:
            raise ImageError("open DMA/console auto-fetch writes differ from stock")
        stock_ssd = run(image, 2_000_000, port0_sstatus=0x133,
                        fast_delays=True, experimental_sata_io=True,
                        capture_mmio=True)
        stock_auto = [(int(event["addr"], 16), int(event["value"], 16))
                      for event in stock_ssd["mmio_trace"]
                      if event["op"] == "write" and event["addr"] == "0x8000C044"]
        ssd_auto = open_dma_writes(program, dma_entry, auto_entry, (0, 7))
        if (stock_auto != [(0x8000C044, 0xD), (0x8000C044, 0x1D),
                           (0x8000C044, 0x81D)] or
                ssd_auto != dma_expected + stock_auto[1:]):
            raise ImageError("open port-0/console auto-fetch bit order differs")
        print("open ARM frontend: 18 MMIO writes match stock IRQ setup for 8 virtual ports")
        print("reported count above 8 is bounded to the supported port bank")
        print("18 DMA-init writes and console auto-fetch match stock; port-0 bit order checked")
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
