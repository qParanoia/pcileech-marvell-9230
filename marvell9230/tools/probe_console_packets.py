

"""Explore stock 88SE9230 virtual-console PACKET commands offline."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from emulate_stock import run


def probe(image: bytes, opcode: int, request: bytes, packet_length: int = 0x63,
          ssd: bool = False, natural: bool = False,
          cdb: bytes = b"", trace_after_pc: int | None = None,
          watch_ram_writes: tuple[int, ...] = (),
          followups: tuple[tuple[int, bytes, int, bytes], ...] = (),
          max_steps: int = 9_000_000) -> dict:
    host_clb = 0x000000000009C000
    host_ctba = 0x000000000009C200
    host_data = 0x000000000009C400
    def packet(packet_opcode: int, payload: bytes, length: int,
               packet_cdb: bytes) -> tuple[bytes, bytes, bytes]:
        header = struct.pack("<8I", 0x00010065, 0, host_ctba, 0, 0, 0, 0, 0)
        table = bytearray(0x90)
        table[0:20] = bytes((0x27, 0x80, 0xA0, 0x01,
                             0, 0, 0, 0x40, 0, length & 0xFF,
                             length >> 8, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        table[0x40] = packet_opcode
        table[0x40:0x40 + len(packet_cdb)] = packet_cdb
        struct.pack_into("<4I", table, 0x80, host_data, 0, 0, length - 1)
        data = bytes(payload).ljust(max(512, length), b"\xA5")
        return header, bytes(table), data

    header, table, original = packet(opcode, request, packet_length, cdb)
    followup_packets = tuple(packet(*items) for items in followups)
    result = run(
        image, max_steps, capture_mmio=True,
        fast_delays=True,
        port0_sstatus=0x133 if ssd else 0,
        experimental_sata_io=ssd,
        synthetic_host_ghc_sequence=(0x80000000,),
        synthetic_host_port_command_issue=1,
        synthetic_host_port_index=7,
        synthetic_frontend_worker_once=not natural,
        synthetic_frontend_stack_top=0x040FF000 if not natural else None,
        synthetic_frontend_consumer_once=not natural,
        synthetic_backend_task_drain_once=not natural,
        synthetic_host_command_list=(host_clb, header),
        synthetic_host_command_table=(host_ctba, table),
        synthetic_host_prdt_buffer=(host_data, original),
        synthetic_stock_host_followups=followup_packets,
        synthetic_host_cpu_window=True,
        trace_after_pc=trace_after_pc,
        trace_after_limit=80,
        watch_ram_writes=watch_ram_writes,
        code_visit_addresses=(0x9558, 0x9864, 0x987E, 0x9938,
                              0x9A38, 0x9A5C, 0x88B4, 0x854C,
                              0x30054554, *range(0x3007EA20, 0x3007EA52, 2),
                              0x3007EA92, 0x3007EABE, 0x3007EACE,
                              0x3007EAEA, 0x3007E95C, 0x3007AFB4,
                              0x3007AFBC, 0x3007AFC4, 0x3007F0D4,
                              0x30053CA4,
                              0x34D8, 0x33598),
        report_memory_ranges=[(0x040055E0, 0x80),
                              (0x040055FC, 0x100),
                              (0x04000230, 0x40),
                              (0x04008100, 0x80),
                              (0x04009A70, 0x80),
                              (0x30065468, 0x100),
                              (0x3007F648, 0x80),
                              (0x30001C00, 0x100),
                              (0x80002C80, 0x40)],
    )
    mmio = [e for e in result.pop("mmio_trace")
            if e["op"] == "write" and
            (e["addr"].startswith("0x80002C") or
             e["addr"] in ("0x80002808", "0x8000C084"))]
    result["selected_mmio_writes"] = mmio[-60:]
    data = bytes.fromhex(result.pop("synthetic_host_prdt_data"))
    result["host_data_prefix"] = data[:128].hex()
    result["host_data_changed"] = sum(a != b for a, b in zip(data, original))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opcode", type=lambda s: int(s, 0), default=0x1D)
    parser.add_argument("--length", type=lambda s: int(s, 0), default=0x63)
    parser.add_argument("--request-hex", default="")
    parser.add_argument("--ssd", action="store_true")
    parser.add_argument("--natural", action="store_true")
    parser.add_argument("--cdb-hex", default="")
    args = parser.parse_args()
    request = bytes.fromhex(args.request_hex) if args.request_hex else bytearray(512)
    if not args.request_hex:
        request[0] = 0xE0
        request[8:12] = bytes((0xE1, 0x10, 0x09, 0))
        request[12:16] = bytes((1, 0, 0, 0xF4))
        request[16] = 3
    image = (Path(__file__).resolve().parents[2] / "88.bin").read_bytes()
    result = probe(image, args.opcode, bytes(request), args.length,
                   args.ssd, args.natural, bytes.fromhex(args.cdb_hex))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
