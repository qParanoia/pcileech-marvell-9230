"""Protocol regression checks for larger USB payload reads."""

import struct
import unittest
import zlib

from read_memory_batch import read_batch


class FakeDevice:
    def __init__(self, frames):
        self.frames = list(frames)
        self.read_sizes = []

    def write(self, endpoint, request, timeout):
        assert endpoint == 0x01 and request.startswith(b"CHBQ")

    def read(self, endpoint, size, timeout):
        assert endpoint == 0x81
        self.read_sizes.append(size)
        frame = self.frames.pop(0)
        assert len(frame) <= size
        return frame


def frames(payload, status=0, received=None, combined=False):
    sequence = 7
    if received is None:
        received = len(payload)
    header = bytearray(32)
    struct.pack_into("<4sHBBI", header, 0, b"CHB1", 32, 1, 0, sequence)
    struct.pack_into("<H", header, 12, 1)
    struct.pack_into("<III", header, 16, 4096, 24, 1)
    trailer = struct.pack(
        "<4sIIIII", b"CEND", sequence, received,
        zlib.crc32(payload) & 0xFFFFFFFF, status, 1,
    )
    ready = struct.pack("<4sIIII", b"CHBR", sequence, status, 0x2004, 4100)
    middle = [payload + trailer] if combined else [payload, trailer]
    return [bytes(header), *middle, ready]


class BatchStreamTests(unittest.TestCase):
    def test_burst_payload_and_separate_trailer(self):
        payload = bytes(range(256)) * 16
        device = FakeDevice(frames(payload))
        data, sequence, _ = read_batch(device, [0x100000], 1, False)
        self.assertEqual(data, payload)
        self.assertEqual(sequence, 7)
        self.assertEqual(device.read_sizes, [512, 4096, 512, 512])

    def test_early_trailer_in_same_usb_transfer(self):
        payload = bytes(range(256)) * 8
        device = FakeDevice(frames(payload, status=7, combined=True))
        with self.assertRaisesRegex(RuntimeError, "SATA FIFO overflow"):
            read_batch(device, [0x100000], 1, False)

    def test_legacy_512_byte_reads_remain_available(self):
        payload = bytes(range(256)) * 16
        header, _, trailer, ready = frames(payload)
        chunks = [payload[index:index + 512]
                  for index in range(0, len(payload), 512)]
        device = FakeDevice([header, *chunks, trailer, ready])
        data, _, _ = read_batch(device, [0x100000], 1, False, 512)
        self.assertEqual(data, payload)
        self.assertEqual(device.read_sizes, [512] * 11)

    def test_mailbox_error_before_batch_header_is_reported(self):
        error = bytearray(32)
        struct.pack_into("<4sHBBI", error, 0, b"CH5K", 32, 3, 1, 8)
        device = FakeDevice([bytes(error)])
        with self.assertRaisesRegex(RuntimeError, "mailbox timeout.*seq=8"):
            read_batch(device, [0x100000], 1, False)


if __name__ == "__main__":
    unittest.main()
