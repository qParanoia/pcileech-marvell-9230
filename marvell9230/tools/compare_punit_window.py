

"""Compare the open PCIe CPU-window mapper with stock CODE1."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from build_c_stage import COMMON, FIRMWARE, ROOT
from inspect_image import ImageError, image_summary
from image_builder import REFERENCE_SHA256


def compile_open(toolchain: Path) -> tuple[bytes, int]:
    out = ROOT / "build" / "punit-window-test"
    out.mkdir(parents=True, exist_ok=True)
    source = out / "window_test.c"
    elf = out / "window_test.elf"
    raw = out / "window_test.bin"
    source.write_text(
        '#include "punit_window.h"\n'
        'volatile unsigned char *test_map(unsigned low, unsigned high, '
        'unsigned size, unsigned index) {\n'
        '  return punit_window_map(0xD0020000u + index * 0x10u, '
        'index ? 0x50000000u : 0x40000000u, low, high, size, 1000u);\n'
        '}\n',
        encoding="ascii",
    )
    bin_dir = toolchain / "bin"
    gcc = bin_dir / "arm-none-eabi-gcc.exe"
    objcopy = bin_dir / "arm-none-eabi-objcopy.exe"
    nm = bin_dir / "arm-none-eabi-nm.exe"
    try:
        subprocess.run(
            [str(gcc), *COMMON, "-std=c11", "-nostdlib", f"-I{FIRMWARE}",
             "-Wl,-Ttext=0x1000", "-Wl,-e,test_map", str(source), "-lgcc",
             "-o", str(elf)],
            check=True, capture_output=True, text=True,
        )
        subprocess.run([str(objcopy), "-O", "binary", str(elf), str(raw)],
                       check=True, capture_output=True, text=True)
        symbols = subprocess.run([str(nm), "-n", str(elf)], check=True,
                                 capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise ImageError(f"PUNIT window test compilation failed: {detail}") from exc
    entry = next(int(line.split()[0], 16) for line in symbols.splitlines()
                 if line.split()[-1:] == ["test_map"])
    return raw.read_bytes(), entry


def execute(program: bytes, entry: int, low: int, high: int,
            size: int, index: int) -> tuple[int, tuple[int, int, int, int]]:
    from unicorn import UC_ARCH_ARM, UC_MODE_ARM, Uc
    from unicorn.arm_const import (
        UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
        UC_ARM_REG_R3, UC_ARM_REG_SP,
    )

    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0, 0x20000)
    uc.mem_map(0xD0020000, 0x1000)
    uc.mem_write(0, program)
    uc.reg_write(UC_ARM_REG_R0, low)
    uc.reg_write(UC_ARM_REG_R1, high)
    uc.reg_write(UC_ARM_REG_R2, size)
    uc.reg_write(UC_ARM_REG_R3, index)
    uc.reg_write(UC_ARM_REG_SP, 0x1F000)
    uc.reg_write(UC_ARM_REG_LR, 0xF000)
    uc.emu_start(entry, 0xF000, count=10000)
    base = 0xD0020000 + index * 0x10
    words = tuple(int.from_bytes(uc.mem_read(base + offset, 4), "little")
                  for offset in (0, 4, 8, 12))
    return uc.reg_read(UC_ARM_REG_R0), words


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--toolchain", type=Path,
                        default=ROOT / "build" / "toolchain")
    args = parser.parse_args()
    image = args.image.read_bytes()
    if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
        raise SystemExit("error: comparison requires the analyzed stock 88.bin")

    summary = image_summary(image)
    code1 = summary["segments"][0]
    source = int(code1["spi_source"], 16)
    length = int(code1["size"], 16)
    stock = bytearray(0x20000)
    stock[:length] = image[source:source + length]
    opened, open_entry = compile_open(args.toolchain)

    cases = (
        (0x12340020, 0x00000001, 16, 1),
        (0x1234FFF0, 0x00000001, 32, 1),
        (0x1235FFF0, 0x00000002, 32, 1),
        (0xABCDFE00, 0x00000003, 0x300, 0),
    )
    for case in cases:
        stock_result = execute(bytes(stock), 0x1830, *case)
        open_result = execute(b"\0" * 0x1000 + opened, open_entry, *case)
        if stock_result != open_result:
            raise SystemExit(
                f"error: window mapper differs for {case!r}: "
                f"stock={stock_result!r} open={open_result!r}"
            )
    print("open PCIe CPU-window mapper matches stock for fixed and crossing ranges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
