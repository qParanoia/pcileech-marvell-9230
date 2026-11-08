

"""Execute the diagnostic ARM build with port-0 disk I/O and a SATA mailbox.

The CH568 SATA peer is modeled; no USB or physical-board result is implied.
Memory-read requests are served through the modeled PUNIT CPU window and
returned as WRITE DMA EXT data streams or F1/A5 reply chunks.
"""
import struct

from build_c_stage import ROOT, compile_stage
from emulate_multiport import Board, require

STAGING = 0x30004000


class DiagnosticBoard(Board):
    def __init__(self, payload, symbols, ch568=True, connected=(0, 2)):
        super().__init__(payload, symbols, connected=connected, expected_pi=0x8B)
        if 2 in connected:
            self.put(self.backend(2) + 0x28, 0x113)
        self.mailbox = []
        self.acks = []
        self.service_commands = []
        self.dma_streams = []
        if ch568:
            identity = bytearray(self.identities[2])
            text = b'CH568 MV9230 USB SATA MAILBOX'.ljust(40, b' ')
            for i, byte in enumerate(text):
                identity[54 + (i ^ 1)] = byte
            self.identities[2] = bytes(identity)

    def host_page(self, address, size, seed):
        """Publish synthetic host physical memory visible through the window."""
        data = bytearray(((seed + i) & 0xFF) for i in range(size))
        self.bus[address] = data
        return bytes(data)

    def complete(self, port, failure=False):
        descriptor, clb = self.jobs[port]
        opcode = descriptor[0x22]
        if port != 2 or opcode == 0xEC:
            return super().complete(port, failure)
        self.jobs.pop(port)
        self.service_commands.append(opcode)
        if not failure and opcode == 0xF0:
            require(descriptor[0x23] == 0x37, 'incorrect mailbox poll feature')
            table = 0x30000000 | (struct.unpack_from('<I', descriptor, 8)[0] & ~3)
            data = 0x30000000 | (self.get(table + 0x80) & ~1)
            words = self.mailbox.pop(0) if self.mailbox else (0, 0, 0, 0)
            block = struct.pack(f'<{len(words)}I', *words)
            self.uc.mem_write(data, block + bytes(512 - len(block)))
            self.put(clb + 4, 512)
        elif not failure and opcode == 0xF1:
            require(descriptor[0x23] == 0xA5, 'incorrect mailbox ack feature')
            self.acks.append(bytes(descriptor[0x20 + x] for x in (4, 5, 6, 8, 9, 10, 12, 13)))
            self.put(clb + 4, 0)
        elif not failure and opcode == 0x35:

            require(descriptor[0x23] == 0, 'mailbox write had a feature byte')
            slot_flags = struct.unpack_from('<I', descriptor, 0)[0]
            require(slot_flags & 0x1F == 5 and slot_flags & 0x40,
                    'mailbox write slot flags are not CFL=5|W')


            declared = struct.unpack_from('<I', descriptor, 4)[0] & 0xFFFF
            entry_count = declared if declared else 1
            require(slot_flags & 0x10000, 'mailbox write without a PRDT')
            table = 0x30000000 | (struct.unpack_from('<I', descriptor, 8)[0] & ~3)
            sectors = descriptor[0x2C] | (descriptor[0x2D] << 8)
            lba = int.from_bytes(descriptor[0x24:0x27], 'little')
            entries = [(self.get(table + 0x8C + i * 16) & 0x3FFFFF) + 1
                       for i in range(entry_count)]
            require(sum(entries) == sectors * 512 or declared == 0,
                    'declared PRDT length disagrees with the entries')
            size = sum(entries)
            require(size == sectors * 512,
                    'mailbox write byte count disagrees with sector count')
            parts = []
            for index, entry_size in enumerate(entries):
                dba = self.get(table + 0x80 + index * 16)
                if dba & 1:
                    require(entry_count == 1 and
                            0x30000000 | (dba & ~1) == STAGING,
                            'mailbox write PRDT does not target the staging buffer')
                    parts.append(bytes(self.uc.mem_read(STAGING, entry_size)))
                else:


                    dba_high = self.get(table + 0x84 + index * 16)
                    parts.append(self.bus_read((dba_high << 32) | dba, entry_size))
            self.dma_streams.append((lba, sectors, b''.join(parts)))
            self.put(clb + 4, size)
        elif not failure:
            raise AssertionError(f'unexpected service command {opcode:02X}')
        self.put(self.backend(port) + 0x38, 0)
        self.put(self.backend(port) + 0x34, 0)
        self.put(self.backend(port) + 0x20, 0x451 if failure else 0x50)
        self.put(self.backend(port) + 0x10, 0x40000000 if failure else 2)

    def submit_service(self, command, tail=(0, 0)):
        """Deliver one mailbox request; returns after its poll completed and
        the firmware armed the reply (F1 chunk or WRITE DMA EXT)."""
        self.mailbox.append((0x314D4843, command, *tail))
        self.acks.clear()
        for _ in range(1100):
            result = self.call('ch568_diag_poll')
            if 2 in self.jobs:
                require(self.jobs[2][0][0x22] == 0xF0, 'mailbox was not ready for a fresh poll')
                self.complete(2)
                self.call('ch568_diag_poll')
                return result
        raise AssertionError('mailbox poll never started')

    def finish_reply(self, chunks):
        for _ in range(chunks):
            require(2 in self.jobs and self.jobs[2][0][0x22] == 0xF1, 'missing reply chunk')
            self.complete(2)
            self.call('ch568_diag_poll')
        require(len(self.acks) == chunks, 'incorrect reply size')
        return b''.join(self.acks)

    def finish_dma_write(self):
        require(2 in self.jobs and self.jobs[2][0][0x22] == 0x35,
                'memory data was not armed as WRITE DMA EXT')
        self.complete(2)
        self.call('ch568_diag_poll')
        require(2 not in self.jobs, 'service issued another command after the data stream')
        require(len(self.dma_streams) == 1, 'expected exactly one data stream')
        stream = self.dma_streams.pop()
        require(not self.acks, 'memory WRITE35 also produced F1/A5 reply chunks')
        require(self.get(0xD0020000) == 0 and self.get(0xD0020010) == 0,
                'a PUNIT window stayed mapped after the read')
        return stream


