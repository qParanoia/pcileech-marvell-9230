

"""Small, deterministic ATA IDENTIFY DEVICE response for emulator probes."""

from __future__ import annotations

import struct


def synthetic_ssd_identify(logical_sector_bytes: int = 512) -> bytes:
    if logical_sector_bytes not in (512, 4096):
        raise ValueError("synthetic SSD supports 512- or 4096-byte logical sectors")
    words = [0] * 256
    words[0] = 0x0040
    words[49] = 1 << 9
    words[60] = 0x0000
    words[61] = 0x0800
    words[80] = 0x07F8
    words[83] = 1 << 10
    words[100] = 0x0000
    words[101] = 0x0800
    if logical_sector_bytes != 512:
        words[106] = 0x5000
        words[117] = logical_sector_bytes // 2
    words[169] = 1
    words[217] = 1

    def ata_string(start: int, length: int, value: str) -> None:
        raw = value.encode("ascii").ljust(length * 2, b" ")[: length * 2]
        for i in range(length):
            words[start + i] = (raw[2 * i] << 8) | raw[2 * i + 1]

    ata_string(10, 10, "EMULATED0000000001")
    ata_string(23, 4, "0.1")
    ata_string(27, 20, "OPEN9230 SYNTHETIC SSD")
    return struct.pack("<256H", *words)
