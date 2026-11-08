

"""Execute the ARM frontend with a translated PCIe bus and all AHCI slots.

Backend completion is injected. This verifies firmware selection, descriptors,
PRDBC and completion masks, not PCIe/SATA electrical behavior or hardware IRQs.
"""
from __future__ import annotations

import struct

from build_c_stage import ROOT, compile_stage
from inspect_image import ImageError


def main() -> int:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_PC

    payload, symbols = compile_stage(
        ROOT / 'build/toolchain', ROOT / 'build/host-slots-test',
        cflags=('-DOPEN9230_STATIC_BOARD_TEST=1', '-DOPEN9230_STATIC_BOOT_TEST=1',
                '-DOPEN9230_BASIC_BOOT=1', '-DOPEN9230_DMA_PROBE=1',
                '-DSTATIC_TEST_POLL_BUDGET=128u'))
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for address, length in ((0, 0x20000), (0x04000000, 0x10000),
                            (0x30000000, 0x80000), (0x50000000, 0x20000),
                            (0x80002000, 0x2000), (0x8000A000, 0x1000),
                            (0x8000C000, 0x1000), (0xD0020000, 0x1000)):
        uc.mem_map(address, length)
    uc.mem_write(0, payload)
    bus: dict[int, bytearray] = {}
    ci_writes: list[int] = []
    console_ci_writes: list[int] = []
    backend_issues: list[bytes] = []

    def put(address: int, value: int) -> None:
        uc.mem_write(address, struct.pack('<I', value & 0xFFFFFFFF))

    def get(address: int) -> int:
        return struct.unpack('<I', uc.mem_read(address, 4))[0]

    def region(address: int, size: int) -> tuple[bytearray, int]:
        for start, data in bus.items():
            if start <= address and address + size <= start + len(data):
                return data, address - start
        raise ImageError(f'unexpected PCIe bus access 0x{address:016X}+{size}')

    def translated(address: int) -> int:
        control = get(0xD0020010)
        if not control & 1:
            raise ImageError('CPU access to a disabled PUNIT window')
        return (get(0xD002001C) << 32) + get(0xD0020018) + (address - 0x50000000)

    def on_read(emu: Uc, _access: int, address: int, size: int, _value: int, _user: object) -> None:
        if 0x50000000 <= address < 0x50020000:
            data, offset = region(translated(address), size)
            emu.mem_write(address, bytes(data[offset:offset + size]))

    def on_write(emu: Uc, _access: int, address: int, size: int, value: int, _user: object) -> None:
        if 0x50000000 <= address < 0x50020000:
            data, offset = region(translated(address), size)
            data[offset:offset + size] = value.to_bytes(size, 'little')
        elif address == 0x80002938:
            ci_writes.append(value & 0xFFFFFFFF)
        elif address == 0x80002CB8:
            console_ci_writes.append(value & 0xFFFFFFFF)
        elif address == 0x8000A938 and value == 1:
            backend_issues.append(bytes(emu.mem_read(0x3006B000, 64)))

    uc.hook_add(UC_HOOK_MEM_READ, on_read)
    uc.hook_add(UC_HOOK_MEM_WRITE, on_write)

    def call(name: str) -> int:
        uc.reg_write(UC_ARM_REG_SP, 0x0400F000)
        uc.reg_write(UC_ARM_REG_LR, 0x1FF00)
        uc.emu_start(symbols[name], 0x1FF00, count=100000)
        if uc.reg_read(UC_ARM_REG_PC) != 0x1FF00:
            raise ImageError(f'{name} did not return within its instruction budget')
        value = uc.reg_read(UC_ARM_REG_R0)
        return value if value < 0x80000000 else value - 0x100000000

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ImageError(message)

    call('host_frontend_basic_reset_state')

    for addr, val in ((0x8000A900, 0x6B003), (0x8000A908, 0x67001),
                      (0x8000A918, 0x10000011), (0x8000A924, 0x101),
                      (0x8000A928, 0x133), (0x80002918, 0x11)):
        put(addr, val)

    def scenario(slot: int, opcode: int = 0xC8, failure: bool = False,
                 clb: int = 0x108920000, extra_mask: int = 0) -> None:
        bus.clear()
        headers = bytearray(b'\xA5' * 1024)
        ctba, rfis = 0x208930500, 0x308940400
        flags = 5 | (0x40 if opcode == 0xCA else 0) | (0x10000 if opcode in (0xC8, 0xCA, 0xEC) else 0)
        header = struct.pack('<4I', flags, 0, ctba & 0xFFFFFFFF, ctba >> 32)
        headers[slot * 32:slot * 32 + 16] = header
        for queued in range(32):
            if extra_mask & (1 << queued):
                headers[queued * 32:queued * 32 + 16] = header

        fis = bytes((0x27, 0x80, opcode, 0, 0, 0, 0, 0xE0, 0, 0, 0, 0, 8, 0, 0, 0))
        table = bytearray(0x90)
        table[:16] = fis
        struct.pack_into('<4I', table, 0x80, 0x08950000, 1, 0, 4095)
        bus[clb] = headers
        bus[ctba] = table
        bus[rfis] = bytearray(256)
        bus[0x108950000] = bytearray(4096)
        before = bytes(headers)
        put(0x80002900, clb)
        put(0x80002904, clb >> 32)
        put(0x80002908, rfis)
        put(0x8000290C, rfis >> 32)
        mask = 1 << slot
        put(0x80002938, mask | extra_mask)
        put(0x8000C060, mask | extra_mask)
        uc.mem_write(0x30000000, header + fis if slot == 0 else b'\xCC' * 32)
        put(0x8000A938, 0)
        put(0x8000A934, 0)
        ci_writes.clear()
        issued = len(backend_issues)
        result = call('host_frontend_poll_basic')
        if opcode == 0x60:
            require(result == -2 and len(backend_issues) == issued, 'unsupported NCQ forwarded')
            require(ci_writes == [(~mask) & 0xFFFFFFFF], 'rejection cleared another slot')
            require(bytes(headers) == before, 'rejection changed host command list')
            return
        require(result == 1 and len(backend_issues) == issued + 1, f'slot {slot}: command not issued')
        require(call('host_frontend_basic_slot') == slot, 'wrong slot selection')
        descriptor = backend_issues[-1]
        require(descriptor[0x20:0x30] == fis, 'wrong CFIS copied to backend')
        require(struct.unpack_from('<Q', descriptor, 8)[0] == ctba | 4, 'wrong CTBA forwarded')
        require(call('host_frontend_poll_basic') == 0, 'second command issued while backend busy')
        require(len(backend_issues) == issued + 1, 'duplicate backend command')

        put(0x8000A938, 0)
        put(0x8000A934, 0)
        put(0x8000A920, 0x451 if failure else 0x50)
        put(0x8000A910, 0x40000000 if failure else 1)
        put(0x3006B004, 0 if failure else (4096 if opcode in (0xC8, 0xCA) else 0))
        result = call('host_frontend_poll_basic')
        require(result == (-3 if failure else 2), 'wrong completion result')
        require(ci_writes == [(~mask) & 0xFFFFFFFF], 'completion cleared another CI bit')
        require(get(0x80002934) == mask, 'wrong SACT completion mask')
        expected = 0 if failure or opcode == 0xEF else 4096
        require(struct.unpack_from('<I', headers, slot * 32 + 4)[0] == expected, 'wrong PRDBC')
        expected_headers = bytearray(before)
        struct.pack_into('<I', expected_headers, slot * 32 + 4, expected)
        require(headers == expected_headers, 'adjacent host header corrupted')
        require(get(0x80002910) == (0x40000000 if failure else 8), 'wrong host interrupt status')
        if extra_mask:


            put(0x80002938, extra_mask)
            put(0x8000C060, extra_mask)
            require(call('host_frontend_poll_basic') == 1, 'queued request not issued')
            queued = (extra_mask & -extra_mask).bit_length() - 1
            require(call('host_frontend_basic_slot') == queued, 'wrong queued slot')
            put(0x8000A938, 0)
            put(0x8000A934, 0)
            put(0x8000A920, 0x50)
            put(0x8000A910, 1)
            put(0x3006B004, 4096)
            require(call('host_frontend_poll_basic') == 2, 'queued request not completed')
            require(ci_writes[-1] == (~(1 << queued)) & 0xFFFFFFFF, 'queued CI mask wrong')
            require(struct.unpack_from('<I', headers, queued * 32 + 4)[0] == 4096,
                    'queued PRDBC written to wrong header')

    for slot in range(32):
        scenario(slot)
    for slot in (22, 1, 31, 2, 0, 22):
        scenario(slot, 0xCA)
        scenario(slot, 0xC8, failure=True)
        scenario(slot, 0x60)

    scenario(1, extra_mask=1 << 22)

    scenario(22, clb=0x1FFFFFFE0)
    print('all 32 host slots: exact CFIS/CTBA, serialization, 4096-byte PRDBC, CI/SACT masks verified')
    print('slot changes 22/1/31/2/0, READ/WRITE, ATA error, NCQ rejection and 64-bit address carry verified')
    print('untouched neighboring headers and preservation of other pending CI bits verified')

    def console_scenario(slot: int, opcode: int, cdb_opcode: int = 0x12,
                         invalid_flags: bool = False, extra_mask: int = 0,
                         clb: int = 0x109800000, shadow_missing: bool = False) -> None:
        bus.clear()
        header_offset = 32 * slot
        headers = bytearray(b'\xA5' * 1024)
        ctba, data_bus, fb = 0x209810500, 0x309820000, 0x409830400
        no_data = opcode in (0xEF, 0xEC, 0x60) or (opcode == 0xA0 and cdb_opcode == 0)
        flags = (4 if invalid_flags else 5) | (0x10000 if not no_data else 0)
        if opcode == 0xA0:
            flags |= 0x20
        header = struct.pack('<4I', flags, 0, ctba & 0xFFFFFFFF, ctba >> 32)
        headers[header_offset:header_offset + 16] = header
        fis = bytes((0x27, 0x80, opcode, 3 if opcode == 0xEF else 0)) + bytes(12)
        table = bytearray(0x90)
        table[:16] = fis
        table[0x40] = cdb_opcode
        struct.pack_into('<4I', table, 0x80, data_bus & 0xFFFFFFFF, data_bus >> 32, 0, 511)
        bus[clb] = headers
        bus[ctba] = table
        bus[data_bus] = bytearray(b'\xCC' * 512)
        bus[fb] = bytearray(b'\xA5' * 256)
        put(0x80002C80, clb)
        put(0x80002C84, clb >> 32)
        put(0x80002C88, fb)
        put(0x80002C8C, fb >> 32)
        put(0x80002C98, 0x11)
        mask = 1 << slot
        put(0x80002CB8, mask | extra_mask)
        put(0x8000C07C, 0 if shadow_missing else mask | extra_mask)
        uc.mem_write(0x30001C00, header + fis if slot == 0 else b'\xCC' * 32)
        before = bytes(headers)
        console_ci_writes.clear()
        issued = len(backend_issues)
        result = call('console_identify_poll')
        failed = invalid_flags or opcode in (0xEC, 0x60) or (opcode == 0xA0 and cdb_opcode == 0xFF)
        require(result != 0, 'pending console request silently ignored')
        require((result < 0) == (invalid_flags or opcode in (0xEC, 0x60)), 'wrong console error return')
        require(call('console_last_slot') == slot, 'wrong console slot')
        require(call('console_last_opcode') == opcode, 'wrong console opcode')
        require(console_ci_writes == [(~mask) & 0xFFFFFFFF], 'console CI completion wrong')
        require(get(0x80002CB4) == mask, 'console SACT mask wrong')
        require(get(0x80002C90) == (0x40000008 if failed else 8), 'console PxIS wrong')
        require(get(0x80002CA0) == (0x451 if failed else 0x50), 'console TFD wrong')
        require(len(backend_issues) == issued, 'virtual console issued physical SATA I/O')
        expected = 0 if failed or no_data else (512 if opcode == 0xA1 else 44)
        expected_headers = bytearray(before)
        struct.pack_into('<I', expected_headers, header_offset + 4, expected)
        require(headers == expected_headers, 'console PRDBC or neighboring header differs')
        rfis = bus[fb]
        require(struct.unpack_from('<I', rfis, 0x40)[0] == (0x04514034 if failed else 0x00504034),
                'console D2H FIS differs')
        require(struct.unpack_from('<I', rfis, 0x58)[0] == (0x045140A1 if failed else 0x005040A1),
                'console SDB FIS differs')
        if opcode == 0xA1 and not failed:
            require(bus[data_bus][:2] == b'\x40\x83', 'console IDENTIFY data differs')
        elif opcode == 0xA0 and expected:
            require(bus[data_bus][8:16] == b'Marvell ', 'console INQUIRY data differs')

    call('console_identify_reset')
    for slot in range(32):
        console_scenario(slot, 0xA1)
        console_scenario(slot, 0xEF)
        console_scenario(slot, 0xA0)
    for slot in (1, 22, 31, 0, 2):
        console_scenario(slot, 0xA0, cdb_opcode=0)
        console_scenario(slot, 0xEC)
        console_scenario(slot, 0x60)
        console_scenario(slot, 0xA1, invalid_flags=True)
        console_scenario(slot, 0xA0, cdb_opcode=0xFF)
    console_scenario(1, 0xEF, extra_mask=1 << 22)
    console_scenario(1, 0xEF, shadow_missing=True)
    console_scenario(1, 0xA1, shadow_missing=True)
    console_scenario(22, 0xA1, clb=0x1FFFFFFE0)
    print('port 7 all 32 slots: A1, EF/03, INQUIRY, PRDBC, D2H/SDB, exact CI/SACT verified')
    print('port 7 no-data PACKET, malformed/unsupported requests retire, other slots preserved, no physical I/O')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
