

"""Run the compiled ARM stage against independent SATA disks and host memory.

Models MMIO completion and DMA, not the PCIe/SATA electrical implementation.
Tests boot-time discovery, simultaneous backend requests, mixed geometry,
out-of-order completions, data isolation, errors and virtual reset isolation.
"""
from __future__ import annotations

import itertools
import struct

from build_c_stage import ROOT, compile_stage
from inspect_image import ImageError


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ImageError(message)


class Board:
    def __init__(self, payload: bytes, symbols: dict[str, int], connected=(0, 1, 2, 3), expected_pi=0x8F):
        from unicorn import (Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE,
                             UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE)
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.symbols = symbols
        self.expected_pi = expected_pi
        self.bus: dict[int, bytearray] = {}
        self.jobs: dict[int, tuple[bytes, int]] = {}
        self.deferred: list[tuple[int, int]] = []
        self.uart = bytearray()
        self.booting = False
        self.ready = False
        self.dlab = False
        self.issues: list[int] = []
        self.sector_bytes = (512, 4096, 512, 512)
        self.disks = [bytearray([0x30 + p]) * 0x20000 for p in range(4)]
        self.identities = []
        for p in range(4):
            data = bytearray(512)
            struct.pack_into('<H', data, 0, 0x40)
            data[54:62] = f'DISK-{p:03}'.encode('ascii')
            if self.sector_bytes[p] == 4096:
                struct.pack_into('<H', data, 212, 0x5000)
                struct.pack_into('<I', data, 234, 2048)
            self.identities.append(bytes(data))
        for address, size in ((0, 0x20000), (0x04000000, 0x10000),
                              (0x30000000, 0x80000), (0x40000000, 0x80000),
                              (0x50000000, 0x20000), (0x80002000, 0x2000),
                              (0x8000A000, 0x1000),
                              (0x8000C000, 0x1000), (0xD0020000, 0x20000),
                              (0xD0070000, 0x10000)):
            self.uc.mem_map(address, size)
        self.uc.mem_write(0, payload)
        self.put(0x8000A800, 3)
        self.put(0x8000A80C, 15)
        self.put(0xD0030000, 0x92301B4B)
        for p in range(4):
            self.put(self.backend(p) + 0x28, 0x133 if p in connected else 0)
            self.put(self.backend(p) + 0x24, 0xFFFFFFFF)
            self.put(self.backend(p) + 0x20, 0x50 if p in connected else 0x7F)

        def read(uc, _access, address, size, _value, _user):
            if 0x50000000 <= address < 0x50020000:
                uc.mem_write(address, self.bus_read(self.translated(address), size))
            elif 0x40000000 <= address < 0x40080000:
                uc.mem_write(address, self.bus_read(self.translated(address), size))
            elif address == 0xD0072014:
                uc.mem_write(address, b'\x60')

        def write(uc, _access, address, size, value, _user):
            if 0x50000000 <= address < 0x50020000:
                self.bus_write(self.translated(address), value.to_bytes(size, 'little'))
            elif 0x40000000 <= address < 0x40080000:
                self.bus_write(self.translated(address), value.to_bytes(size, 'little'))
            elif address == 0xD007200C:
                self.dlab = bool(value & 0x80)
            elif address == 0xD0072000 and not self.dlab:
                self.uart.append(value & 0xFF)
            for p in range(4):
                host, backend = self.host(p), self.backend(p)
                if address == host + 0x38:
                    self.deferred.append((address, self.get(address) & value))
                    shadow = 0x8000C060 + p * 4
                    self.deferred.append((shadow, self.get(shadow) & value))
                elif address == backend + 0x10:
                    self.deferred.append((address, self.get(address) & ~value))
                elif address == backend + 0x18 and value & 0x11 == 0x11:
                    if self.get(backend + 0x28) & 15 == 3:
                        self.deferred.append((backend + 0x24, 0x101))
                elif address == backend + 0x38 and value == 1:
                    require(p not in self.jobs, f'port {p}: overwrote an active backend')
                    clb = 0x30000000 | (self.get(backend) & ~3)
                    descriptor = bytes(uc.mem_read(clb, 64))
                    self.jobs[p] = descriptor, clb
                    self.issues.append(p)

        def step(uc, address, _size, _user):
            for target, value in self.deferred:
                self.put(target, value)
            self.deferred.clear()
            if self.booting:
                for p in tuple(self.jobs):
                    self.complete(p)
                if address == symbols['stage_poll_marker'] and self.get(0x8000280C) == self.expected_pi:
                    self.ready = True
                    uc.emu_stop()

        self.uc.hook_add(UC_HOOK_MEM_READ, read)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, write)
        self.uc.hook_add(UC_HOOK_CODE, step)

    @staticmethod
    def host(p):
        return 0x80002900 + p * 0x80

    @staticmethod
    def backend(p):
        return 0x8000A900 + p * 0x80

    def put(self, address, value):
        self.uc.mem_write(address, struct.pack('<I', value & 0xFFFFFFFF))

    def get(self, address):
        return struct.unpack('<I', self.uc.mem_read(address, 4))[0]

    def translated(self, address):
        if 0x50000000 <= address < 0x50020000:
            require(self.get(0xD0020010) & 1, 'access through a disabled CPU window')
            return (self.get(0xD002001C) << 32) + self.get(0xD0020018) + address - 0x50000000
        require(self.get(0xD0020000) & 1, 'access through a disabled CPU window')
        return (self.get(0xD002000C) << 32) + self.get(0xD0020008) + address - 0x40000000

    def region(self, address, size):
        for base, data in self.bus.items():
            if base <= address and address + size <= base + len(data):
                return data, address - base
        raise ImageError(f'unmapped host DMA address {address:016X}+{size}')

    def bus_read(self, address, size):
        data, offset = self.region(address, size)
        return bytes(data[offset:offset + size])

    def bus_write(self, address, payload):
        data, offset = self.region(address, len(payload))
        data[offset:offset + len(payload)] = payload

    def call(self, name, *args):
        from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_SP
        self.uc.reg_write(UC_ARM_REG_SP, 0x04003D00)
        self.uc.reg_write(UC_ARM_REG_LR, 0x1FF00)
        for i, value in enumerate(args):
            self.uc.reg_write(UC_ARM_REG_R0 + i, value)
        self.uc.emu_start(self.symbols[name], 0x1FF00, count=200000)
        require(self.uc.reg_read(UC_ARM_REG_PC) == 0x1FF00, f'{name} did not return')
        value = self.uc.reg_read(UC_ARM_REG_R0)
        return value if value < 0x80000000 else value - 0x100000000

    def boot(self):
        self.booting = True
        self.uc.emu_start(0, 0x1FF00, count=2000000)
        self.booting = False
        require(self.ready, 'firmware did not reach initialized host service')
        require(self.get(0x80002800) & 31 == 7, 'CAP.NP does not include management port 7')
        for p in range(4):
            linked = (self.get(self.backend(p) + 0x28) & 15 == 3 and
                      bool(self.expected_pi & (1 << p)))
            require(self.get(self.host(p) + 0x28) == (0x133 if linked else 0),
                    f'port {p}: incorrect host link report')
            if self.get(self.backend(p) + 0x28) & 15 == 3:
                data_address = 0x3006E080 if not p else 0x3006E400 + (p - 1) * 512
                require(bytes(self.uc.mem_read(data_address, 512)) == self.identities[p],
                        f'port {p}: startup IDENTIFY data mixed with another disk')
        self.put(0x80002804, 0x80000002)
        for p in range(4):
            self.put(self.host(p) + 0x18, 0x11)
        self.call('host_frontend_basic_reset_state')

    def request(self, p, slot=22, opcode=0x35, content=None):
        base = ((p + 1) << 32) + 0x08900000
        ctba, fb, data_address = base + 0x2000, base + 0x4000, base + 0x6000
        size = self.sector_bytes[p]
        headers = bytearray(b'\xA5' * 1024)
        flags = 0x10005 | (0x40 if opcode == 0x35 else 0)
        header = struct.pack('<4I', flags, 0, ctba & 0xFFFFFFFF, ctba >> 32)
        headers[slot * 32:slot * 32 + 16] = header
        fis = bytes((0x27, 0x80, opcode, 0, 2, 0, 0, 0x40, 0, 0, 0, 0, 1, 0, 0, 0))
        table = bytearray(0x90)
        table[:16] = fis
        struct.pack_into('<4I', table, 0x80, data_address & 0xFFFFFFFF, data_address >> 32, 0, size - 1)
        self.bus[base] = headers
        self.bus[ctba] = table
        self.bus[fb] = bytearray(256)
        self.bus[data_address] = bytearray(content if content is not None else b'\xA6' * size)
        for offset, value in ((0, base), (4, base >> 32), (8, fb), (12, fb >> 32),
                              (0x38, 1 << slot)):
            self.put(self.host(p) + offset, value)


        self.put(0x8000C060 + p * 4, (1 << slot) if p == 0 else 0)
        if p == 0 and slot == 0:
            self.uc.mem_write(0x30000000, header + fis)
        return headers, self.bus[data_address], self.bus[fb]

    def complete(self, p, failure=False):
        descriptor, clb = self.jobs.pop(p)
        table_address = struct.unpack_from('<Q', descriptor, 8)[0]
        local = bool(table_address & 1)
        if local:
            table_address = 0x30000000 | (table_address & ~3)
            table = bytes(self.uc.mem_read(table_address, 0x90))
        else:
            table = self.bus_read(table_address & ~0x3F, 0x90)
        dba, _, dbc = struct.unpack_from('<QII', table, 0x80)
        opcode = descriptor[0x22]
        size = (dbc & 0x3FFFFF) + 1
        lba = int.from_bytes(descriptor[0x24:0x27], 'little')
        start = lba * self.sector_bytes[p]
        if not failure:
            if opcode == 0xEC:
                data = self.identities[p]
            elif opcode == 0x25:
                data = self.disks[p][start:start + size]
            elif opcode == 0x35:
                data = self.bus_read(dba, size)
                self.disks[p][start:start + size] = data
            else:
                raise ImageError(f'unexpected test backend opcode {opcode:02X}')
            if opcode in (0xEC, 0x25):
                if local:
                    self.uc.mem_write(0x30000000 | (dba & ~1), bytes(data))
                else:
                    self.bus_write(dba, data)
        self.put(clb + 4, 0 if failure else size)
        fb = 0x30000000 | (self.get(self.backend(p) + 8) & ~1)
        self.put(fb + 0x40, 0x04514034 if failure else 0x00504034)
        self.put(self.backend(p) + 0x38, 0)
        self.put(self.backend(p) + 0x34, 0)
        self.put(self.backend(p) + 0x20, 0x451 if failure else 0x50)
        self.put(self.backend(p) + 0x10, 0x40000000 if failure else 2)

    def poll(self, expected, port=None):
        event = self.call('host_frontend_poll_basic')
        require(event == expected, f'expected event {expected}, got {event}')
        if port is not None:
            require(self.call('host_frontend_basic_port') == port, 'event attributed to another port')


