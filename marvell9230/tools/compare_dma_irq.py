

"""Exercise stock frontend DMA IRQ and completion-ring paths offline."""

from __future__ import annotations

import argparse
from pathlib import Path

from emulate_stock import run
from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary


DMA_STATUS = 0x8000C040
DMA_PRODUCER = 0x8000C030
COMPLETION_RING = 0x30060F24
CONTEXT_SLOTS = 0x0400551C
SCRATCH_CONTEXTS = 0x0400F000


def word(snapshot: str, offset: int = 0) -> int:
    return int.from_bytes(bytes.fromhex(snapshot)[offset:offset + 4], "little")


def sample(image: bytes, irq_status: int, producer: int = 8,
           completion_words: tuple[int, ...] = ()) -> dict:
    ram = {}
    for index, completion in enumerate(completion_words):
        context = SCRATCH_CONTEXTS + index * 0x20
        ram[COMPLETION_RING + index * 4] = completion
        ram[CONTEXT_SLOTS + index * 4] = context
        for field in range(0, 0x10, 4):
            ram[context + field] = 0
    return run(
        image, 3_000_000, capture_mmio=True,
        inject_irq_at_pc=0xE8, injected_irq_pending=0x4,
        debug_mmio_writes={DMA_STATUS: irq_status, DMA_PRODUCER: producer},
        debug_ram_writes=ram,
        report_memory_ranges=[(0x04005518, 0xC), (SCRATCH_CONTEXTS, 0x50)],
    )


def check_irq(sample_result: dict, status: int) -> None:
    trace = sample_result["mmio_trace"]
    ack = [event for event in trace if event["op"] == "write" and
           event["addr"] == f"0x{DMA_STATUS:08X}" and
           int(event["value"], 16) == status]
    if not sample_result["debug_irq_injected"] or sample_result["irq_vector_visits"] < 2 or not ack:
        raise ImageError(f"DMA IRQ status 0x{status:X} did not reach stock handler")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        image = args.image.read_bytes()
        if image_summary(image)["spi_sha256"] != REFERENCE_SHA256:
            raise ImageError("this comparison requires the analyzed stock 88.bin")
        for status, expected in ((0x1, "dma interrupt without completion entry??? (8 8)"),
                                 (0x4, "DMA_PARITY_ERR_IRQ"),
                                 (0x8, "DMA_UR_ERR_IRQ")):
            result = sample(image, status)
            check_irq(result, status)
            if expected not in result["uart"]:
                raise ImageError(f"DMA IRQ status 0x{status:X} missed expected UART line")
            print(f"DMA IRQ status=0x{status:X}: ack and {expected}")
        for producer, completions, statuses in (
            (0, (0,), (0x02,)),
            (0, (0x40000,), (0x81,)),
            (1, (0, 1), (0x02, 0x02)),
        ):
            result = sample(image, 1, producer, completions)
            check_irq(result, 1)
            snapshots = result["memory_snapshots"]
            slots = snapshots["0x04005518"]
            contexts = snapshots[f"0x{SCRATCH_CONTEXTS:08X}"]
            if word(slots) != producer or any(word(slots, 4 + i * 4) != 0
                                               for i in range(len(completions))):
                raise ImageError("stock DMA ring cursor or context release mismatch")
            if any(bytes.fromhex(contexts)[i * 0x20 + 1] != expected
                   for i, expected in enumerate(statuses)):
                raise ImageError("stock DMA completion status mismatch")
            print(f"DMA producer={producer}, completions={len(completions)}: " +
                  ", ".join(f"0x{value:02X}" for value in statuses))
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
