

"""Assemble a small standalone ARM-state RAM stage with Keystone."""

from __future__ import annotations

from pathlib import Path

from inspect_image import ImageError


def assemble_arm(source: Path, max_bytes: int = 1024) -> bytes:
    try:
        from keystone import KS_ARCH_ARM, KS_MODE_ARM, KS_MODE_LITTLE_ENDIAN, Ks
    except ImportError as exc:
        raise ImageError("keystone-engine Python package is required") from exc
    try:
        encoding, _ = Ks(KS_ARCH_ARM, KS_MODE_ARM | KS_MODE_LITTLE_ENDIAN).asm(
            source.read_text(encoding="utf-8"), addr=0
        )
    except Exception as exc:
        raise ImageError(f"ARM assembly failed: {exc}") from exc
    payload = bytes(encoding)
    if len(payload) % 4 or len(payload) > max_bytes:
        raise ImageError(f"unexpected ARM payload size: {len(payload)}")
    return payload