def main():
    payload, symbols = compile_stage(ROOT / 'build/toolchain', ROOT / 'build/multiport-test',
        cflags=('-DOPEN9230_STATIC_BOARD_TEST=1', '-DOPEN9230_STATIC_BOOT_TEST=1',
                '-DOPEN9230_BASIC_BOOT=1', '-DOPEN9230_DMA_PROBE=1',
                '-DOPEN9230_NO_OPTION_ROM=1', '-DSTATIC_TEST_POLL_BUDGET=128u'))
    board = Board(payload, symbols)
    board.boot()
    print('actual ARM startup: four late signatures, independent IDENTIFY/geometry, PI=8F, CAP.NP=7')
    for pair in itertools.combinations(range(4), 2):
        expected = {p: bytes([0x80 + p]) * board.sector_bytes[p] for p in pair}
        pending = {p: board.request(p, opcode=0x35, content=expected[p]) for p in pair}
        for _ in pair:
            board.poll(1)
        require(set(board.jobs) == set(pair), 'two physical ports were not active together')
        for p in reversed(pair):
            board.complete(p)
            board.poll(2, p)
            require(board.get(board.host(p) + 0x38) == 0, 'completed host CI did not clear')
            require(struct.unpack_from('<I', pending[p][0], 22 * 32 + 4)[0] == board.sector_bytes[p],
                    'PRDBC used another disk geometry')
        responses = {p: board.request(p, opcode=0x25) for p in pair}
        for _ in pair:
            board.poll(1)
        for p in reversed(pair):
            board.complete(p)
            board.poll(2, p)
            require(bytes(responses[p][1]) == expected[p], 'cross-port disk data corruption')
            require(struct.unpack_from('<I', responses[p][2], 0x40)[0] == 0x00504034,
                    'response FIS published to another port')
    print('all six port pairs: simultaneous WRITE/READ, reversed completion, 512/4096-byte sectors, exact data')
    for slot in range(32):
        for p in range(4):
            board.request(p, slot, 0x25)
        for _ in range(4):
            board.poll(1)
        require(len(board.jobs) == 4, 'four backends not active concurrently')
        for p in (3, 1, 2, 0):
            board.complete(p)
            board.poll(2, p)
    print('all four ports x all 32 slots: concurrent requests, independent backend SRAM and host CI')
    refs = {p: board.request(p, opcode=0x25) for p in range(4)}
    for _ in range(4):
        board.poll(1)
    board.complete(1, failure=True)
    board.poll(-3, 1)
    require(struct.unpack_from('<I', refs[1][0], 22 * 32 + 4)[0] == 0, 'failed read claimed data')
    for p in (2, 0, 3):
        require(board.get(board.backend(p) + 0x38) == 1, 'failure disturbed another backend')
        board.complete(p)
        board.poll(2, p)
    print('ATA error on port 1: no data credited; ports 0/2/3 continue and complete')

    board.request(1, opcode=0x25)
    board.poll(1, 1)
    board.put(board.host(0) + 0x2C, 1)
    require(board.call('host_frontend_poll_port_reset', 0) == 0, 'premature reset release')
    board.put(board.host(0) + 0x2C, 0)
    require(board.call('host_frontend_poll_port_reset', 0) == 1, 'COMRESET release not handled')
    require(set(board.jobs) == {1}, 'port-zero reset disturbed another active disk')
    board.complete(1)
    board.poll(2, 1)
    for p in (1, 3):
        single = Board(payload, symbols, connected=(p,))
        single.boot()
        single.request(p, slot=0, opcode=0x25)
        single.poll(1, p)
        single.complete(p)
        single.poll(2, p)
    print('COMRESET isolation; boot and I/O with only port 1 or port 3 populated, port 0 empty')


if __name__ == '__main__':
    main()
