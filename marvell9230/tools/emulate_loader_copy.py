

"""Exercise the stock ARM loader's MAGIIMGF copy routine in Unicorn.

The fixture begins at the observed segment-copy function, after the board's
boot ROM has loaded the loader. It does not emulate PCI enumeration or SPI
autoloader hardware.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from inspect_image import ImageError, image_summary


LOADER_BASE = 0x0400C000
COPY_ENTRY = LOADER_BASE + 0x18C
RETURN_SENTINEL = 0x04020000


def verify_loader_copy(image: bytes) -> int:
    from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_MODE_ARM, Uc
    from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP

    layout = image_summary(image)
    if len(image) != 0x80000 or layout["segment_count"] != 4:
        raise ImageError("unexpected SPI layout for stock loader fixture")
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in (
        (0x00000000, 0x30000), (0x04000000, 0x100000),
        (0x30000000, 0x80000), (0xF8064000, 0x80000),
        (0xFFFF0000, 0x10000), (0x80002000, 0x1000),
        (0x8000A000, 0x1000), (0xD0030000, 0x1000),
        (0xD0032000, 0x1000),
    ):
        uc.mem_map(base, size)


    uc.mem_write(LOADER_BASE, image[0xC000:0x20000])
    uc.mem_write(0xFFFF0000, image[0xC000:0x1C000])
    uc.mem_write(0xF8064000, image)
    uc.mem_write(0xD0030000, (0x92301B4B).to_bytes(4, "little"))
    uc.mem_write(0x80002800, (3).to_bytes(4, "little"))
    uc.reg_write(UC_ARM_REG_PC, COPY_ENTRY)
    uc.reg_write(UC_ARM_REG_SP, 0x04080000)
    uc.reg_write(UC_ARM_REG_LR, RETURN_SENTINEL)
    returned = False
    unmapped: list[int] = []

    def on_code(emu: Uc, address: int, _size: int, _user: object) -> None:
        nonlocal returned
        if address == RETURN_SENTINEL:
            returned = True
            emu.emu_stop()

    def on_unmapped(_emu: Uc, _access: int, address: int,
                    _size: int, _value: int, _user: object) -> bool:
        unmapped.append(address)
        return False

    uc.hook_add(UC_HOOK_CODE, on_code)
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)
    try:
        uc.emu_start(COPY_ENTRY, 0xFFFFFFFF, count=300000)
    except Exception as exc:
        raise ImageError(f"stock loader copy fault at {unmapped or 'mapped address'}: {exc}") from exc
    if not returned:
        raise ImageError("stock loader did not return within 300000 instructions")
    for segment in layout["segments"]:
        source = int(segment["spi_source"], 16)
        destination = int(segment["destination"], 16)
        size = int(segment["size"], 16)

        copied_size = (size + 7) & ~7
        if source + copied_size > len(image):
            raise ImageError(f"segment {segment['index']} copy exceeds SPI image")
        if bytes(uc.mem_read(destination, copied_size)) != image[source:source + copied_size]:
            raise ImageError(f"loader did not copy segment {segment['index']} including padding")
    return len(layout["segments"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        copied = verify_loader_copy(args.image.read_bytes())
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"stock ARM loader copied {copied} MAGIIMGF segments, including 8-byte padding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
