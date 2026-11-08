

"""Build a local, hybrid SPI image with an open proof-of-execution payload.

The output retains the vendor autoload, loader, Option ROM and unused firmware
segments from a user-supplied template. It is for isolated bring-up only; it
is not a distributable open firmware or a functional SATA controller.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from image_builder import replace_code1_entry
from inspect_image import ImageError


MARKER_ADDRESS = 0x04001000
MARKER_VALUE = 0x9230B007
MESSAGE = b"OPEN9230\r\n\0"
MESSAGE_BYTES = ", ".join(f"0x{value:02x}" for value in MESSAGE)
SOURCE = f"""
    b start
    b halt
    b halt
    b halt
    b halt
    b halt
    b halt
    b halt
start:
    ldr r0, marker_address
    ldr r1, marker_value
    str r1, [r0]
    ldr r0, uart0_base
    mov r1, #0
    strb r1, [r0, #4]
    mov r1, #0x80
    strb r1, [r0, #0xc]
    mov r1, #0xa2
    strb r1, [r0]
    mov r1, #0
    strb r1, [r0, #4]
    mov r1, #3
    strb r1, [r0, #0xc]
    mov r1, #7
    strb r1, [r0, #8]
    adr r2, message
send_next:
    ldrb r1, [r2], #1
    cmp r1, #0
    beq halt
wait_tx_ready:
    ldrb r3, [r0, #0x14]
    tst r3, #0x20
    beq wait_tx_ready
    strb r1, [r0]
    b send_next
halt:
    b halt
marker_address:
    .word 0x{MARKER_ADDRESS:08x}
marker_value:
    .word 0x{MARKER_VALUE:08x}
uart0_base:
    .word 0xd0072000
message:
    .byte {MESSAGE_BYTES}
    .align 2
"""


def assemble_probe() -> bytes:
    try:
        from keystone import KS_ARCH_ARM, KS_MODE_ARM, KS_MODE_LITTLE_ENDIAN, Ks
    except ImportError as exc:
        raise ImageError("keystone-engine Python package is required") from exc
    assembler = Ks(KS_ARCH_ARM, KS_MODE_ARM | KS_MODE_LITTLE_ENDIAN)
    try:
        encoding, _ = assembler.asm(SOURCE, addr=0)
    except Exception as exc:
        raise ImageError(f"ARM probe assembly failed: {exc}") from exc
    payload = bytes(encoding)
    if len(payload) % 4 or len(payload) > 256:
        raise ImageError("unexpected ARM probe size")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.template.resolve() == args.output.resolve():
        parser.error("output must differ from template")
    try:
        template = args.template.read_bytes()
        probe = assemble_probe()
        data, start = replace_code1_entry(template, probe)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"output: {args.output.resolve()}")
    print(f"probe: {len(probe)} bytes at SPI 0x{start:x}, RAM 0x00000000")
    print(f"UART0 after boot: {MESSAGE[:-1].decode('ascii')!r} at 115200 8N1 (when pins enabled)")
    print(f"Optional JTAG marker: [0x{MARKER_ADDRESS:08x}] = 0x{MARKER_VALUE:08x}")
    print(f"SHA-256: {hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
