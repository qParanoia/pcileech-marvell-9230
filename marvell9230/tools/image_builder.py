
"""Build local experimental images from the exact analyzed SPI dump."""

from __future__ import annotations

import hashlib

from inspect_image import ImageError, image_summary


REFERENCE_SHA256 = "dd2ab739e4776d4687a1c067e2a85f17c39a3a6d96fb1ee711221560e989694f"


def disable_option_rom(image: bytes) -> bytes:
    """Diagnostic: erase only the known legacy Option ROM SPI region.

    Does not disable the PCI ROM BAR or prove what a motherboard will execute.
    Autoload, the ARM loader and MAGIIMGF container stay byte-for-byte intact.
    """
    if len(image) != 0x80000 or image[0x20000:0x20002] != b'\x55\xAA':
        raise ImageError('unexpected image size or Option ROM signature')
    if image[0x30000:0x30008] != b'MAGIIMGF':
        raise ImageError('unexpected firmware container boundary')
    return image[:0x20000] + b'\xFF' * 0x10000 + image[0x30000:]


def replace_code1_entry(template: bytes, payload: bytes) -> tuple[bytes, int]:
    """Replace only the beginning of the first segment; return image and SPI offset."""
    if hashlib.sha256(template).hexdigest() != REFERENCE_SHA256:
        raise ImageError("template SHA-256 differs from the analyzed 88.bin")
    layout = image_summary(template)
    if layout["segment_count"] != 4:
        raise ImageError("reference image segment count changed")
    code1 = layout["segments"][0]
    if code1["destination"] != "0x00000000":
        raise ImageError("first segment does not load at address zero")
    if layout["autoload_signature"] != "a5a5a5a5":
        raise ImageError("unexpected autoload signature")
    start = int(code1["spi_source"], 16)
    capacity = int(code1["size"], 16)
    if len(payload) > capacity:
        raise ImageError("payload exceeds first code segment")
    image = bytearray(template)
    image[start : start + len(payload)] = payload
    return bytes(image), start
