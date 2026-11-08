

"""Check the open virtual port-0 COMRESET release path in Unicorn."""

from __future__ import annotations

import struct
import subprocess

from build_c_stage import COMMON, FIRMWARE, ROOT
from inspect_image import ImageError


def main() -> None:
    from unicorn import UC_ARCH_ARM, UC_MODE_ARM, Uc
    from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_SP

    bin_dir = ROOT / "build" / "toolchain" / "bin"
    out = ROOT / "build" / "host-port-reset-test"
    out.mkdir(parents=True, exist_ok=True)
    elf = out / "host-port-reset.elf"
    raw = out / "host-port-reset.bin"
    subprocess.run([
        str(bin_dir / "arm-none-eabi-gcc.exe"), *COMMON,
        "-DOPEN9230_DMA_PROBE=1", "-std=c11", "-nostdlib",
        "-Wl,-Ttext=0x1000", "-Wl,-e,host_frontend_poll_port0_reset",
        str(FIRMWARE / "host_frontend.c"), str(FIRMWARE / "host_command.c"),
        "-lgcc", "-o", str(elf),
    ], check=True, capture_output=True, text=True)
    subprocess.run([str(bin_dir / "arm-none-eabi-objcopy.exe"), "-O", "binary",
                    str(elf), str(raw)], check=True, capture_output=True, text=True)
    symbols = subprocess.run([str(bin_dir / "arm-none-eabi-nm.exe"), "-n", str(elf)],
                             check=True, capture_output=True, text=True).stdout
    entry = next(int(line.split()[0], 16) for line in symbols.splitlines()
                 if line.split()[-1:] == ["host_frontend_poll_port0_reset"])
    reset_state = next(int(line.split()[0], 16) for line in symbols.splitlines()
                       if line.split()[-1:] == ["host_frontend_basic_reset_state"])
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in ((0x1000, 0x10000), (0x80002000, 0x2000),
                       (0x8000A000, 0x2000), (0x8000C000, 0x1000),
                       (0xD0020000, 0x1000)):
        uc.mem_map(base, size)
    uc.mem_write(0x1000, raw.read_bytes())
    uc.reg_write(UC_ARM_REG_SP, 0x11000)

    def put(address: int, value: int) -> None:
        uc.mem_write(address, struct.pack("<I", value))

    def get(address: int) -> int:
        return struct.unpack("<I", uc.mem_read(address, 4))[0]

    def call(address: int) -> int:
        uc.reg_write(UC_ARM_REG_LR, 0xF000)
        uc.reg_write(UC_ARM_REG_PC, address)
        uc.emu_start(address, 0xF000, count=10000)
        return uc.reg_read(UC_ARM_REG_R0)

    put(0x8000A928, 0x133)
    put(0x8000A924, 0x101)
    put(0x8000A920, 0x50)
    put(0x80002918, 0x7)
    put(0x80002924, 0xFFFFFFFF)
    put(0x80002928, 0)
    put(0x80002920, 0x7F)
    call(reset_state)
    if call(entry) != 0:
        raise ImageError("port reset fired before SCTL assertion")
    put(0x8000292C, 1)
    if call(entry) != 0:
        raise ImageError("port reset fired during SCTL assertion")
    put(0x8000292C, 0)
    if (call(entry) != 1 or get(0x80002924) != 0x101 or
            get(0x80002928) != 0x133 or get(0x80002920) != 0x50 or
            get(0x80002934) != 0xFFFFFFFF or get(0x80003010) != 0x1000):
        raise ImageError("virtual port state was not restored after COMRESET")
    if call(entry) != 0:
        raise ImageError("COMRESET release fired twice")


    put(0x80002924, 0xFFFFFFFF)
    put(0x80002928, 0)
    put(0x80002920, 0x7F)
    put(0x80002804, 0x80000002)
    put(0x80003010, 0)
    call(reset_state)
    put(0x80003010, 0x1000)
    if call(entry) != 1 or get(0x80002924) != 0x101 or get(0x80002928) != 0x133:
        raise ImageError("latched COMRESET interrupt did not restore the virtual port")
    print("open virtual port-0 COMRESET release restores link, signature and task file")


if __name__ == "__main__":
    main()
