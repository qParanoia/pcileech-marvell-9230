

"""Inspect the SPI image and the MAGIIMGF table used by the 88SE9230 loader.

This tool reads an existing image. It does not modify or redistribute any part
of the vendor firmware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


MAGIC = b"MAGIIMGF"
MIN_DESCRIPTOR_SIZE = 0x20
MAX_SEGMENTS = 32


class ImageError(ValueError):
    pass


def u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ImageError(f"32-bit read outside image at 0x{offset:x}")
    return struct.unpack_from("<I", data, offset)[0]


def parse_container(data: bytes, base: int) -> dict:
    count = u32(data, base + 0x18)
    stride = u32(data, base + 0x1C)
    table_offset = u32(data, base + 0x20)
    if not 1 <= count <= MAX_SEGMENTS:
        raise ImageError(f"implausible segment count: {count}")
    if not MIN_DESCRIPTOR_SIZE <= stride <= 0x1000 or stride % 4:
        raise ImageError(f"implausible descriptor size: 0x{stride:x}")
    if base + table_offset + count * stride > len(data):
        raise ImageError("segment table extends beyond SPI image")

    segments = []
    for index in range(count):
        desc = base + table_offset + index * stride
        destination = u32(data, desc + 0x10)
        size = u32(data, desc + 0x14)
        relative_source = u32(data, desc + 0x18)
        source = base + relative_source
        if size == 0 or source < base or source + size > len(data):
            raise ImageError(f"segment {index} has invalid source or size")
        tag = data[desc : desc + 16]
        tag_ascii = "".join(chr(c) if 32 <= c < 127 else "." for c in tag)
        segments.append(
            {
                "index": index,
                "tag_ascii": tag_ascii,
                "descriptor_offset": f"0x{desc:x}",
                "destination": f"0x{destination:08x}",
                "size": f"0x{size:x}",
                "spi_source": f"0x{source:x}",
                "spi_end": f"0x{source + size:x}",
                "sha256": hashlib.sha256(data[source : source + size]).hexdigest(),
            }
        )

    return {
        "firmware_header_offset": f"0x{base:x}",
        "header_word_08_unknown": f"0x{u32(data, base + 0x08):08x}",
        "header_word_28_unknown": f"0x{u32(data, base + 0x28):08x}",
        "segment_count": count,
        "descriptor_size": f"0x{stride:x}",
        "descriptor_table_relative_offset": f"0x{table_offset:x}",
        "segments": segments,
    }


def image_summary(data: bytes) -> dict:
    candidates = []
    search_at = 0
    while (base := data.find(MAGIC, search_at)) >= 0:
        try:
            candidates.append(parse_container(data, base))
        except ImageError:

            pass
        search_at = base + len(MAGIC)
    if not candidates:
        raise ImageError("no valid MAGIIMGF segment table found")
    if len(candidates) != 1:
        raise ImageError("multiple valid MAGIIMGF segment tables found")

    manifest = []
    if len(data) >= 0x3000:
        for line in data[0x2000:0x3000].splitlines():
            line = line.split(b"\0", 1)[0].strip(b"\xff \r\n")
            if b"VERSION[" in line:
                manifest.append(line.decode("ascii", errors="replace"))

    return {
        "spi_size": f"0x{len(data):x}",
        "spi_sha256": hashlib.sha256(data).hexdigest(),
        "autoload_signature": data[:4].hex(),
        "option_rom_signature": data[0x20000:0x20002].hex(),
        "manifest": manifest,
        **candidates[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="SPI flash dump to inspect")
    args = parser.parse_args()
    try:
        result = image_summary(args.image.read_bytes())
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
