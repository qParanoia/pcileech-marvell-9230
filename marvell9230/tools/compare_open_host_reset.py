

"""Compare the open ARM host-reset register sequence with stock 88.bin."""

from __future__ import annotations

import argparse
import struct
import subprocess
from pathlib import Path

from build_c_stage import COMMON, FIRMWARE, ROOT
from emulate_stock import run
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary


def compile_reset(toolchain: Path) -> tuple[bytes, int]:
    bin_dir = toolchain / "bin"
    gcc = bin_dir / "arm-none-eabi-gcc.exe"
    objcopy = bin_dir / "arm-none-eabi-objcopy.exe"
    nm = bin_dir / "arm-none-eabi-nm.exe"
    out = ROOT / "build" / "host-reset-test"
    out.mkdir(parents=True, exist_ok=True)
    elf = out / "host_reset.elf"
    raw = out / "host_reset.bin"
    try:
        subprocess.run([str(gcc), *COMMON, "-std=c11", "-nostdlib",
                        "-Wl,-Ttext=0x1000", "-Wl,--gc-sections", "-Wl,-e,host_frontend_reset_registers",
                        str(FIRMWARE / "host_frontend.c"),
                        str(FIRMWARE / "host_command.c"), "-lgcc", "-o", str(elf)],
                       check=True, text=True, capture_output=True)
        subprocess.run([str(objcopy), "-O", "binary", str(elf), str(raw)],
                       check=True, text=True, capture_output=True)
        symbols = subprocess.run([str(nm), "-n", str(elf)], check=True,
                                 text=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise ImageError(f"ARM reset compilation failed: {detail}") from exc
    matches = [int(line.split()[0], 16) for line in symbols.splitlines()
               if line.split()[-1:] == ["host_frontend_reset_registers"]]
    if len(matches) != 1:
        raise ImageError("ARM host reset symbol missing")
    program = raw.read_bytes()
    if len(program) > 4096:
        raise ImageError("ARM host reset fixture exceeds code page")
    return program, matches[0]


def run_open(program: bytes, entry: int, *, linked_ssd: bool = False) -> tuple[int, list[tuple[int, int]]]:
    from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
    from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP

    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x1000, 0x1000)
    uc.mem_map(0x30000, 0x1000)
    uc.mem_map(0x80002000, 0x2000)
    uc.mem_write(0x1000, program)

    generic = (0x00140006, 0xFFFFFFFF, 0, 0x7F)
    console = (0x00100006, 0xEB140101, 0x113, 0x50)
    ssd = (0x00140006, 0x00000101, 0x00000133, 0x50)
    ports = b"".join(struct.pack("<4I", *(console if i == 7 else
                                             ssd if i == 0 and linked_ssd else generic))
                     for i in range(8))
    uc.mem_write(0x30000, ports)
    uc.mem_write(0x80002804, struct.pack("<I", 0x80000001))
    uc.reg_write(UC_ARM_REG_SP, 0x31000)
    uc.reg_write(UC_ARM_REG_LR, 0xF000)
    uc.reg_write(UC_ARM_REG_R0, 0x30000)
    uc.reg_write(UC_ARM_REG_R1, 8)
    writes: list[tuple[int, int]] = []

    def record(_uc: Uc, _access: int, address: int, size: int,
               value: int, _user: object) -> None:
        if size == 4 and 0x80002800 <= address < 0x80003100:
            writes.append((address, value & 0xFFFFFFFF))

    uc.hook_add(UC_HOOK_MEM_WRITE, record)
    uc.emu_start(entry, 0xF000, count=20000)
    return uc.reg_read(UC_ARM_REG_R0), writes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--toolchain", type=Path, default=ROOT / "build" / "toolchain")
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("this comparison requires the analyzed stock 88.bin")
        program, entry = compile_reset(args.toolchain.resolve())
        for linked_ssd in (False, True):
            if linked_ssd:
                stock = run(image, 6_000_000, capture_mmio=True,
                            port0_sstatus=0x133, fast_delays=True,
                            experimental_sata_io=True,
                            synthetic_host_ghc_sequence=(0x80000000, 0x80000001))
            else:
                stock = run(image, 3_000_000, capture_mmio=True,
                            inject_irq_at_pc=0xE8, injected_irq_pending=0x100,
                            initial_mmio={0x80002808: 2},
                            host_ghc_on_debug_irq=0x80000001)
            host_writes = [(int(e["addr"], 16), int(e["value"], 16))
                           for e in stock["mmio_trace"] if e["op"] == "write"
                           and 0x80002800 <= int(e["addr"], 16) < 0x80003100]
            first = host_writes.index((0x80002800, 0xC0309F07))
            expected = host_writes[first:first + 118]
            if len(expected) != 118 or expected[-1] != (0x80002804, 0):
                raise ImageError("stock host reset trace boundary has changed")


            expected[0] = (0x80002800, 0x80309F07)
            count, actual = run_open(program, entry, linked_ssd=linked_ssd)
            if count != 8 or actual != expected:
                mismatch = next(((i, a, b) for i, (a, b) in enumerate(zip(actual, expected))
                                 if a != b), None)
                raise ImageError(f"open reset differs from stock ({'ssd' if linked_ssd else 'empty'}): "
                                 f"count={count}, writes={len(actual)}/{len(expected)}, first={mismatch}")
    except (OSError, ImageError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print("open ARM host reset: 117 stock writes match; CAP advertises 32 slots without NCQ")
    print("this comparison covers register reset, not hardware DMA or IRQ timing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
