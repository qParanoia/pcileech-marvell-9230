

"""Compile the freestanding ARMv5TE C stage and place it in the local template."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from image_builder import replace_code1_entry, disable_option_rom
from inspect_image import ImageError


ROOT = Path(__file__).resolve().parent.parent
FIRMWARE = ROOT / "firmware"
COMMON = [
    "-march=armv5te", "-marm", "-mfloat-abi=soft", "-ffreestanding",
    "-fno-builtin", "-fno-pic", "-fno-stack-protector",
    "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
    "-fdata-sections", "-ffunction-sections", "-O2", "-Wall", "-Wextra", "-Werror",
]


def invoke(args: list[str]) -> str:
    try:
        return subprocess.run(args, check=True, text=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise ImageError(f"ARM toolchain command failed: {detail}") from exc


def compile_stage(toolchain: Path, build_dir: Path, cflags: tuple[str, ...] = ()) -> tuple[bytes, dict[str, int]]:
    bin_dir = toolchain / "bin"
    gcc = str(bin_dir / "arm-none-eabi-gcc.exe")
    objcopy = str(bin_dir / "arm-none-eabi-objcopy.exe")
    nm = str(bin_dir / "arm-none-eabi-nm.exe")
    for path in (gcc, objcopy, nm):
        if not Path(path).is_file():
            raise ImageError(f"missing ARM toolchain program: {path}")
    build_dir.mkdir(parents=True, exist_ok=True)
    crt = build_dir / "crt0.o"
    stage = build_dir / "stage.o"
    sata = build_dir / "sata_port0.o"
    punit = build_dir / "punit.o"
    monitor = build_dir / "monitor.o"
    host_frontend = build_dir / "host_frontend.o"
    host_command = build_dir / "host_command.o"
    console_identify = build_dir / "console_identify.o"
    ch568_diag = build_dir / "ch568_diag.o"
    elf = build_dir / "stage.elf"
    raw = build_dir / "stage.raw.bin"
    invoke([gcc, *COMMON, "-c", str(FIRMWARE / "crt0.S"), "-o", str(crt)])
    invoke([gcc, *COMMON, *cflags, "-std=c11", "-c", str(FIRMWARE / "stage.c"), "-o", str(stage)])
    invoke([gcc, *COMMON, "-std=c11", "-c", str(FIRMWARE / "sata_port0.c"), "-o", str(sata)])
    invoke([gcc, *COMMON, "-std=c11", "-c", str(FIRMWARE / "punit.c"), "-o", str(punit)])
    invoke([gcc, *COMMON, *cflags, "-std=c11", "-c", str(FIRMWARE / "monitor.c"), "-o", str(monitor)])
    invoke([gcc, *COMMON, *cflags, "-std=c11", "-c", str(FIRMWARE / "host_frontend.c"), "-o", str(host_frontend)])
    invoke([gcc, *COMMON, "-std=c11", "-c", str(FIRMWARE / "host_command.c"), "-o", str(host_command)])
    invoke([gcc, *COMMON, "-std=c11", "-c", str(FIRMWARE / "console_identify.c"), "-o", str(console_identify)])
    invoke([gcc, *COMMON, *cflags, "-std=c11", "-c", str(FIRMWARE / "ch568_diag.c"), "-o", str(ch568_diag)])
    invoke([
        gcc, "-march=armv5te", "-marm", "-mfloat-abi=soft", "-nostdlib",
        "-Wl,--gc-sections", "-Wl,--build-id=none", f"-Wl,-Map={build_dir / 'stage.map'}",
        "-T", str(FIRMWARE / "stage.ld"), str(crt), str(stage), str(sata), str(punit), str(monitor), str(host_frontend), str(host_command), str(console_identify), str(ch568_diag), "-lgcc", "-o", str(elf),
    ])
    invoke([objcopy, "-O", "binary", str(elf), str(raw)])
    symbols = {}
    for line in invoke([nm, "-n", str(elf)]).splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    payload = raw.read_bytes()
    if not payload or len(payload) > 0x15AA4:
        raise ImageError(f"unexpected open stage payload length: {len(payload)}")
    if symbols.get("_start") != 0 or "stage_idle" not in symbols:
        raise ImageError("open stage entry or idle symbol missing")
    return payload, symbols


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--toolchain", type=Path, default=ROOT / "build" / "toolchain")
    parser.add_argument("--no-option-rom", action="store_true",
                        help="diagnostic basic-boot-probe: erase the legacy x86 Option ROM region")
    parser.add_argument("--ch568-diagnostics", action="store_true",
                        help="reserve SATA port 2 for fixed CH568 PING/STATUS diagnostics")
    variant = parser.add_mutually_exclusive_group()
    variant.add_argument("--experimental-frontend", action="store_true",
                         help="include the UART-armed host IDENTIFY experiment")
    variant.add_argument("--static-board-test", action="store_true",
                         help="run a fixed read-only board diagnostic without UART commands")
    variant.add_argument("--static-boot-test", action="store_true",
                         help="run continuous static read-only host service and UART trace")
    variant.add_argument("--basic-boot", action="store_true",
                         help="boot with a static one-port basic AHCI service")
    variant.add_argument("--basic-boot-probe", "--basic-boot-v13", action="store_true",
                         help="basic boot with read-only host IDENTIFY DMA telemetry")
    args = parser.parse_args()
    if args.no_option_rom and not args.basic_boot_probe:
        parser.error("--no-option-rom requires --basic-boot-probe")
    if args.ch568_diagnostics and not args.basic_boot_probe:
        parser.error("--ch568-diagnostics requires --basic-boot-probe")
    if args.template.resolve() == args.output.resolve():
        parser.error("output must differ from template")
    try:
        if args.basic_boot_probe:
            cflags = ("-DOPEN9230_STATIC_BOARD_TEST=1", "-DOPEN9230_STATIC_BOOT_TEST=1",
                      "-DOPEN9230_BASIC_BOOT=1", "-DOPEN9230_DMA_PROBE=1",
                      "-DSTATIC_TEST_POLL_BUDGET=128u")
            build_dir = ROOT / "build" / "c-stage-basic-boot-probe"
        elif args.basic_boot:
            cflags = ("-DOPEN9230_STATIC_BOARD_TEST=1", "-DOPEN9230_STATIC_BOOT_TEST=1",
                      "-DOPEN9230_BASIC_BOOT=1", "-DSTATIC_TEST_POLL_BUDGET=128u")
            build_dir = ROOT / "build" / "c-stage-basic-boot"
        elif args.static_boot_test:
            cflags = ("-DOPEN9230_STATIC_BOARD_TEST=1", "-DOPEN9230_STATIC_BOOT_TEST=1")
            build_dir = ROOT / "build" / "c-stage-static-boot-test"
        elif args.static_board_test:
            cflags = ("-DOPEN9230_STATIC_BOARD_TEST=1",)
            build_dir = ROOT / "build" / "c-stage-static-board-test"
        elif args.experimental_frontend:
            cflags = ("-DOPEN9230_EXPERIMENTAL_FRONTEND=1",)
            build_dir = ROOT / "build" / "c-stage-experimental-frontend"
        else:
            cflags = ()
            build_dir = ROOT / "build" / "c-stage"
        if args.no_option_rom:
            cflags += ("-DOPEN9230_NO_OPTION_ROM=1",)
            build_dir = ROOT / "build" / "c-stage-basic-boot-probe-no-option-rom"
        if args.ch568_diagnostics:
            cflags += ("-DOPEN9230_CH568_DIAGNOSTICS=1",)
            build_dir = ROOT / "build" / "c-stage-ch568-diagnostics-v22"
        payload, symbols = compile_stage(args.toolchain.resolve(), build_dir, cflags=cflags)
        image, start = replace_code1_entry(args.template.read_bytes(), payload)
        if args.no_option_rom:
            image = disable_option_rom(image)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(image)
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"output: {args.output.resolve()}")
    print(f"open C stage: {len(payload)} bytes at SPI 0x{start:X}")
    print(f"stage_idle: 0x{symbols['stage_idle']:08X}")
    print(f"SHA-256: {hashlib.sha256(image).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
