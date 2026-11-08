

"""Bounded Unicorn run of the stock RAM image with a minimal MMIO fixture.

This is a reverse-engineering aid, not a hardware model. Unknown MMIO pages
are zero-filled and reported; instruction fetch from them stops the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter, deque
from pathlib import Path

from image_builder import REFERENCE_SHA256
from inspect_image import ImageError, image_summary
from ata_identify import synthetic_ssd_identify


def _synthetic_rw_location(opcode: int, fis: bytes) -> tuple[int, int]:
    """Decode the ATA address/count used by the synthetic disk fixture."""
    if opcode in (0xC8, 0xCA):
        lba = int.from_bytes(fis[4:7], "little") | ((fis[7] & 0x0F) << 24)
        return lba, fis[12] or 256
    lba = int.from_bytes(fis[4:7] + fis[8:11], "little")
    return lba, int.from_bytes(fis[12:14], "little") or 65536


def run(
    image: bytes,
    max_steps: int,
    capture_mmio: bool = False,
    allow_modified_image: bool = False,
    port0_sstatus: int = 0,
    fast_delays: bool = False,
    experimental_sata_io: bool = False,
    synthetic_sata_polling: bool = False,
    synthetic_irq_on_completion_index: int | None = None,
    synthetic_sata_error_on_completion_index: int | None = None,
    synthetic_sata_idle_pc: int = 0xE8,
    inject_irq_at_pc: int | None = None,
    injected_irq_pending: int = 1,
    host_ghc_on_debug_irq: int | None = None,
    debug_mmio_writes: dict[int, int] | None = None,
    debug_ram_writes: dict[int, int] | None = None,
    synthetic_host_ghc_sequence: tuple[int, ...] = (),
    synthetic_host_port_command_issue: int | None = None,
    synthetic_host_port_index: int = 0,
    synthetic_frontend_worker_once: bool = False,
    synthetic_frontend_stack_top: int | None = None,
    synthetic_frontend_consumer_once: bool = False,
    synthetic_backend_task_drain_once: bool = False,
    synthetic_host_autofetch_header: bytes = b"",
    synthetic_host_command_list: tuple[int, bytes] | None = None,
    synthetic_host_command_table: tuple[int, bytes] | None = None,
    synthetic_host_prdt_buffer: tuple[int, bytes] | None = None,
    synthetic_host_prdt_layout: tuple[tuple[int, int], ...] | None = None,
    synthetic_host_rfis_buffer: tuple[int, bytes] | None = None,
    synthetic_stock_host_followups: tuple[tuple[bytes, bytes, bytes], ...] = (),
    synthetic_host_cpu_window: bool = False,
    synthetic_host_cpu_header_corrupt: bool = False,
    synthetic_host_cpu_header_at_aligned_base: bool = False,
    synthetic_backend_received_fis: bytes | None = None,
    synthetic_open_autofetch_at_enable: bool = False,
    synthetic_open_followup_fetched: bytes = b"",
    synthetic_open_followup_table: bytes = b"",
    synthetic_disk_model: bool = False,
    synthetic_clear_prdt_on_followup: bool = False,
    synthetic_logical_sector_bytes: int = 512,
    synthetic_open_console_fetched: bytes = b"",
    synthetic_open_console_command_table: tuple[int, bytes] | None = None,
    synthetic_open_console_prdt_buffer: tuple[int, bytes] | None = None,
    synthetic_open_console_followups: tuple[
        tuple[bytes, tuple[int, bytes], tuple[int, bytes]], ...
    ] = (),
    synthetic_open_host_issue_after_marker: bool = False,
    synthetic_open_port_reset_after_marker: bool = False,
    code_visit_addresses: tuple[int, ...] = (),
    trace_after_pc: int | None = None,
    trace_after_limit: int = 0,
    watch_ram_writes: tuple[int, ...] = (),
    report_memory_ranges: list[tuple[int, int]] | None = None,
    code_limit: int | None = None,
    initial_mmio: dict[int, int] | None = None,
    initial_ram: dict[int, bytes] | None = None,
    uart_input: bytes = b"",
) -> dict:
    from unicorn import (
        UC_ARCH_ARM,
        UC_HOOK_CODE,
        UC_HOOK_MEM_READ,
        UC_HOOK_MEM_UNMAPPED,
        UC_HOOK_MEM_WRITE,
        UC_MEM_FETCH_UNMAPPED,
        UC_MEM_WRITE_UNMAPPED,
        UC_MODE_ARM,
        Uc,
        UcError,
    )
    from unicorn.arm_const import UC_ARM_REG_CPSR, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_SPSR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_R6, UC_ARM_REG_R9, UC_ARM_REG_R11

    layout = image_summary(image)
    if not allow_modified_image and layout["spi_sha256"] != REFERENCE_SHA256:
        raise ImageError("input SHA-256 differs from the analyzed 88.bin")
    if layout["spi_size"] != "0x80000" or layout["segment_count"] != 4:
        raise ImageError("unexpected SPI image layout")
    if synthetic_logical_sector_bytes not in (512, 4096):
        raise ImageError("synthetic disk supports 512- or 4096-byte logical sectors")
    if synthetic_clear_prdt_on_followup and not synthetic_disk_model:
        raise ImageError("clearing synthetic PRDT before follow-up requires the disk model")
    if synthetic_host_prdt_buffer is not None:
        if synthetic_host_command_table is None:
            raise ImageError("synthetic host PRDT buffer requires a command table")
        host_data_address, host_data_initial = synthetic_host_prdt_buffer
        if (host_data_address & 1 or not 0 <= host_data_address < 1 << 64
                or not 0 < len(host_data_initial) <= 131072):
            raise ImageError("synthetic host PRDT buffer must be 1..131072 bytes at an aligned bus address")
        host_data = bytearray(host_data_initial)
        if synthetic_host_prdt_layout is not None:
            if (not synthetic_host_prdt_layout or
                    sum(length for _, length in synthetic_host_prdt_layout) != len(host_data) or
                    any(address & 1 or length <= 0 or length > 0x400000 or
                        address < 0 or address + length > 1 << 64
                        for address, length in synthetic_host_prdt_layout)):
                raise ImageError("invalid synthetic fragmented PRDT layout")
    else:
        if synthetic_host_prdt_layout is not None:
            raise ImageError("synthetic PRDT layout requires a data buffer")
        host_data = None
    if synthetic_host_rfis_buffer is not None:
        rfis_address, rfis_initial = synthetic_host_rfis_buffer
        if (rfis_address & 0xFF or not 0 <= rfis_address < 1 << 64 or
                len(rfis_initial) != 0x100):
            raise ImageError("synthetic host RFIS needs a 256-byte aligned bus buffer")
    host_table = bytearray(synthetic_host_command_table[1]) if synthetic_host_command_table else None
    disk_sectors: dict[int, bytes] = {}
    if synthetic_backend_received_fis is not None and len(synthetic_backend_received_fis) != 0x100:
        raise ImageError("synthetic backend received-FIS area must be 256 bytes")
    if synthetic_open_console_prdt_buffer is not None and (
            synthetic_open_console_command_table is None or
            not 0 < len(synthetic_open_console_prdt_buffer[1]) <= 4096):
        raise ImageError("synthetic console PRDT needs a table and 1..4096-byte buffer")
    if not 0 <= synthetic_host_port_index < 8:
        raise ImageError("synthetic host port index must be 0..7")

    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mapped = set()

    def map_region(base: int, length: int) -> None:
        aligned = (base + length + 0xFFF) & ~0xFFF
        for page in range(base & ~0xFFF, aligned, 0x1000):
            if page not in mapped:
                uc.mem_map(page, 0x1000)
                mapped.add(page)

    for base, length in [
        (0x00000000, 0x20000),
        (0x04000000, 0x100000),
        (0x30000000, 0x80000),
        (0x80003000, 0x1000),
        (0xD0072000, 0x1000),
        (0xF8064000, len(image)),
    ]:
        map_region(base, length)
    if (synthetic_host_cpu_window or synthetic_open_console_command_table is not None
            or synthetic_host_rfis_buffer is not None):
        map_region(0x50000000, 0x10000)
    uc.mem_write(0xF8064000, image)
    for seg in layout["segments"]:
        dest = int(seg["destination"], 16)
        source = int(seg["spi_source"], 16)
        size = int(seg["size"], 16)
        uc.mem_write(dest, image[source : source + size])


    map_region(0xD0030000, 0x1000)
    uc.mem_write(0xD0030000, struct.pack("<I", 0x92301B4B))


    uc.mem_write(0xD0030008, struct.pack("<I", 0x00000011))
    map_region(0xD0071000, 0x1000)
    uc.mem_write(0xD0071054, struct.pack("<I", 0x0000002F))
    uc.mem_write(0xD0072014, b"\x60")
    map_region(0x80002000, 0x1000)
    uc.mem_write(0x80002800, struct.pack("<I", 7))
    map_region(0x8000A000, 0x1000)
    uc.mem_write(0x8000A800, struct.pack("<I", 3))
    uc.mem_write(0x8000A80C, struct.pack("<I", 0xF))
    for port in range(4):
        uc.mem_write(0x8000A924 + port * 0x80, struct.pack("<I", 0xFFFFFFFF))
    if port0_sstatus:
        uc.mem_write(0x8000A928, struct.pack("<I", port0_sstatus))
        uc.mem_write(0x8000A924, struct.pack("<I", 0x00000101))
    for address, value in (initial_mmio or {}).items():
        if address & 3 or not 0x80000000 <= address < 0xF0000000:
            raise ImageError(f"invalid initial MMIO word: 0x{address:08X}")
        map_region(address, 4)
        uc.mem_write(address, struct.pack("<I", value))
    for address, contents in (initial_ram or {}).items():
        if not contents or not (0x30000000 <= address < 0x30080000) or address + len(contents) > 0x30080000:
            raise ImageError(f"invalid initial SRAM range: 0x{address:08X}")
        uc.mem_write(address, contents)
    if synthetic_host_rfis_buffer is not None:
        uc.mem_write(0x50000000 | (rfis_address & 0xFFFF), rfis_initial)

    unknown = Counter()
    uart = bytearray()
    uart_rx = deque(uart_input)
    stop_reason = "instruction limit"
    last_pc = 0
    last_pc_outside_delay = 0
    instructions = 0
    dlab = False
    timer_ticks = 0
    spi_command = 0
    spi_trace: list[dict] = []
    revision_writes: list[dict] = []
    port0_command_issues: list[dict] = []
    srst_pending = False
    synthetic_irq_injected = False
    synthetic_irq_pending = False
    synthetic_host_events_delivered = 0
    synthetic_late_host_delivered = False
    synthetic_open_port_reset_phase = 0
    synthetic_open_followup_delivered = False
    synthetic_open_console_delivered = False
    synthetic_open_console_followups_delivered = 0
    console_ci_writeback: tuple[int, int] | None = None
    synthetic_host_port_event_delivered = False
    synthetic_stock_host_followups_delivered = 0
    synthetic_stock_host_followup_snapshots: list[dict[str, str]] = []
    synthetic_frontend_worker_called = False
    synthetic_frontend_consumer_called = False
    synthetic_backend_task_drain_called = False
    synthetic_host_auto_fetches: list[dict] = []
    synthetic_host_fis_fetches: list[dict] = []
    synthetic_open_autofetch_delivered = False
    synthetic_host_data_transfers: list[dict] = []
    pcie_window_accesses: list[dict] = []
    frontend_fis_snapshots: list[dict] = []
    backend_fis_accesses: list[dict] = []
    debug_irq_injected = False
    synthetic_completions: list[dict] = []
    irq_vector_visits = 0
    irq_code_trace: list[str] = []
    code_visits = Counter()
    code_visit_samples: dict[str, list[dict[str, str]]] = {}
    trace_after: list[str] = []
    fault_context: dict[str, str] = {}
    watched_ram_writes: list[dict[str, str]] = []
    identify_parse_trace: list[dict] = []
    raid_scan_entries = 0
    mmio_trace: list[dict] = []
    mmio_dropped = 0

    def record_mmio(operation: str, address: int, size: int, value: int) -> None:
        nonlocal mmio_dropped
        if not capture_mmio or not 0x80000000 <= address < 0xF0000000:
            return
        if address in (0xD0020314, 0xD0072014, 0xD0072000, 0xD0060008):
            return
        event = {
            "pc": f"0x{last_pc:08X}",
            "op": operation,
            "addr": f"0x{address:08X}",
            "size": size,
            "value": f"0x{value:0{size * 2}X}",
        }
        if mmio_trace and all(mmio_trace[-1].get(k) == v for k, v in event.items()):
            mmio_trace[-1]["repeat"] = mmio_trace[-1].get("repeat", 1) + 1
        elif len(mmio_trace) < 50000:
            mmio_trace.append(event)
        else:
            mmio_dropped += 1

    def on_unmapped(emu: Uc, access: int, address: int, size: int, value: int, user: object) -> bool:
        nonlocal stop_reason
        if access == UC_MEM_FETCH_UNMAPPED:
            stop_reason = f"unmapped instruction fetch at 0x{address:08X}"
            return False
        if not (0x40000000 <= address < 0x40040000 or
                0x50000000 <= address < 0x50010000 or
                0x80000000 <= address < 0xF0000000):
            stop_reason = f"unexpected data access at 0x{address:08X}"
            fault_context.update({
                "pc": f"0x{last_pc:08X}",
                "address": f"0x{address:08X}",
                "access": "write" if access == UC_MEM_WRITE_UNMAPPED else "read",
                "r0": f"0x{emu.reg_read(UC_ARM_REG_R0):08X}",
                "r1": f"0x{emu.reg_read(UC_ARM_REG_R1):08X}",
                "r2": f"0x{emu.reg_read(UC_ARM_REG_R2):08X}",
                "r4": f"0x{emu.reg_read(UC_ARM_REG_R4):08X}",
                "r6": f"0x{emu.reg_read(UC_ARM_REG_R6):08X}",
            })
            return False
        page = address & ~0xFFF
        unknown[("write" if access == UC_MEM_WRITE_UNMAPPED else "read", page)] += 1
        if len(unknown) > 128:
            stop_reason = "too many unknown MMIO pages"
            return False
        map_region(page, 0x1000)
        return True

    def on_read(emu: Uc, access: int, address: int, size: int, value: int, user: object) -> None:
        nonlocal timer_ticks, srst_pending
        if 0x50000000 <= address < 0x50010000 and len(pcie_window_accesses) < 64:
            pcie_window_accesses.append({"op": "read", "pc": f"0x{last_pc:08X}",
                                         "addr": f"0x{address:08X}", "size": size})
        if (synthetic_backend_received_fis is not None
                and 0x30067000 <= address < 0x30067100
                and len(backend_fis_accesses) < 64):
            backend_fis_accesses.append({"op": "read", "pc": f"0x{last_pc:08X}",
                                         "addr": f"0x{address:08X}", "size": size,
                                         "lr": f"0x{emu.reg_read(UC_ARM_REG_LR):08X}"})
        if address == 0xD0072014:
            emu.mem_write(address, b"\x61" if uart_rx else b"\x60")
        elif address == 0xD0072000 and not dlab and uart_rx:
            emu.mem_write(address, bytes((uart_rx.popleft(),)))
        elif address == 0xD0020110:


            emu.mem_write(address, struct.pack("<I", 0))
        elif address == 0xD0020314:


            timer_ticks += 1
            emu.mem_write(address, struct.pack("<I", (0xFFFFFFFF - timer_ticks * 0x100) & 0xFFFFFFFF))
        elif address in (0x80003070, 0x80003074):


            word = struct.unpack("<I", emu.mem_read(address, 4))[0]
            emu.mem_write(address, struct.pack("<I", word & ~0x800000))
        elif port0_sstatus and address == 0x8000A938 and srst_pending:


            word = struct.unpack("<I", emu.mem_read(address, 4))[0]
            emu.mem_write(address, struct.pack("<I", word & ~1))
            srst_pending = False
        elif address == 0xD0060000:

            word = struct.unpack("<I", emu.mem_read(address, 4))[0]
            emu.mem_write(address, struct.pack("<I", word & ~0x10))
        elif address == 0xD0060008:
            if len(spi_trace) < 8:
                spi_trace.append({
                    "command": f"0x{spi_command:08X}",
                    "address_reg": f"0x{struct.unpack('<I', emu.mem_read(0xD0060004, 4))[0]:08X}",
                    "pc": f"0x{last_pc:08X}",
                })


            if spi_command == 0x12:
                value = 0
            elif spi_command == 0x14:
                flash_addr = struct.unpack("<I", emu.mem_read(0xD0060004, 4))[0]
                value = struct.unpack_from("<I", image, flash_addr)[0] if flash_addr + 4 <= len(image) else 0xFFFFFFFF
            else:
                value = 0x001330EF
            emu.mem_write(address, struct.pack("<I", value))
        if capture_mmio and 0x80000000 <= address < 0xF0000000:
            observed = int.from_bytes(emu.mem_read(address, size), "little")
            record_mmio("read", address, size, observed)

    def fetch_synthetic_host_list(emu: Uc) -> None:
        if synthetic_host_command_list is None:
            return
        host_address, command_list = synthetic_host_command_list
        if host_address & 0x1F or not 0 <= host_address < 1 << 64 or len(command_list) > 0x400:
            raise ImageError("invalid synthetic host command-list address or length")
        port_base = 0x80002900 + 0x80 * synthetic_host_port_index
        local_base = 0x30000000 + 0x400 * synthetic_host_port_index
        clb_low, clb_high = struct.unpack("<II", emu.mem_read(port_base, 8))
        if ((clb_high << 32) | clb_low) != host_address:
            raise ImageError("synthetic host CLB does not match command list")
        fetched_list = command_list.ljust(0x400, b"\x00")
        emu.mem_write(local_base, fetched_list)
        if synthetic_host_cpu_window:
            window_list = 0x50000000 | (host_address & 0xFFFF)
            map_region(window_list, len(fetched_list))
            emu.mem_write(window_list, fetched_list)
            if synthetic_host_cpu_header_at_aligned_base:
                aligned_window = 0x50000000 | (host_address & 0xFC00)
                map_region(aligned_window, len(fetched_list))
                emu.mem_write(aligned_window, fetched_list)
            if (synthetic_host_cpu_header_corrupt or
                    synthetic_host_cpu_header_at_aligned_base):
                first = struct.unpack_from("<I", fetched_list)[0]
                emu.mem_write(window_list, struct.pack("<I", first ^ 0x400))
        synthetic_host_auto_fetches.append({
            "bus_address": f"0x{host_address:016X}",
            "sram_address": f"0x{local_base:08X}", "size": 0x400,
        })
        if synthetic_host_command_table is not None:
            table_address, table = synthetic_host_command_table[0], host_table
            table_low, table_high = struct.unpack_from("<II", fetched_list, 8)
            header_table_address = (table_high << 32) | (table_low & ~0x3F)
            if table_address != header_table_address or len(table) < 16 or len(table) > 0x10000:
                raise ImageError("synthetic host command table does not match slot-0 header")
            emu.mem_write(local_base + 0x10, bytes(table[:16]))
            if synthetic_host_cpu_window:
                window_table = 0x50000000 | (table_address & 0xFFFF)
                map_region(window_table, len(table))
                emu.mem_write(window_table, bytes(table))
                if host_data is not None and len(host_data) <= 4096:
                    window_data = 0x50000000 | (host_data_address & 0xFFFF)
                    map_region(window_data, len(host_data))
                    emu.mem_write(window_data, bytes(host_data))
            synthetic_host_fis_fetches.append({
                "bus_address": f"0x{table_address:016X}",
                "sram_address": f"0x{local_base + 0x10:08X}", "size": 16,
            })

    def synthetic_prdt_bytes(slot_header: bytes) -> int:
        """Validate PRDs against the modeled host bus buffer layout."""
        if host_table is None or host_data is None:
            return 0
        count = struct.unpack_from("<I", slot_header)[0] >> 16
        if not count or len(host_table) < 0x80 + 16 * count:
            return 0
        if synthetic_host_prdt_layout is not None and count != len(synthetic_host_prdt_layout):
            return 0
        total = 0
        for index in range(count):
            low, high, _, dbc = struct.unpack_from("<4I", host_table,
                                                   0x80 + 16 * index)
            address = (high << 32) | low
            length = (dbc & 0x3FFFFF) + 1
            expected_address = (synthetic_host_prdt_layout[index][0]
                                if synthetic_host_prdt_layout is not None
                                else host_data_address + total)
            expected_length = (synthetic_host_prdt_layout[index][1]
                               if synthetic_host_prdt_layout is not None else length)
            if (address != expected_address or length != expected_length or
                    total + length > len(host_data)):
                return 0
            total += length
        return total if total == len(host_data) else 0

    def on_write(emu: Uc, access: int, address: int, size: int, value: int, user: object) -> None:
        nonlocal dlab, spi_command, srst_pending, synthetic_open_autofetch_delivered, synthetic_open_followup_delivered, synthetic_open_console_delivered
        nonlocal console_ci_writeback

        if allow_modified_image and address == 0x80002CB8 and size == 4:


            previous = struct.unpack('<I', emu.mem_read(address, 4))[0]
            console_ci_writeback = (value & 0xFFFFFFFF, previous & value)

        if address in watch_ram_writes and len(watched_ram_writes) < 64:
            watched_ram_writes.append({"pc": f"0x{last_pc:08X}",
                                       "address": f"0x{address:08X}",
                                       "size": str(size),
                                       "value": f"0x{value:0{size * 2}X}"})
        if 0x50000000 <= address < 0x50010000 and len(pcie_window_accesses) < 64:
            pcie_window_accesses.append({"op": "write", "pc": f"0x{last_pc:08X}",
                                         "addr": f"0x{address:08X}", "size": size,
                                         "value": f"0x{value:0{size * 2}X}"})
        if (synthetic_backend_received_fis is not None
                and (0x30067000 <= address < 0x30067100
                     or address == 0x0400062C
                     or 0x04000640 <= address < 0x04000650)
                and len(backend_fis_accesses) < 64):
            backend_fis_accesses.append({"op": "write", "pc": f"0x{last_pc:08X}",
                                         "addr": f"0x{address:08X}", "size": size,
                                         "value": f"0x{value:0{size * 2}X}"})
        record_mmio("write", address, size, value)
        if address == 0xD007200C:
            dlab = bool(value & 0x80)
        elif address == 0xD0072000 and not dlab:
            uart.append(value & 0xFF)
        elif address == 0xD0060000:
            spi_command = value
        elif (address == 0x80002808 and value == 1 and allow_modified_image
              and synthetic_open_followup_fetched and not synthetic_open_followup_delivered):
            if len(synthetic_open_followup_fetched) != 32:
                raise ImageError("synthetic open follow-up must be 32 fetched bytes")
            if synthetic_open_followup_table:
                if host_table is None or len(synthetic_open_followup_table) != len(host_table):
                    raise ImageError("synthetic open follow-up table size differs")
                if synthetic_open_followup_table[:16] != synthetic_open_followup_fetched[16:32]:
                    raise ImageError("synthetic open follow-up table FIS differs")
                host_table[:] = synthetic_open_followup_table
                if synthetic_host_cpu_window:
                    table_address = synthetic_host_command_table[0]
                    emu.mem_write(0x50000000 | (table_address & 0xFFFF), bytes(host_table))
            synthetic_open_followup_delivered = True
            if synthetic_clear_prdt_on_followup:
                if host_data is None:
                    raise ImageError("synthetic follow-up has no PRDT buffer to clear")
                host_data[:] = b"\xCC" * len(host_data)
                if synthetic_host_cpu_window and len(host_data) <= 4096:
                    window_data = 0x50000000 | (host_data_address & 0xFFFF)
                    emu.mem_write(window_data, bytes(host_data))
            emu.mem_write(0x30000000, synthetic_open_followup_fetched)
            emu.mem_write(0x8000C060, struct.pack("<I", 1))
            emu.mem_write(0x80002938, struct.pack("<I", 1))
        elif (address == 0x80002808 and value == 1 and allow_modified_image
              and synthetic_open_followup_delivered
              and synthetic_open_console_fetched and not synthetic_open_console_delivered):
            if len(synthetic_open_console_fetched) != 0x100:
                raise ImageError("synthetic console fetch must contain 256 bytes")
            autofetch = struct.unpack("<I", emu.mem_read(0x8000C044, 4))[0]
            if not (autofetch & (1 << 11)):
                raise ImageError("console auto-fetch was not enabled")
            synthetic_open_console_delivered = True
            emu.mem_write(0x30001C00, synthetic_open_console_fetched)
            emu.mem_write(0x8000C07C, struct.pack("<I", 1))
            emu.mem_write(0x80002CB8, struct.pack("<I", 1))
            emu.mem_write(0x80002C98, struct.pack("<I", 7))
            if synthetic_open_console_command_table is not None:
                table_address, table = synthetic_open_console_command_table
                fetched_table_low, fetched_table_high = struct.unpack_from(
                    "<II", synthetic_open_console_fetched, 8)
                if ((fetched_table_high << 32) | fetched_table_low) != table_address:
                    raise ImageError("synthetic console CTBA mismatch")
                window_table = 0x50000000 | (table_address & 0xFFFF)
                map_region(window_table, len(table))
                emu.mem_write(window_table, table)
                if synthetic_open_console_prdt_buffer is not None:
                    data_address, data = synthetic_open_console_prdt_buffer
                    window_data = 0x50000000 | (data_address & 0xFFFF)
                    map_region(window_data, len(data))
                    emu.mem_write(window_data, data)
        elif address == 0x8000C084 and len(frontend_fis_snapshots) < 8:
            context = emu.reg_read(UC_ARM_REG_R4)
            port = emu.reg_read(UC_ARM_REG_R9)
            frontend_fis_snapshots.append({
                "pc": f"0x{last_pc:08X}",
                "host_fis_sram": bytes(emu.mem_read(0x30003000, 0x60)).hex(),
                "r4": f"0x{context:08X}",
                "r9": f"0x{port:08X}",
                "context_fis": bytes(emu.mem_read(context + 0x20, 0x20)).hex()
                if 0x04000000 <= context < 0x04100000 else None,
                "port_fis_base": f"0x{struct.unpack('<I', emu.mem_read(port + 0x48, 4))[0]:08X}"
                if 0x04000000 <= port < 0x04100000 else None,
            })
        elif address == 0x04000028 and len(revision_writes) < 8:
            revision_writes.append({"pc": f"0x{last_pc:08X}", "value": f"0x{value:0{size * 2}X}"})
        elif (address == 0x8000C044 and synthetic_open_autofetch_at_enable
              and synthetic_host_command_list is not None
              and not synthetic_open_autofetch_delivered and value & 0x10
              and struct.unpack("<I", emu.mem_read(0x8000C060, 4))[0] & 1):
            fetch_synthetic_host_list(emu)
            if synthetic_host_rfis_buffer is not None:
                emu.mem_write(0x80002908, struct.pack("<II", rfis_address & 0xFFFFFFFF,
                                                      rfis_address >> 32))
                command = struct.unpack("<I", emu.mem_read(0x80002918, 4))[0]
                emu.mem_write(0x80002918, struct.pack("<I", command | 0x10))
            synthetic_open_autofetch_delivered = True
        elif port0_sstatus and address == 0x8000A938 and value:
            if last_pc == 0x6538 and value & 1:
                srst_pending = True
            event = {"pc": f"0x{last_pc:08X}", "value": f"0x{value:08X}"}
            if last_pc == 0x4BAC or allow_modified_image:
                slot = (value & -value).bit_length() - 1
                command_header = 0x3006B000 + slot * 0x40
                request_word = struct.unpack("<I", emu.mem_read(command_header + 8, 4))[0]
                request_addr = 0x30000000 | (request_word & ~0xF)
                buffer_word = struct.unpack("<I", emu.mem_read(request_addr + 0x80, 4))[0]
                event["slot"] = slot
                event["ata_command"] = f"0x{emu.mem_read(command_header + 0x22, 1)[0]:02X}"
                event["request_addr"] = f"0x{request_addr:08X}"


                event["data_buffer"] = f"0x{0x30000000 | (buffer_word & ~0x7):08X}"
                event["data_pointer_flags"] = f"0x{buffer_word & 0xF:X}"
                event["data_target_before"] = bytes(emu.mem_read(0x30000000 | (buffer_word & ~0x7), 32)).hex()
                event["command_slot_raw"] = bytes(emu.mem_read(command_header, 0x40)).hex()
                event["request_raw"] = bytes(emu.mem_read(request_addr, 0xA0)).hex()
                event["command_ram_3006B000"] = bytes(emu.mem_read(0x3006B000, 64)).hex()
                event["command_ram_30067000"] = bytes(emu.mem_read(0x30067000, 64)).hex()
                ram = bytes(emu.mem_read(0x30060000, 0x20000))
                event["fis_candidates"] = [
                    {"addr": f"0x{0x30060000 + i:08X}", "bytes": ram[i:i + 20].hex()}
                    for i in range(len(ram) - 20)
                    if ram[i:i + 2] == b"\x27\x80"
                ][:20]
                event["cpsr"] = f"0x{emu.reg_read(UC_ARM_REG_CPSR):08X}"
                event["irq_mask_ram"] = f"0x{struct.unpack('<I', emu.mem_read(0x040002AC, 4))[0]:08X}"
                event["irq_table_bit4"] = f"0x{struct.unpack('<I', emu.mem_read(0x040002C0, 4))[0]:08X}"
                event["irq_enable"] = f"0x{struct.unpack('<I', emu.mem_read(0xD0020204, 4))[0]:08X}"
                event["port0_is"] = f"0x{struct.unpack('<I', emu.mem_read(0x8000A910, 4))[0]:08X}"
                event["port0_ie"] = f"0x{struct.unpack('<I', emu.mem_read(0x8000A914, 4))[0]:08X}"
                event["controller_registers"] = {
                    f"0x{addr:08X}": f"0x{struct.unpack('<I', emu.mem_read(addr, 4))[0]:08X}"
                    for addr in (
                        0xD0020110, 0xD0020114, 0xD0020300, 0xD0020318,
                        0x8000A804, 0x8000A900, 0x8000A908, 0x8000A918,
                        0x8000A970,
                    )
                }
                mask = struct.unpack("<I", emu.mem_read(0x040002AC, 4))[0]
                handlers = []
                for bit in range(32):
                    if not mask & (1 << bit):
                        continue
                    pointer = struct.unpack("<I", emu.mem_read(0x040002B0 + 4 * bit, 4))[0]
                    if 0x04000000 <= pointer < 0x04100000:
                        pair = bytes(emu.mem_read(pointer, 8))
                        handlers.append({"bit": bit, "struct": f"0x{pointer:08X}", "mask": f"0x{struct.unpack_from('<I', pair)[0]:08X}", "callback": f"0x{struct.unpack_from('<I', pair, 4)[0]:08X}"})
                event["irq_handlers"] = handlers
                event["backend_irq_state"] = {
                    f"0x{base:08X}": bytes(emu.mem_read(base, 0x40)).hex()
                    for base in (0x30060020, 0x30060108, 0x3006021C)
                }
                event["backend_irq_registers"] = {
                    f"0x{addr:08X}": f"0x{struct.unpack('<I', emu.mem_read(addr, 4))[0]:08X}"
                    for addr in (0x80003050, 0x80003058, 0x80003060, 0x8000A910)
                }
                event["sata_irq_state"] = bytes(emu.mem_read(0x04003F10, 0x40)).hex()
            port0_command_issues.append(event)

    def deliver_irq(emu: Uc, return_pc: int, pending: int) -> None:
        map_region(0xD0020000, 0x1000)
        emu.mem_write(0xD0020200, struct.pack("<I", pending))
        saved_cpsr = emu.reg_read(UC_ARM_REG_CPSR)
        emu.reg_write(UC_ARM_REG_CPSR, (saved_cpsr & ~0x1FF) | 0x92)
        emu.reg_write(UC_ARM_REG_SPSR, saved_cpsr)
        emu.reg_write(UC_ARM_REG_LR, return_pc + 4)
        emu.reg_write(UC_ARM_REG_PC, 0x18)

    def on_code(emu: Uc, address: int, size: int, user: object) -> None:
        nonlocal console_ci_writeback
        if console_ci_writeback is not None:
            written, cleared = console_ci_writeback
            current = struct.unpack('<I', emu.mem_read(0x80002CB8, 4))[0]
            if current == written:
                emu.mem_write(0x80002CB8, struct.pack('<I', cleared))
            console_ci_writeback = None
        nonlocal last_pc, last_pc_outside_delay, instructions, synthetic_irq_injected, synthetic_irq_pending, synthetic_host_events_delivered, synthetic_late_host_delivered, synthetic_open_port_reset_phase, synthetic_host_port_event_delivered, synthetic_frontend_worker_called, synthetic_frontend_consumer_called, synthetic_backend_task_drain_called, synthetic_open_console_followups_delivered, synthetic_stock_host_followups_delivered, debug_irq_injected, irq_vector_visits, raid_scan_entries, stop_reason
        last_pc = address
        if trace_after_pc is not None and (trace_after or address == trace_after_pc) and len(trace_after) < trace_after_limit:
            trace_after.append(f"0x{address:08X}")
        if address in code_visit_addresses:
            code_visits[address] += 1
            key = f"0x{address:08X}"
            if len(code_visit_samples.setdefault(key, [])) < 8:
                code_visit_samples[key].append({
                    "step": str(instructions),
                    "r0": f"0x{emu.reg_read(UC_ARM_REG_R0):08X}",
                    "r1": f"0x{emu.reg_read(UC_ARM_REG_R1):08X}",
                    "r2": f"0x{emu.reg_read(UC_ARM_REG_R2):08X}",
                    "r4": f"0x{emu.reg_read(UC_ARM_REG_R4):08X}",
                    "r4_flags": f"0x{struct.unpack('<I', emu.mem_read(emu.reg_read(UC_ARM_REG_R4) + 0xC, 4))[0]:08X}"
                    if 0x04000000 <= emu.reg_read(UC_ARM_REG_R4) < 0x04100000 else None,
                    "r9": f"0x{emu.reg_read(UC_ARM_REG_R9):08X}",
                    "r11": f"0x{emu.reg_read(UC_ARM_REG_R11):08X}",
                    "sp": f"0x{emu.reg_read(UC_ARM_REG_SP):08X}",
                    "fis_sram_30": bytes(emu.mem_read(0x30003030, 32)).hex(),
                    "command_ctx_20": bytes(emu.mem_read(0x04000640, 16)).hex(),
                    "after_host_worker": synthetic_frontend_worker_called,
                    "after_backend_drain": synthetic_backend_task_drain_called,
                })
        if code_limit is not None and address >= code_limit:
            stop_reason = f"entered code outside open stage at 0x{address:08X}"
            emu.emu_stop()
            return
        if address == 0x30048724:
            raid_scan_entries += 1
        if address in (0x18, 0x143B0):
            irq_vector_visits += 1
        if synthetic_irq_injected and len(irq_code_trace) < 100:
            irq_code_trace.append(f"0x{address:08X}")
        if address in (0x4538, 0x4554, 0x4560) and len(identify_parse_trace) < 12:
            r0 = emu.reg_read(UC_ARM_REG_R0)
            identify_parse_trace.append({
                "pc": f"0x{address:08X}",
                "r0": f"0x{r0:08X}",
                "r4": f"0x{emu.reg_read(UC_ARM_REG_R4):08X}",
                "r6": f"0x{emu.reg_read(UC_ARM_REG_R6):08X}",
                "word_r0_plus_80": f"0x{struct.unpack('<I', emu.mem_read(r0 + 0x80, 4))[0]:08X}" if 0x30000000 <= r0 < 0x3007FF80 else None,
            })
        if not 0x17E4 <= address <= 0x182C:
            last_pc_outside_delay = address
        instructions += 1
        if (address == synthetic_sata_idle_pc and synthetic_open_console_delivered
                and synthetic_open_console_followups_delivered < len(synthetic_open_console_followups)
                and not (struct.unpack("<I", emu.mem_read(0x80002CB8, 4))[0] & 1)):
            fetched, (table_address, table), (data_address, data) = (
                synthetic_open_console_followups[synthetic_open_console_followups_delivered])
            if (len(fetched) != 0x100 or len(table) < 0x90 or not data):
                raise ImageError("invalid synthetic console follow-up")
            fetched_table_low, fetched_table_high = struct.unpack_from("<II", fetched, 8)
            if ((fetched_table_high << 32) | fetched_table_low) != table_address:
                raise ImageError("synthetic console follow-up CTBA mismatch")
            synthetic_open_console_followups_delivered += 1
            table_window = 0x50000000 | (table_address & 0xFFFF)
            data_window = 0x50000000 | (data_address & 0xFFFF)
            map_region(table_window, len(table))
            map_region(data_window, len(data))
            emu.mem_write(table_window, table)
            emu.mem_write(data_window, data)
            emu.mem_write(0x30001C00, fetched)
            emu.mem_write(0x80002C90, struct.pack("<I", 0))
            emu.mem_write(0x8000C07C, struct.pack("<I", 1))
            emu.mem_write(0x80002CB8, struct.pack("<I", 1))
        if (synthetic_open_host_issue_after_marker and not synthetic_late_host_delivered
                and address == synthetic_sata_idle_pc
                and b"HOST_SERVICE_CONTINUES" in uart
                and synthetic_host_command_list is not None):
            synthetic_late_host_delivered = True
            host_address, _ = synthetic_host_command_list
            emu.mem_write(0x80002804, struct.pack("<I", 0x80000002))
            emu.mem_write(0x80002900, struct.pack("<I", host_address & 0xFFFFFFFF))
            emu.mem_write(0x80002904, struct.pack("<I", host_address >> 32))
            emu.mem_write(0x80002918, struct.pack("<I", 1))
            emu.mem_write(0x80002938, struct.pack("<I", 1))
            emu.mem_write(0x8000C060, struct.pack("<I", 1))
            fetch_synthetic_host_list(emu)
        if (synthetic_open_port_reset_after_marker
                and address == synthetic_sata_idle_pc
                and b"HOST_SERVICE_CONTINUES" in uart
                and synthetic_open_port_reset_phase < 2):
            if synthetic_open_port_reset_phase == 0:
                emu.mem_write(0x8000292C, struct.pack("<I", 1))
                emu.mem_write(0x80002924, struct.pack("<I", 0xFFFFFFFF))
                emu.mem_write(0x80002928, struct.pack("<I", 0))
                emu.mem_write(0x80002920, struct.pack("<I", 0x7F))
            else:
                emu.mem_write(0x8000292C, struct.pack("<I", 0))
            synthetic_open_port_reset_phase += 1
        if (address == 0xE8 and synthetic_stock_host_followups_delivered < len(synthetic_stock_host_followups)
                and synthetic_backend_task_drain_called
                and not (struct.unpack("<I", emu.mem_read(0x80002CB8, 4))[0] & 1)):
            if (synthetic_host_command_list is None or
                    synthetic_host_command_table is None or
                    synthetic_host_prdt_buffer is None):
                raise ImageError("stock host follow-ups require the initial host command fixture")
            header, table, data = synthetic_stock_host_followups[synthetic_stock_host_followups_delivered]
            if len(header) != 32 or len(table) < 0x90 or not data:
                raise ImageError("invalid stock host follow-up")
            synthetic_stock_host_followup_snapshots.append({
                "reply": bytes(emu.mem_read(0x30065468, 0x250)).hex(),
                "ui_state": bytes(emu.mem_read(0x3007F648, 0x40)).hex(),
                "host_data": bytes(emu.mem_read(
                    0x50000000 | (synthetic_host_prdt_buffer[0] & 0xFFFF),
                    0x250)).hex(),
                "uart_length": str(len(uart)),
            })
            synthetic_stock_host_followups_delivered += 1
            table_address = synthetic_host_command_table[0]
            data_address = synthetic_host_prdt_buffer[0]
            emu.mem_write(0x30001C00, header)
            emu.mem_write(0x30001C10, table[:16])
            emu.mem_write(0x50000000 | (table_address & 0xFFFF), table)
            emu.mem_write(0x50000000 | (data_address & 0xFFFF), data)
            emu.mem_write(0x80002C90, struct.pack("<I", 0))
            emu.mem_write(0x8000C07C, struct.pack("<I", 1))
            emu.mem_write(0x80002CB8, struct.pack("<I", 1))
            synthetic_frontend_worker_called = False
            synthetic_frontend_consumer_called = False
            synthetic_backend_task_drain_called = False
            deliver_irq(emu, address, 1 << (9 + synthetic_host_port_index))
        if inject_irq_at_pc == address and not debug_irq_injected:
            debug_irq_injected = True
            if host_ghc_on_debug_irq is not None:
                emu.mem_write(0x80002804, struct.pack("<I", host_ghc_on_debug_irq))
            for mmio_address, mmio_value in (debug_mmio_writes or {}).items():
                if mmio_address & 3 or not 0x80000000 <= mmio_address < 0xF0000000:
                    raise ImageError(f"invalid debug MMIO word: 0x{mmio_address:08X}")
                map_region(mmio_address, 4)
                emu.mem_write(mmio_address, struct.pack("<I", mmio_value & 0xFFFFFFFF))
            for ram_address, ram_value in (debug_ram_writes or {}).items():
                if ram_address & 3 or not (0x04000000 <= ram_address < 0x04100000 or
                                             0x30000000 <= ram_address < 0x30080000):
                    raise ImageError(f"invalid debug RAM word: 0x{ram_address:08X}")
                emu.mem_write(ram_address, struct.pack("<I", ram_value & 0xFFFFFFFF))
            deliver_irq(emu, address, injected_irq_pending)
        if (address == 0xE8 and synthetic_host_events_delivered < len(synthetic_host_ghc_sequence)
                and b"console device: 12 mapping to vportid: 7" in uart):
            ghc = synthetic_host_ghc_sequence[synthetic_host_events_delivered]
            synthetic_host_events_delivered += 1
            emu.mem_write(0x80002804, struct.pack("<I", ghc))
            emu.mem_write(0x80002808, struct.pack("<I", 2))
            deliver_irq(emu, address, 0x100)
        elif (address == 0xE8 and synthetic_host_port_command_issue is not None
              and not synthetic_host_port_event_delivered
              and b"AHCI mode enabled by host." in uart):
            synthetic_host_port_event_delivered = True
            port_base = 0x80002900 + 0x80 * synthetic_host_port_index
            local_shadow = 0x8000C060 + 4 * synthetic_host_port_index
            emu.mem_write(local_shadow, struct.pack("<I", synthetic_host_port_command_issue))
            port_event = 0x40
            if synthetic_host_command_list is not None:
                host_address, command_list = synthetic_host_command_list
                if host_address & 0x3FF or not 0 <= host_address < 1 << 64 or len(command_list) > 0x400:
                    raise ImageError("invalid synthetic host command-list address or length")
                emu.mem_write(port_base, struct.pack("<I", host_address & 0xFFFFFFFF))
                emu.mem_write(port_base + 4, struct.pack("<I", host_address >> 32))
                port_event |= 1
                auto_fetch_control = struct.unpack("<I", emu.mem_read(0x8000C044, 4))[0]
                port_state = 0x04005218 + 0x58 + 0x4C * synthetic_host_port_index
                device_state = struct.unpack("<I", emu.mem_read(port_state + 0x10, 4))[0]
                port_flags = struct.unpack("<H", emu.mem_read(device_state + 0x70, 2))[0]
                if auto_fetch_control & (1 << (4 + synthetic_host_port_index)) and port_flags & 0x20:
                    fetch_synthetic_host_list(emu)
            port_cmd = struct.unpack("<I", emu.mem_read(port_base + 0x18, 4))[0]
            emu.mem_write(port_base + 0x18, struct.pack("<I", port_cmd | 1))
            emu.mem_write(0x80003010 + 8 * synthetic_host_port_index, struct.pack("<I", port_event))
            deliver_irq(emu, address, 1 << (9 + synthetic_host_port_index))
        elif (address == 0xE8 and synthetic_frontend_worker_once
              and synthetic_host_port_event_delivered
              and not synthetic_frontend_worker_called):
            synthetic_frontend_worker_called = True
            if synthetic_frontend_stack_top is not None:
                if synthetic_frontend_stack_top & 7:
                    raise ImageError("synthetic frontend stack top must be 8-byte aligned")
                emu.reg_write(UC_ARM_REG_SP, synthetic_frontend_stack_top)
            if len(synthetic_host_autofetch_header) > 0x400:
                raise ImageError("synthetic host command list exceeds 0x400 bytes")
            if synthetic_host_autofetch_header:
                emu.mem_write(0x30000000 + 0x400 * synthetic_host_port_index,
                              synthetic_host_autofetch_header)
            emu.reg_write(UC_ARM_REG_R0, 0x04005218)
            emu.reg_write(UC_ARM_REG_LR, address)
            emu.reg_write(UC_ARM_REG_PC, 0x7A60)
        elif (address == 0xE8 and synthetic_frontend_consumer_once
              and synthetic_frontend_worker_called
              and not synthetic_frontend_consumer_called):
            synthetic_frontend_consumer_called = True
            emu.reg_write(UC_ARM_REG_LR, address)
            emu.reg_write(UC_ARM_REG_PC, 0x854C)
        elif (address == 0xE8 and synthetic_backend_task_drain_once
              and synthetic_frontend_worker_called
              and not synthetic_backend_task_drain_called):
            synthetic_backend_task_drain_called = True
            emu.reg_write(UC_ARM_REG_R0, 0x04003690)
            emu.reg_write(UC_ARM_REG_LR, address)
            emu.reg_write(UC_ARM_REG_PC, 0x8DF8)
        if (
            experimental_sata_io
            and address == synthetic_sata_idle_pc
            and len(synthetic_completions) < 16
        ):
            pending = [event for event in port0_command_issues if "ata_command" in event]
            if len(pending) > len(synthetic_completions):
                event = pending[len(synthetic_completions)]
                command = int(event["ata_command"], 16)
                buffer = int(event["data_buffer"], 16)


                is_error = (len(synthetic_completions)
                            == synthetic_sata_error_on_completion_index)
                if command in (0x06, 0xB0, 0xC8, 0xCA, 0xE7,
                               0xEC, 0x25, 0x35, 0xEA, 0xEF, 0xF5):


                    if command == 0xEC:
                        slot_header = bytes.fromhex(event["command_slot_raw"])
                        table_low, table_high = struct.unpack_from("<II", slot_header, 8)
                        issued_table_address = (table_high << 32) | (table_low & ~0x3F)
                        is_host_command = (synthetic_host_command_table is not None
                                           and issued_table_address == synthetic_host_command_table[0])
                        if is_host_command:


                            table = host_table
                            prdt_length = struct.unpack_from("<I", slot_header)[0] >> 16
                            if (not is_error and host_data is not None and
                                    prdt_length == 1 and len(table) >= 0x90):
                                count = synthetic_prdt_bytes(slot_header)
                                if count == 512:
                                    host_data[:] = synthetic_ssd_identify(
                                        synthetic_logical_sector_bytes)
                                    synthetic_host_data_transfers.append({
                                        "bus_address": f"0x{host_data_address:016X}",
                                        "bytes": count,
                                        "source": "synthetic IDENTIFY sector",
                                    })
                        elif not is_error:
                            emu.mem_write(buffer, synthetic_ssd_identify(
                                synthetic_logical_sector_bytes))
                    elif command in (0x25, 0xC8):
                        slot_header = bytes.fromhex(event["command_slot_raw"])
                        table_low, table_high = struct.unpack_from("<II", slot_header, 8)
                        issued_table_address = (table_high << 32) | (table_low & ~0x3F)
                        is_host_command = (synthetic_host_command_table is not None
                                           and issued_table_address == synthetic_host_command_table[0])
                        if is_host_command:
                            count = synthetic_prdt_bytes(slot_header)
                            if count and not is_error:
                                fis = slot_header[0x20:0x30]
                                lba, sectors = _synthetic_rw_location(command, fis)
                                if synthetic_disk_model:
                                    if count != synthetic_logical_sector_bytes * sectors:
                                        raise ImageError("synthetic READ sector count and PRDT length differ")
                                    host_data[:] = b"".join(
                                        disk_sectors.get(lba + index,
                                                         b"\x5A" * (synthetic_logical_sector_bytes - 2) + b"\x55\xAA")
                                        for index in range(sectors))
                                else:
                                    host_data[:] = (
                                        b"\x5A" * (synthetic_logical_sector_bytes - 2) + b"\x55\xAA"
                                    ) * (count // synthetic_logical_sector_bytes)
                                synthetic_host_data_transfers.append({
                                    "bus_address": f"0x{host_data_address:016X}",
                                    "bytes": count,
                                    "source": "synthetic disk sector" if synthetic_disk_model
                                              else "synthetic LBA-0 sector",
                                    **({"lba": lba, "sectors": sectors}
                                       if synthetic_disk_model else {}),
                                })
                        elif (not is_error and synthetic_sata_polling and
                              allow_modified_image):
                            emu.mem_write(buffer, b"\x5A" * 510 + b"\x55\xAA")
                    elif command in (0x35, 0xCA):
                        slot_header = bytes.fromhex(event["command_slot_raw"])
                        table_low, table_high = struct.unpack_from("<II", slot_header, 8)
                        issued_table_address = (table_high << 32) | (table_low & ~0x3F)
                        if (synthetic_host_command_table is not None
                                and issued_table_address == synthetic_host_command_table[0]
                                and host_data is not None and not is_error):
                            count = synthetic_prdt_bytes(slot_header)
                            if count:
                                fis = slot_header[0x20:0x30]
                                lba, sectors = _synthetic_rw_location(command, fis)
                                if synthetic_disk_model:
                                    if count != synthetic_logical_sector_bytes * sectors:
                                        raise ImageError("synthetic WRITE sector count and PRDT length differ")
                                    for index in range(sectors):
                                        disk_sectors[lba + index] = bytes(
                                            host_data[synthetic_logical_sector_bytes * index:
                                                      synthetic_logical_sector_bytes * (index + 1)])
                                synthetic_host_data_transfers.append({
                                    "bus_address": f"0x{host_data_address:016X}",
                                    "bytes": count,
                                    "source": "synthetic WRITE sector",
                                    "sha256": hashlib.sha256(host_data).hexdigest(),
                                    **({"lba": lba, "sectors": sectors}
                                       if synthetic_disk_model else {}),
                                })
                    if (synthetic_host_cpu_window and host_data is not None
                            and len(host_data) <= 4096):
                        window_data = 0x50000000 | (host_data_address & 0xFFFF)
                        emu.mem_write(window_data, bytes(host_data))
                    synthetic_completions.append({
                        "command": event["ata_command"],
                        "slot": event["slot"],
                        "buffer": event["data_buffer"],
                    })
                    if synthetic_backend_received_fis is not None:
                        emu.mem_write(0x30067000, synthetic_backend_received_fis)
                    if is_error:
                        emu.mem_write(0x8000A920, struct.pack("<I", 0x00000451))
                        emu.mem_write(0x30067040,
                                      bytes((0x34, 0x40, 0x51, 0x04)) + bytes(12))
                    emu.mem_write(0x8000A808, struct.pack("<I", 1))
                    port_is = (1 << 30) if is_error else (
                        1 if command in (0x06, 0x25, 0x35, 0xC8, 0xCA,
                                         0xE7, 0xEA, 0xEF, 0xF5) else 2)
                    emu.mem_write(0x8000A910, struct.pack("<I", port_is))
                    ci = struct.unpack("<I", emu.mem_read(0x8000A938, 4))[0]
                    emu.mem_write(0x8000A938, struct.pack("<I", ci & ~(1 << event["slot"])))
                    sact = struct.unpack("<I", emu.mem_read(0x8000A934, 4))[0]
                    emu.mem_write(0x8000A934, struct.pack("<I", sact & ~(1 << event["slot"])))
                    if not synthetic_sata_polling:
                        synthetic_irq_injected = True
                        deliver_irq(emu, address, 1)
                    elif (len(synthetic_completions) - 1 == synthetic_irq_on_completion_index
                          and struct.unpack("<I", emu.mem_read(0xD0020204, 4))[0] & 1
                          and struct.unpack("<I", emu.mem_read(0x8000A914, 4))[0] & port_is):
                        emu.mem_write(0xD0020200, struct.pack("<I", 1))
                        synthetic_irq_pending = True
        if (synthetic_irq_pending and address == synthetic_sata_idle_pc
                and not (emu.reg_read(UC_ARM_REG_CPSR) & 0x80)):
            synthetic_irq_pending = False
            synthetic_irq_injected = True
            deliver_irq(emu, address, 1)
        if fast_delays and address in (0x17E4, 0x1810):


            emu.reg_write(UC_ARM_REG_PC, emu.reg_read(UC_ARM_REG_LR))

    uc.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)
    uc.hook_add(UC_HOOK_MEM_READ, on_read)
    uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
    uc.hook_add(UC_HOOK_CODE, on_code)
    uc.reg_write(UC_ARM_REG_CPSR, 0xD3)
    uc.reg_write(UC_ARM_REG_SP, 0x04004000)
    uc.reg_write(UC_ARM_REG_PC, 0)
    try:
        uc.emu_start(0, 0xFFFFFFFF, count=max_steps)
    except UcError as exc:
        if stop_reason == "instruction limit":
            stop_reason = str(exc)
    result = {
        "instructions": instructions,
        "last_pc": f"0x{last_pc:08X}",
        "last_pc_outside_delay": f"0x{last_pc_outside_delay:08X}",
        "lr": f"0x{uc.reg_read(UC_ARM_REG_LR):08X}",
        "sp": f"0x{uc.reg_read(UC_ARM_REG_SP):08X}",
        "stop_reason": stop_reason,
        "uart": uart.decode("ascii", errors="replace"),
        "uart_rx_remaining": len(uart_rx),
        "unknown_pages": [
            {"access": access, "base": f"0x{base:08X}", "count": count}
            for (access, base), count in unknown.most_common()
        ],
        "spi_read_trace": spi_trace,
        "revision_writes": revision_writes,
        "port0_command_issues": port0_command_issues,
        "synthetic_irq_injected": synthetic_irq_injected,
        "debug_irq_injected": debug_irq_injected,
        "synthetic_completions": synthetic_completions,
        "synthetic_host_events_delivered": synthetic_host_events_delivered,
        "synthetic_late_host_delivered": synthetic_late_host_delivered,
        "synthetic_open_port_reset_phase": synthetic_open_port_reset_phase,
        "synthetic_open_followup_delivered": synthetic_open_followup_delivered,
        "synthetic_open_console_delivered": synthetic_open_console_delivered,
        "synthetic_open_console_followups_delivered": synthetic_open_console_followups_delivered,
        "synthetic_host_port_event_delivered": synthetic_host_port_event_delivered,
        "synthetic_stock_host_followups_delivered": synthetic_stock_host_followups_delivered,
        "synthetic_stock_host_followup_snapshots": synthetic_stock_host_followup_snapshots,
        "synthetic_frontend_worker_called": synthetic_frontend_worker_called,
        "synthetic_frontend_consumer_called": synthetic_frontend_consumer_called,
        "synthetic_backend_task_drain_called": synthetic_backend_task_drain_called,
        "synthetic_host_auto_fetches": synthetic_host_auto_fetches,
        "synthetic_host_fis_fetches": synthetic_host_fis_fetches,
        "synthetic_open_autofetch_delivered": synthetic_open_autofetch_delivered,
        "synthetic_host_data_transfers": synthetic_host_data_transfers,
        "synthetic_disk_sector_hashes": {
            str(lba): hashlib.sha256(data).hexdigest()
            for lba, data in disk_sectors.items()
        },
        "pcie_window_accesses": pcie_window_accesses,
        "frontend_fis_snapshots": frontend_fis_snapshots,
        "backend_fis_accesses": backend_fis_accesses,
        "irq_vector_visits": irq_vector_visits,
        "irq_code_trace": irq_code_trace,
        "code_visits": {f"0x{address:08X}": code_visits[address]
                        for address in code_visit_addresses},
        "code_visit_samples": code_visit_samples,
        "trace_after": trace_after,
        "fault_context": fault_context,
        "watched_ram_writes": watched_ram_writes,
        "identify_parse_trace": identify_parse_trace,
        "raid_scan_entries": raid_scan_entries,
    }
    if not allow_modified_image:
        result["vport_map_count"] = struct.unpack("<I", uc.mem_read(0x0400006C, 4))[0]
        result["vport_map_raw"] = [
            f"0x{struct.unpack('<I', uc.mem_read(0x3005552C + i * 4, 4))[0]:08X}"
            for i in range(8)
        ]
    if inject_irq_at_pc is not None:
        result["stage_markers"] = {
            "boot": f"0x{struct.unpack('<I', uc.mem_read(0x04001000, 4))[0]:08X}",
            "irq_count": struct.unpack("<I", uc.mem_read(0x04001004, 4))[0],
            "irq_last": f"0x{struct.unpack('<I', uc.mem_read(0x04001008, 4))[0]:08X}",
            "cpsr": f"0x{uc.reg_read(UC_ARM_REG_CPSR):08X}",
        }
    if report_memory_ranges:
        result["memory_snapshots"] = {
            f"0x{address:08X}": bytes(uc.mem_read(address, length)).hex()
            for address, length in report_memory_ranges
            if 0 < length <= 4096
        }
    if host_data is not None:
        if (synthetic_host_cpu_window and synthetic_host_auto_fetches
                and len(host_data) <= 4096):
            window_data = 0x50000000 | (host_data_address & 0xFFFF)
            host_data[:] = uc.mem_read(window_data, len(host_data))
        result["synthetic_host_prdt_data"] = bytes(host_data).hex()
    if (synthetic_host_cpu_window and synthetic_host_command_list is not None
            and synthetic_host_auto_fetches):
        result["synthetic_host_command_list_data"] = bytes(uc.mem_read(
            0x50000000 | (synthetic_host_command_list[0] & 0xFFFF), 0x400)).hex()
    if synthetic_host_rfis_buffer is not None:
        result["synthetic_host_rfis_data"] = bytes(
            uc.mem_read(0x50000000 | (rfis_address & 0xFFFF), 0x100)).hex()
    if synthetic_open_console_prdt_buffer is not None:
        console_data_address, console_initial = synthetic_open_console_prdt_buffer
        window_data = 0x50000000 | (console_data_address & 0xFFFF)
        result["synthetic_open_console_prdt_data"] = bytes(
            uc.mem_read(window_data, len(console_initial))).hex()
    if capture_mmio:
        result["mmio_trace"] = mmio_trace
        result["mmio_dropped"] = mmio_dropped
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--steps", type=int, default=200000)
    parser.add_argument("--mmio-trace", type=Path, help="write detailed MMIO trace as JSON")
    parser.add_argument("--port0-sstatus", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--fast-delays", action="store_true")
    parser.add_argument("--experimental-sata-io", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.steps <= 10_000_000:
        parser.error("--steps must be between 1 and 10000000")
    if not 0 <= args.port0_sstatus <= 0xFFFFFFFF:
        parser.error("--port0-sstatus must be a 32-bit word")
    try:
        if args.mmio_trace and args.mmio_trace.resolve() == args.image.resolve():
            raise ImageError("MMIO trace path must differ from input image")
        result = run(
            args.image.read_bytes(),
            args.steps,
            capture_mmio=bool(args.mmio_trace),
            port0_sstatus=args.port0_sstatus,
            fast_delays=args.fast_delays,
            experimental_sata_io=args.experimental_sata_io,
        )
        if args.mmio_trace:
            args.mmio_trace.parent.mkdir(parents=True, exist_ok=True)
            args.mmio_trace.write_text(json.dumps(result.pop("mmio_trace"), indent=2), encoding="utf-8")
            result["mmio_trace_path"] = str(args.mmio_trace.resolve())
    except (OSError, ImageError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
