

"""List open-stage gaps against the stock Option ROM packet sequence."""

from __future__ import annotations

import re

from compare_console_packet import exercise
from inspect_image import ImageError
from probe_option_rom_sequence import build_packets


def main() -> None:
    packets = build_packets()
    first = packets[0]
    result = exercise(
        first[1], first[2], first[3], 0xE11D,
        preface_a1=True, management=False,
        dma_probe=True,
        extra_followups=tuple((opcode, request, length,
                               cdb[2] if len(cdb) > 2 else 0)
                              for _, opcode, request, length, cdb in packets[1:]),
    )
    lines = re.findall(
        r"HOST_CONSOLE OP=000000A0 CODE=([0-9A-F]{8}) "
        r"STATUS=([0-9A-F]{8}) EVENT=00000001", result["uart"])
    if len(lines) != len(packets):
        raise ImageError(f"expected {len(packets)} packet completions, got {len(lines)}")
    gaps = []
    for packet, (code, status) in zip(packets, lines):
        print(f"{packet[0]}: code={code} open_status={status}")
        if status != "00000000":
            gaps.append(packet[0])
    print(f"stock_status=00000000 for all {len(packets)} commands")
    print("remaining management status gaps:", ", ".join(gaps) or "none")


if __name__ == "__main__":
    main()