def main():
    payload, symbols = compile_stage(ROOT / 'build/toolchain', ROOT / 'build/ch568-diag-test',
        cflags=('-DOPEN9230_STATIC_BOARD_TEST=1', '-DOPEN9230_STATIC_BOOT_TEST=1',
                '-DOPEN9230_BASIC_BOOT=1', '-DOPEN9230_DMA_PROBE=1',
                '-DOPEN9230_NO_OPTION_ROM=1', '-DOPEN9230_CH568_DIAGNOSTICS=1',
                '-DSTATIC_TEST_POLL_BUDGET=128u'))
    board = DiagnosticBoard(payload, symbols)
    board.boot()
    require(board.call('ch568_diag_ready') == 1, 'CH568 identity not recognized')
    require(board.get(0x8000280C) == 0x8B, 'service socket exposed to host disk driver')

    data = bytes(range(256)) * 2
    board.request(0, opcode=0x35, content=data)
    board.poll(1, 0)
    board.submit_service(0x1340)
    require(set(board.jobs) == {0, 2}, 'service and disk commands did not coexist')
    status = struct.unpack('<16I', board.finish_reply(8))
    require(status[:3] == (0x31324453, 24, 0x92301B4B), 'incorrect STATUS identity/version')
    require(status[4] == 0x8B and status[6] == 2, 'incorrect port map in STATUS')
    require(status[12:15] == (1, 0, 0), 'STATUS did not capture an active P0 command')
    require(set(board.jobs) == {0}, 'service retired another disk command')
    board.complete(0)
    board.poll(2, 0)
    _, response, _ = board.request(0, opcode=0x25)
    board.poll(1, 0)
    board.submit_service(0x1337)
    require(struct.unpack('<2I', board.finish_reply(1)) == (0x92301B4B, 24), 'PING failed')
    board.complete(0)
    board.poll(2, 0)
    require(bytes(response) == data, 'CH568 service corrupted P0 disk data')


    low_page = board.host_page(0x0000B000, 0x1000, 0x11)
    board.submit_service(0x1338, (0x0000B000 >> 32, 0x0000B000 & 0xFFFFFFFF))
    require(board.finish_reply(8) == low_page[:64],
            'READ64 returned wrong sub-4GiB host memory')
    high_page = board.host_page(0x123400000, 0x1000, 0x22)
    board.submit_service(0x1338, (0x123400000 >> 32, 0x123400000 & 0xFFFFFFFF))
    require(board.finish_reply(8) == high_page[:64],
            'READ64 returned wrong above-4GiB host memory')


    aligned = board.host_page(0x100000000, 0x1000, 0x33)
    board.submit_service(0x133A, (0x100000000 >> 32, 0x100000000 & 0xFFFFFFFF))
    lba, sectors, stream = board.finish_dma_write()
    require((lba, sectors) == (0x7F0, 8) and stream == aligned,
            'READ4K stream wrong for an aligned page')

    crossing = board.host_page(0x1234F800, 0x1000, 0x44)
    board.submit_service(0x133A, (0, 0x1234F800))
    lba, sectors, stream = board.finish_dma_write()
    require((lba, sectors) == (0x7F0, 8) and stream == crossing,
            'READ4K stream wrong for a 64-KiB-crossing page')


    pages = [board.host_page(0xA0000000 + i * 0x2000, 0x1000, 0x50 + i)
             for i in range(16)]
    tail = [16, 0x777]
    for page_address in (0xA0000000 + i * 0x2000 for i in range(16)):
        tail += [page_address & 0xFFFFFFFF, page_address >> 32]
    board.submit_service(0x133B, tuple(tail))
    lba, sectors, stream = board.finish_dma_write()
    require((lba, sectors) == (0x7E0, 128) and stream == b''.join(pages),
            'READ-BATCH stream wrong for sixteen scattered pages')

    mixed = [board.host_page(0x8000, 0x1000, 0x60),
             board.host_page(0x100001000, 0x1000, 0x61),
             board.host_page(0x100009000, 0x1000, 0x62)]
    board.submit_service(0x133B, (3, 0x778,
                                  0x8000 & 0xFFFFFFFF, 0x8000 >> 32,
                                  0x100001000 & 0xFFFFFFFF, 0x100001000 >> 32,
                                  0x100009000 & 0xFFFFFFFF, 0x100009000 >> 32))
    lba, sectors, stream = board.finish_dma_write()
    require((lba, sectors) == (0x7E0, 24) and stream == b''.join(mixed),
            'READ-BATCH stream wrong for mixed low/high pages')


    run = board.host_page(0x200000000, 0x80000, 0x80)
    board.submit_service(0x1341, (0x2, 0x0, 128, 0))
    lba, sectors, stream = board.finish_dma_write()
    require((lba, sectors) == (0x7D0, 1024) and stream == run,
            'READ-LINEAR stream wrong for 128 direct pages')

    single = board.host_page(0x300000000, 0x1000, 0x90)
    board.submit_service(0x1341, (0x3, 0x0, 1, 0))
    lba, sectors, stream = board.finish_dma_write()
    require((lba, sectors) == (0x7D0, 8) and stream == single,
            'READ-LINEAR stream wrong for one page')


    board.request(0, opcode=0x25)
    board.poll(1, 0)
    overlap = board.host_page(0x1000, 0x1000, 0xA0)
    board.submit_service(0x1341, (0x0, 0x1000, 1, 0))
    require(set(board.jobs) == {0, 2}, 'disk read displaced by a linear read')
    lba, sectors, stream = board.finish_dma_write()
    require(stream == overlap, 'READ-LINEAR corrupted under concurrent disk I/O')
    board.complete(0)
    board.poll(2, 0)


    board.request(0, opcode=0x25)
    board.poll(1, 0)
    probe = board.host_page(0x100010000, 0x1000, 0x70)
    board.submit_service(0x133A, (0x100010000 >> 32, 0x100010000 & 0xFFFFFFFF))
    require(set(board.jobs) == {0, 2}, 'disk read displaced by a memory read')
    board.finish_dma_write()
    board.complete(0)
    board.poll(2, 0)


    board.submit_service(0x1342, (2, 0,
                                  0x0, 0x0, 0xC0000000, 0x0,
                                  0x0, 0x1, 0x40000000, 0x1))
    require(struct.unpack('<2I', board.finish_reply(1))[0] == 0x4D414350,
            'SET-MAP not acknowledged')
    good = board.host_page(0x100000000, 0x1000, 0xB0)
    board.submit_service(0x1341, (0x1, 0x0, 1, 0))
    lba, sectors, stream = board.finish_dma_write()
    require(stream == good, 'in-map LINEAR failed after SET-MAP')
    board.submit_service(0x1341, (0x2, 0x0, 1, 0))
    require(not board.acks and not board.dma_streams and 2 not in board.jobs,
            'out-of-map LINEAR reached the engine')


    board.submit_service(0x1340)
    errors_before = struct.unpack('<16I', board.finish_reply(8))[15]
    for command, tail in ((0x1339, (1, 0)),
                          (0x133B, (0, 0x777)),
                          (0x133B, (17, 0x777)),
                          (0x1340, (1, 0)),
                          (0x1337, (1, 0)),
                          (0x133C, (0, 0)),
                          (0x1341, (0, 0x1000, 0, 0)),
                          (0x1341, (0, 0x1000, 129, 0)),
                          (0x1341, (0, 0xFFFFF000, 2, 0))):
        before = {addr: bytes(value) for addr, value in board.bus.items()}
        board.submit_service(command, tail)
        require(not board.acks and not board.dma_streams,
                'unsupported request received a data reply')
        require(2 not in board.jobs, 'unsupported request armed a data command')
        require({addr: bytes(value) for addr, value in board.bus.items()} == before,
                'unsupported request modified host or controller buffers')
    board.submit_service(0x1340)
    status = struct.unpack('<16I', board.finish_reply(8))
    require(status[15] == errors_before + 9, 'rejected requests were not all counted')
    require(status[6] == 2 and status[7] > 0, 'service state disturbed by rejections')
    print('V24 ARM: READ64/READ4K/READ-BATCH staged + READ-LINEAR direct-PRDT, exact host data')
    print('128-page direct stream and disk I/O coexist on separate windows; all limits and argument abuse rejected')


    ordinary = DiagnosticBoard(payload, symbols, ch568=False)
    ordinary.boot()
    require(ordinary.call('ch568_diag_ready') == 0, 'ordinary disk accepted as CH568')
    require(ordinary.call('ch568_diag_poll') == 0 and not ordinary.jobs, 'private command sent to disk')
    absent = DiagnosticBoard(payload, symbols, connected=(0,))
    absent.boot()
    require(absent.call('ch568_diag_ready') == 0, 'absent device accepted as CH568')
    absent.request(0, opcode=0x25)
    absent.poll(1, 0)
    absent.complete(0)
    absent.poll(2, 0)
    print('Missing CH568 or ordinary disk in reserved socket: service inactive; real P0 disk still works')


if __name__ == '__main__':
    main()
