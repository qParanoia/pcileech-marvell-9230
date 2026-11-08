

"""Emulate the diagnostic with fixture MMIO values and verify its UART output."""

from __future__ import annotations

import struct
import sys

from build_diag import assemble_diag


UART0 = 0xD0072000
EXPECTED = (
    b"OPEN9230 DIAG\r\n"
    b"CHIP=92301B4B\r\n"
    b"STRAP=0000002F\r\n"
    b"SPI0=A5A5A5A5\r\n"
)


def main() -> int:
    from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
    from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_SP

    payload = assemble_diag()
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in [
        (0x00000000, 0x10000),
        (0x04000000, 0x10000),
        (0xD0030000, 0x1000),
        (0xD0071000, 0x1000),
        (0xD0072000, 0x1000),
        (0xF8064000, 0x1000),
    ]:
        uc.mem_map(base, size)
    uc.mem_write(0, payload)
    uc.mem_write(0xD0030000, struct.pack("<I", 0x92301B4B))
    uc.mem_write(0xD0071054, struct.pack("<I", 0x0000002F))
    uc.mem_write(0xF8064000, struct.pack("<I", 0xA5A5A5A5))
    uc.mem_write(UART0 + 0x14, b"\x20")
    uc.reg_write(UC_ARM_REG_PC, 0)
    uc.reg_write(UC_ARM_REG_SP, 0x04004000)

    output = bytearray()
    dlab = False

    def on_write(emu: Uc, access: int, address: int, size: int, value: int, user: object) -> None:
        nonlocal dlab
        if address == UART0 + 0xC:
            dlab = bool(value & 0x80)
        elif address == UART0 and not dlab:
            output.append(value & 0xFF)
            if len(output) >= len(EXPECTED):
                emu.emu_stop()

    uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
    uc.emu_start(0, 0x1000, count=20000)
    marker = struct.unpack("<I", uc.mem_read(0x04001000, 4))[0]
    if bytes(output) != EXPECTED:
        raise AssertionError(f"UART output mismatch: {bytes(output)!r}")
    if marker != 0x9230B007:
        raise AssertionError(f"RAM marker mismatch: 0x{marker:08x}")
    sys.stdout.buffer.write(output)
    print("emulation: UART output and RAM marker verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
