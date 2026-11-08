

"""Exercise the open virtual-console PACKET path without flashing SPI."""

from __future__ import annotations

import struct
from pathlib import Path

from build_c_stage import ROOT, compile_stage
from emulate_stock import run
from image_builder import replace_code1_entry
from inspect_image import ImageError
from probe_console_packets import probe


def exercise(opcode: int, request: bytes, length: int, expected_code: int,
             preface_a1: bool = False, management: bool = True,
             cdb_byte2: int = 0, expected_status: int = 0,
             extra_followups: tuple[tuple[int, bytes, int, int], ...] = (),
             basic_boot: bool = False, dma_probe: bool = False) -> dict:
    image = (Path(__file__).resolve().parents[2] / "88.bin").read_bytes()
    cflags = ("-DOPEN9230_STATIC_BOARD_TEST=1", "-DOPEN9230_STATIC_BOOT_TEST=1",
              "-DSTATIC_TEST_POLL_BUDGET=128u")
    if basic_boot or dma_probe:
        cflags += ("-DOPEN9230_BASIC_BOOT=1",)
    if dma_probe:
        cflags += ("-DOPEN9230_DMA_PROBE=1",)
    payload, symbols = compile_stage(
        ROOT / "build" / "toolchain",
        ROOT / "build" / ("c-stage-console-packet-probe" if dma_probe
                           else "c-stage-console-packet-basic" if basic_boot
                           else "c-stage-console-packet-compare"),
        cflags=cflags,
    )
    opened, _ = replace_code1_entry(image, payload)
    port0_clb, port0_ctba, port0_data = 0x110000000, 0x110002000, 0x110100000
    port0_header = struct.pack("<4I", 0x00010005, 0,
                               port0_ctba & 0xFFFFFFFF, port0_ctba >> 32)
    port0_table = bytearray(0x90)
    port0_table[:16] = bytes((0x27, 0x80, 0xEC, 0)) + bytes(10) + b"\x01\x00"
    struct.pack_into("<4I", port0_table, 0x80,
                     port0_data & 0xFFFFFFFF, port0_data >> 32, 0, 0x800001FF)
    ef_fetched = (struct.pack("<4I", 5, 0, port0_ctba & 0xFFFFFFFF,
                              port0_ctba >> 32)
                  + bytes((0x27, 0x80, 0xEF, 0x03)) + bytes(12))
    received_fis = bytearray(0x100)
    received_fis[0x40:0x50] = bytes((0x34, 0x40, 0x50)) + bytes(13)
    console_ctba, console_data = 0x9C200, 0x9C400
    header = struct.pack("<8I", 0x00010065, 0, console_ctba, 0, 0, 0, 0, 0)
    table = bytearray(0x90)
    table[:20] = bytes((0x27, 0x80, 0xA0, 1, 0, 0, 0, 0x40, 0,
                         length & 0xFF, length >> 8)) + bytes(9)
    table[0x40] = opcode
    table[0x42] = cdb_byte2
    struct.pack_into("<4I", table, 0x80, console_data, 0, 0, length - 1)
    fetched = bytearray(0x100)
    fetched[:32] = header
    fetched[0x10:0x20] = table[:16]
    response_ctba, response_data, response_length = 0x9C600, 0x9C800, 0x24F
    response_header = struct.pack("<8I", 0x00010065, 0, response_ctba, 0,
                                  0, 0, 0, 0)
    response_table = bytearray(0x90)
    response_table[:20] = bytes((0x27, 0x80, 0xA0, 1, 0, 0, 0, 0x40, 0,
                                 response_length & 0xFF,
                                 response_length >> 8)) + bytes(9)
    response_table[0x40] = 0x1C
    response_table[0x42] = 0xE1
    struct.pack_into("<4I", response_table, 0x80,
                     response_data, 0, 0, response_length - 1)
    response_fetched = bytearray(0x100)
    response_fetched[:32] = response_header
    response_fetched[0x10:0x20] = response_table[:16]
    followups = (((bytes(response_fetched),
                   (response_ctba, bytes(response_table)),
                   (response_data, b"\xA5" * response_length)),)
                 if management else ())
    initial_fetched, initial_table, initial_data = (
        bytes(fetched), (console_ctba, bytes(table)),
        (console_data, request.ljust(512, b"\xA5")))
    if preface_a1:
        a1_ctba, a1_data = 0x9CA00, 0x9CC00
        a1_header = struct.pack("<8I", 0x00010005, 0, a1_ctba, 0, 0, 0, 0, 0)
        a1_table = bytearray(0x90)
        a1_table[:16] = bytes((0x27, 0x80, 0xA1)) + bytes(13)
        struct.pack_into("<4I", a1_table, 0x80, a1_data, 0, 0, 0x800001FF)
        a1_fetched = bytearray(0x100)
        a1_fetched[:32] = a1_header
        a1_fetched[0x10:0x20] = a1_table[:16]
        initial_fetched = bytes(a1_fetched)
        initial_table = (a1_ctba, bytes(a1_table))
        initial_data = (a1_data, b"\xA5" * 512)
        followups = ((bytes(fetched), (console_ctba, bytes(table)),
                      (console_data, request.ljust(512, b"\xA5"))), *followups)
    for extra_opcode, extra_request, extra_length, extra_cdb_byte2 in extra_followups:
        extra_fetched = bytearray(0x100)
        extra_fetched[:32] = response_header
        extra_table = bytearray(0x90)
        extra_table[:20] = bytes((0x27, 0x80, 0xA0, 1, 0, 0, 0, 0x40, 0,
                                  extra_length & 0xFF, extra_length >> 8)) + bytes(9)
        extra_table[0x40] = extra_opcode
        extra_table[0x42] = extra_cdb_byte2
        struct.pack_into("<4I", extra_table, 0x80,
                         response_data, 0, 0, extra_length - 1)
        extra_fetched[0x10:0x20] = extra_table[:16]
        followups = (*followups, (bytes(extra_fetched),
                                  (response_ctba, bytes(extra_table)),
                                  (response_data, extra_request.ljust(
                                      max(512, extra_length), b"\xA5"))))
    result = run(
        opened, 1_200_000, allow_modified_image=True,
        code_limit=len(payload), synthetic_sata_idle_pc=symbols["stage_poll_marker"],
        port0_sstatus=0x133, experimental_sata_io=True,
        synthetic_sata_polling=True, synthetic_irq_on_completion_index=2,
        synthetic_open_autofetch_at_enable=True,
        synthetic_open_followup_fetched=ef_fetched,
        synthetic_open_console_fetched=initial_fetched,
        synthetic_open_console_command_table=initial_table,
        synthetic_open_console_prdt_buffer=initial_data,
        synthetic_open_console_followups=followups,
        synthetic_host_command_list=(port0_clb, port0_header),
        synthetic_host_command_table=(port0_ctba, bytes(port0_table)),
        synthetic_host_prdt_buffer=(port0_data, b"\xA5" * 512),
        synthetic_host_cpu_window=dma_probe,
        synthetic_backend_received_fis=bytes(received_fis),
        initial_mmio={0x80002804: 0x80000000, 0x8000C060: 1,
                      0x80002900: port0_clb & 0xFFFFFFFF,
                      0x80002904: port0_clb >> 32, 0x80002918: 1,
                      0x80002938: 1},
        report_memory_ranges=[(0x80002C80, 0x40), (0x0400023C, 0x10),
                              (0x5000C400, 0x80), (0x5000C800, 0x80)],
    )
    marker = f"HOST_CONSOLE OP=000000A0 CODE={expected_code:08X} STATUS="
    if marker not in result["uart"]:
        raise ImageError(f"PACKET {opcode:02X} not processed: {result['uart'][-500:]}")
    port = bytes.fromhex(result["memory_snapshots"]["0x80002C80"])
    if struct.unpack_from("<I", port, 0x38)[0] & 1:
        raise ImageError(f"PACKET {opcode:02X} left slot 0 active")
    if result["synthetic_open_console_followups_delivered"] != len(followups):
        raise ImageError("console follow-up count mismatch")
    if management:
        if "HOST_CONSOLE OP=000000A0 CODE=0000001C STATUS=00000000 EVENT=00000001" not in result["uart"]:
            raise ImageError("management response PACKET 1C was not completed")
        response = bytes.fromhex(result["memory_snapshots"]["0x5000C800"])
        if (response[0] != 0xE1 or response[8] != request[8] or
                response[0x18] != expected_status):
            raise ImageError("management reply content mismatch")
    if preface_a1 and "HOST_CONSOLE OP=000000A1 CODE=00000000 STATUS=00000000 EVENT=00000001" not in result["uart"]:
        raise ImageError("A1 preface did not complete")
    return result


