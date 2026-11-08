

"""Build the relocatable-in-source, fixed-address UART host probe payload."""

from __future__ import annotations

import argparse
import hashlib
import zlib
from pathlib import Path

from build_c_stage import COMMON, ROOT, invoke
from inspect_image import ImageError


def build(toolchain: Path, output: Path) -> bytes:
    bin_dir = toolchain / "bin"
    gcc = str(bin_dir / "arm-none-eabi-gcc.exe")
    objcopy = str(bin_dir / "arm-none-eabi-objcopy.exe")
    nm = str(bin_dir / "arm-none-eabi-nm.exe")
    for program in (gcc, objcopy, nm):
        if not Path(program).is_file():
            raise ImageError(f"missing ARM toolchain program: {program}")
    build_dir = ROOT / "build" / "host-probe"
    build_dir.mkdir(parents=True, exist_ok=True)
    source = ROOT / "payloads" / "host_probe.c"
    linker = ROOT / "payloads" / "payload.ld"
    obj = build_dir / "host_probe.o"
    elf = build_dir / "host_probe.elf"
    invoke([gcc, *COMMON, "-std=c11", "-c", str(source), "-o", str(obj)])
    invoke([
        gcc, "-march=armv5te", "-marm", "-mfloat-abi=soft", "-nostdlib",
        "-Wl,--gc-sections", "-Wl,--build-id=none", "-T", str(linker),
        str(obj), "-lgcc", "-o", str(elf),
    ])
    symbols = {}
    for line in invoke([nm, "-n", str(elf)]).splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    if symbols.get("payload_entry") != 0x30070000:
        raise ImageError("host probe entry is not at the upload address")
    output.parent.mkdir(parents=True, exist_ok=True)
    invoke([objcopy, "-O", "binary", str(elf), str(output)])
    data = output.read_bytes()
    if not 4 <= len(data) <= 0x10000 or len(data) & 3:
        raise ImageError(f"invalid host probe length: {len(data)}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, default=ROOT / "build" / "toolchain")
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "host-probe.payload.bin")
    args = parser.parse_args()
    try:
        data = build(args.toolchain.resolve(), args.output.resolve())
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"output: {args.output.resolve()}")
    print(f"bytes: {len(data)}")
    print(f"CRC-32: {zlib.crc32(data):08X}")
    print(f"SHA-256: {hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
