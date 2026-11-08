

"""Check the serialized open host READ path without a board image."""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path

from build_c_stage import COMMON, FIRMWARE, ROOT
from inspect_image import ImageError


def main() -> int:
    from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
    from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_SP

    toolchain = ROOT / "build" / "toolchain" / "bin"
    out = ROOT / "build" / "host-read-only-test"
    out.mkdir(parents=True, exist_ok=True)
    elf = out / "host_read_only.elf"
    raw = out / "host_read_only.bin"
    gcc = toolchain / "arm-none-eabi-gcc.exe"
    objcopy = toolchain / "arm-none-eabi-objcopy.exe"
    nm = toolchain / "arm-none-eabi-nm.exe"
    try:
        subprocess.run([str(gcc), *COMMON, "-std=c11", "-nostdlib",
                        "-Wl,-Ttext=0x1000", "-Wl,-e,host_frontend_poll_basic",
                        str(FIRMWARE / "host_frontend.c"),
                        str(FIRMWARE / "host_command.c"), "-lgcc", "-o", str(elf)],
                       check=True, capture_output=True, text=True)
        subprocess.run([str(objcopy), "-O", "binary", str(elf), str(raw)],
                       check=True, capture_output=True, text=True)
        symbols = subprocess.run([str(nm), "-n", str(elf)],
                                 check=True, capture_output=True, text=True).stdout
        entry = next(int(line.split()[0], 16) for line in symbols.splitlines()
                     if line.split()[-1:] == ["host_frontend_poll_basic"])
        opcode_entry = next(int(line.split()[0], 16) for line in symbols.splitlines()
                            if line.split()[-1:] == ["host_frontend_basic_opcode"])
        program = raw.read_bytes()
        uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        uc.mem_map(0x1000, 0x10000)
        uc.mem_map(0x30000000, 0x1000)
        uc.mem_map(0x30003000, 0x1000)
        uc.mem_map(0x3006B000, 0x1000)
        uc.mem_map(0x30067000, 0x1000)
        uc.mem_map(0x80002000, 0x2000)
        uc.mem_map(0x8000A000, 0x2000)
        uc.mem_map(0x8000C000, 0x1000)
        uc.mem_write(0x1000, program)
        uc.reg_write(UC_ARM_REG_SP, 0x11000)
        completion_writes: list[tuple[int, int]] = []
        fis_at_trigger: list[bytes] = []

        def record(_uc: Uc, _access: int, address: int, size: int,
                   value: int, _user: object) -> None:
            if size == 4 and address in (0x80002934, 0x8000C084,
                                         0x80002920, 0x80002938,
                                         0x80002910, 0x80002808):
                completion_writes.append((address, value & 0xFFFFFFFF))
                if address == 0x8000C084:
                    fis_at_trigger.append(bytes(_uc.mem_read(0x30003020, 16)))

        uc.hook_add(UC_HOOK_MEM_WRITE, record)

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
        put(0x8000C060, 1)
        put(0x80002938, 1)
        completion_writes.clear()
        header = struct.pack("<4I", 0x00010005, 0, 0x10002000, 1)
        read_fis = bytes((0x27, 0x80, 0x25, 0, 0, 0, 0, 0x40,
                          0, 0, 0, 0, 1, 0, 0, 0))
        uc.mem_write(0x30000000, header + read_fis)
        if call(entry) != 1 or get(0x8000A938) != 1 or call(opcode_entry) != 0x25:
            raise ImageError("READ DMA EXT did not reach backend slot 0")
        slot = bytes(uc.mem_read(0x3006B000, 64))
        if slot[:4] != header[:4] or get(0x3006B008) != 0x10002004 or slot[0x20:0x30] != read_fis:
            raise ImageError("READ DMA EXT backend descriptor differs")
        put(0x8000A938, 0)
        put(0x8000A910, 1)
        if call(entry) != 2 or get(0x80002938) != 0xFFFFFFFE or get(0x80002910) != 8 or get(0x8000C084) != 1 or get(0x80002808) != 1:
            raise ImageError("READ DMA EXT frontend completion differs")
        if completion_writes != [(0x80002934, 1), (0x8000C084, 1),
                                 (0x80002920, 0x50), (0x80002938, 0xFFFFFFFE),
                                 (0x80002910, 8), (0x80002808, 1)]:
            raise ImageError(f"READ completion register order differs: {completion_writes!r}")


        put(0x80002938, 1)
        if call(entry) != 1 or get(0x8000A938) != 1:
            raise ImageError("identical READ was not reissued")
        put(0x8000A938, 0)
        put(0x8000A910, 1)
        if call(entry) != 2 or get(0x80002938) != 0xFFFFFFFE:
            raise ImageError("identical READ did not complete")


        feature_header = struct.pack("<4I", 5, 0, 0x10002000, 1)
        feature_fis = bytes((0x27, 0x80, 0xEF, 0x03)) + b"\x00" * 12
        uc.mem_write(0x30000000, feature_header + feature_fis)
        put(0x80002938, 1)
        if call(entry) != 1 or call(opcode_entry) != 0xEF or get(0x8000A938) != 1:
            raise ImageError("back-to-back SET FEATURES did not issue")
        put(0x8000A938, 0)
        put(0x8000A910, 1)
        uc.mem_write(0x30067040, bytes((0x34, 0x40, 0x50)) + bytes(13))
        if call(entry) != 2 or get(0x80002938) != 0xFFFFFFFE:
            raise ImageError("back-to-back SET FEATURES did not complete")
        if (get(0x30003020) != 0 or get(0x80002910) != 8 or
                completion_writes.count((0x80002934, 1)) != 3 or
                fis_at_trigger[-1][:4] != b"\x00\x00\x00\x00" or
                completion_writes[-6:] != [(0x80002934, 1),
                                           (0x8000C084, 1),
                                           (0x80002920, 0x50),
                                           (0x80002938, 0xFFFFFFFE),
                                           (0x80002910, 8), (0x80002808, 1)]):
            raise ImageError("SET FEATURES completion differs from stock")
        write_header = struct.pack("<4I", 0x00010045, 0, 0x10002000, 1)
        write_fis = bytes((0x27, 0x80, 0x35, 0, 0, 0, 0, 0x40,
                           0, 0, 0, 0, 1, 0, 0, 0))
        uc.mem_write(0x30000000, write_header + write_fis)
        put(0x80002938, 1)
        if call(entry) != 1 or call(opcode_entry) != 0x35 or get(0x8000A938) != 1:
            raise ImageError("WRITE DMA EXT did not issue")
        put(0x8000A938, 0)
        put(0x8000A910, 1)
        if call(entry) != 2 or get(0x80002938) != 0xFFFFFFFE or get(0x80002910) != 8:
            raise ImageError("WRITE DMA EXT did not complete")
        flush_header = struct.pack("<4I", 5, 0, 0x10002000, 1)
        flush_fis = bytes((0x27, 0x80, 0xEA, 0, 0, 0, 0, 0x40,
                           0, 0, 0, 0, 1, 0, 0, 0))
        uc.mem_write(0x30000000, flush_header + flush_fis)
        put(0x80002938, 1)
        if call(entry) != 1 or call(opcode_entry) != 0xEA or get(0x8000A938) != 1:
            raise ImageError("FLUSH CACHE EXT did not issue")
        put(0x8000A938, 0)
        put(0x8000A910, 1)
        if call(entry) != 2 or get(0x80002938) != 0xFFFFFFFE or get(0x80002910) != 8:
            raise ImageError("FLUSH CACHE EXT did not complete")


        freeze_fis = bytes((0x27, 0x80, 0xF5, 0, 0, 0, 0, 0x40,
                            0, 0, 0, 0, 1, 0, 0, 0))
        uc.mem_write(0x30000000, flush_header + freeze_fis)
        put(0x80002938, 1)
        if call(entry) != 1 or call(opcode_entry) != 0xF5 or get(0x8000A938) != 1:
            raise ImageError("SECURITY FREEZE LOCK did not reach backend")
        put(0x8000A938, 0)
        put(0x8000A910, 1)
        uc.mem_write(0x30067040, bytes((0x34, 0x40, 0x50)) + bytes(13))
        if (call(entry) != 2 or get(0x80002938) != 0xFFFFFFFE or
                get(0x80002910) != 8 or get(0x80002934) != 1 or
                fis_at_trigger[-1][:4] != b"\x00\x00\x00\x00"):
            raise ImageError("SECURITY FREEZE LOCK completion differs from stock")
        uc.mem_write(0x30000000, header + read_fis)
        put(0x80002938, 1)
        if call(entry) != 1 or get(0x8000A938) != 1:
            raise ImageError("error fixture READ did not issue")
        put(0x8000A938, 0)
        put(0x8000A910, 0x40000000)
        put(0x8000A920, 0x451)
        uc.mem_write(0x30067040, bytes((0x34, 0x40, 0x51, 0x04)) + bytes(12))
        if (call(entry) != 0xFFFFFFFD or get(0x80002938) != 0xFFFFFFFE or
                get(0x80002910) != 0x40000000 or get(0x80002920) != 0x451 or
                fis_at_trigger[-1][:4] != b"\x34\x40\x51\x04"):
            raise ImageError("backend ATA error left the host slot pending")
        put(0x8000C060, 0)
        if call(entry) != 0:
            raise ImageError("slot-0 rearm failed")
        put(0x8000C060, 1)
        put(0x8000A938, 0)
        put(0x80002938, 1)
        uc.mem_write(0x30000000, header + read_fis[:8] + b"\x00\x00\x00\x00\x00\x00\x00\x00")
        uc.mem_write(0x30000012, b"\x35")
        if (call(entry) != 0xFFFFFFFE or get(0x8000A938) != 0 or
                get(0x80002938) != 0xFFFFFFFE or
                get(0x80002910) != 0x40000000 or
                get(0x80002920) != 0x451 or
                fis_at_trigger[-1][:4] != b"\x34\x40\x51\x04"):
            raise ImageError("malformed WRITE was not retired with ATA error")
        put(0x8000C060, 0)
        if call(entry) != 0:
            raise ImageError("malformed slot did not rearm")
        put(0x8000C060, 1)
        put(0x80002938, 1)
        uc.mem_write(0x30000000, header + read_fis)
        uc.mem_write(0x30000012, b"\x60")
        if (call(entry) != 0xFFFFFFFE or get(0x80002938) != 0xFFFFFFFE or
                get(0x80002910) != 0x40000000):
            raise ImageError("unsupported NCQ command left host slot pending")

        put(0x80002938, 1)
        if (call(entry) != 0xFFFFFFFE or get(0x80002938) != 0xFFFFFFFE or
                get(0x80002910) != 0x40000000):
            raise ImageError("identical rejected command was not retired again")
        put(0x8000C060, 0)
        if call(entry) != 0:
            raise ImageError("NCQ rejection did not rearm")
        put(0x8000C060, 1)
        put(0x80002938, 1)
        put(0x8000A938, 1)
        uc.mem_write(0x30000000, header + read_fis)
        if call(entry) != 0 or get(0x80002938) != 1:
            raise ImageError("backend busy command was not deferred")
        put(0x8000A938, 0)
        if call(entry) != 1 or get(0x8000A938) != 1:
            raise ImageError("deferred command did not issue when backend became idle")
    except (OSError, subprocess.CalledProcessError, StopIteration, ImageError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    print("open READ, WRITE, FLUSH, EF/03, F5: completion, rejection and busy retry verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