def main() -> None:
    request = bytearray(99)
    request[0] = 0xE0
    request[8] = 0xFD
    request[0x38:0x3C] = (0x25).to_bytes(4, "little")
    request[0x3C] = 0xA4
    request[0x4C:0x4E] = (0x10).to_bytes(2, "little")
    request[0x56:0x58] = (0x6AC6).to_bytes(2, "little")
    request[0x58:0x5A] = (0xBD8B).to_bytes(2, "little")
    result = exercise(0x1D, bytes(request), 99, 0xFD1D)
    if "STATUS=00000000" not in result["uart"]:
        raise ImageError("FD/A4 did not succeed")
    seconds = struct.unpack_from("<I", bytes.fromhex(
        result["memory_snapshots"]["0x0400023C"]), 4)[0]
    if seconds != 0x6AC6BD8B:
        raise ImageError(f"OS time mismatch: {seconds:08X}")
    stock = probe((Path(__file__).resolve().parents[2] / "88.bin").read_bytes(),
                  0x1D, bytes(request), 99)
    stock_reply = bytes.fromhex(stock["memory_snapshots"]["0x30065468"])
    open_reply = bytes.fromhex(result["memory_snapshots"]["0x5000C800"])
    if stock_reply[:99] != open_reply[:99]:
        raise ImageError("FD/A4 reply differs from the stock handler")
    print("open FD/A4: packet completed, OS time synchronized")
    version = bytearray(62)
    version[0] = 0xE0
    version[8:12] = bytes((0xE1, 0x10, 0x09, 0))
    version[12:16] = bytes((1, 0, 0, 0xF4))
    version[16] = 3
    result = exercise(0x1D, bytes(version), 62, 0xE11D)
    if "STATUS=00000000" not in result["uart"]:
        raise ImageError("E1/10/09 version request did not succeed")
    stock = probe((Path(__file__).resolve().parents[2] / "88.bin").read_bytes(),
                  0x1D, bytes(version), 62, ssd=True)
    if "BIOS ver from option rom : 1 0 0 3f4" not in stock["uart"]:
        raise ImageError("stock E1/10/09 callback was not reached")
    stock_reply = bytes.fromhex(stock["memory_snapshots"]["0x30065468"])
    open_reply = bytes.fromhex(result["memory_snapshots"]["0x5000C800"])
    if open_reply[:62] != stock_reply[:62]:
        raise ImageError("E1/10/09 reply differs from stock")
    print("open E1/10/09 version request: packet and response completed")
    ui_query = bytearray(62)
    ui_query[0] = 0xE0
    ui_query[8:12] = bytes((0xE1, 0x10, 0x01, 1))
    result = exercise(0x1D, bytes(ui_query), 62, 0xE11D,
                      expected_status=0xFF)
    if "STATUS=000000FF" not in result["uart"]:
        raise ImageError("E1/10/01 inactive UI query did not return 0xff")
    print("open E1/10/01 inactive UI query: status ff")
    result = exercise(0x1D, bytes(request), 99, 0xFD1D, preface_a1=True)
    print("open A1 -> FD/A4 -> 1C: all three commands completed without a CI gap")
    repeated = exercise(
        0x1D, bytes(request), 99, 0xFD1D, management=False,
        extra_followups=((0x1D, bytes(request), 99, 0),))
    if repeated["uart"].count(
            "HOST_CONSOLE OP=000000A0 CODE=0000FD1D STATUS=00000000 EVENT=00000001") != 2:
        raise ImageError("two identical PACKET requests were not both completed")
    print("two identical PACKET requests each retire their host slot")
    for opcode, length, cdb_byte2 in ((0x03, 19, 0), (0x12, 44, 0),
                                       (0x46, 32, 0), (0x5A, 32, 0x2A)):
        opened = exercise(opcode, b"\xA5" * length, length, opcode,
                          management=False, cdb_byte2=cdb_byte2)
        stock = probe((Path(__file__).resolve().parents[2] / "88.bin").read_bytes(),
                      opcode, b"\xA5" * length, length,
                      cdb=bytes((opcode, 0, cdb_byte2)))
        observed = bytes.fromhex(opened["memory_snapshots"]["0x5000C400"])
        reference = bytes.fromhex(stock["host_data_prefix"])
        if observed[:length] != reference[:length]:
            differences = [(i, observed[i], reference[i]) for i in range(length)
                           if observed[i] != reference[i]]
            raise ImageError(f"SCSI {opcode:02X} response differs from stock: {differences[:12]}")
        print(f"open SCSI {opcode:02X}: {length} response bytes match stock")
    physical_query = bytearray(591)
    physical_query[0] = 0xE0
    physical_query[8:10] = bytes((0xF3, 3))
    physical_query[0x17] = 1
    physical_query[0x38:0x3C] = (0x211).to_bytes(4, "little")
    physical_query[0x3D] = 2
    physical_query[0x40:0x44] = (1).to_bytes(4, "little")
    opened = exercise(0x1D, bytes(physical_query), 591, 0xF31D)
    stock = probe((Path(__file__).resolve().parents[2] / "88.bin").read_bytes(),
                  0x1D, bytes(physical_query), 591, ssd=True)
    open_reply = bytes.fromhex(opened["memory_snapshots"]["0x5000C800"])
    stock_reply = bytes.fromhex(stock["memory_snapshots"]["0x30065468"])
    if open_reply != stock_reply[:len(open_reply)]:
        differences = [(i, open_reply[i], stock_reply[i])
                       for i in range(len(open_reply)) if open_reply[i] != stock_reply[i]]
        raise ImageError(f"F3/03 physical-disk reply differs: {differences[:12]}")
    print("open F3/03: one-SSD management reply matches stock")


if __name__ == "__main__":
    main()
