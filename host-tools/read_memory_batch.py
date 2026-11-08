
"""Read/benchmark 1..16 physical pages with the CH568/9230 0x133B path."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
import time
import zlib


VID = 0x4348
PID = 0x5637
EP_OUT = 0x01
EP_IN = 0x81
PAGE_SIZE = 4096
MAX_PAGES = 16
REQUEST_MAGIC = b"CHBQ"
RESPONSE_MAGIC = b"CHB1"
TRAILER_MAGIC = b"CEND"
READY_MAGIC = b"CHBR"
REQUEST_HEADER_SIZE = 16
RESPONSE_HEADER_SIZE = 32
RESPONSE_TRAILER_SIZE = 24
READY_SIZE = 20

ERROR_NAMES = {
    0: "success",
    1: "mailbox timeout",
    2: "SATA receive CRC error",
    3: "invalid SATA Data FIS length/state",
    4: "SATA transmit error",
    5: "SATA PHY/link error",
    6: "USB bus reset",
    7: "SATA FIFO overflow",
}


def parse_address(value: str) -> int:
    try:
        result = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a physical address") from exc
    if not 0 <= result <= 0xFFFFFFFFFFFFFFFF:
        raise argparse.ArgumentTypeError("address is outside the 64-bit range")
    if result & (PAGE_SIZE - 1):
        raise argparse.ArgumentTypeError("address must be 4-KiB aligned")
    return result


def make_request(addresses: list[int], skip_crc: bool = False) -> bytes:
    header = struct.pack(
        "<4sBBHII", REQUEST_MAGIC, 1, len(addresses),
        REQUEST_HEADER_SIZE, 1 if skip_crc else 0, 0,
    )
    entries = b"".join(
        struct.pack("<II", address & 0xFFFFFFFF, address >> 32)
        for address in addresses
    )
    return header + entries


def make_linear_request(address: int, pages: int,
                        skip_crc: bool = False) -> bytes:
    return struct.pack(
        "<4sBBHBB2x", b"CHLQ", 1, pages, 24, 1 if skip_crc else 0, 0
    ) + struct.pack(
        "<II4x", address >> 32, address & 0xFFFFFFFF
    )


def read_packet(device, timeout_ms: int, size: int = 512) -> bytes:
    return bytes(device.read(EP_IN, size, timeout=timeout_ms))


def is_diagnostic_packet(packet: bytes) -> bool:
    return len(packet) < 512 and (
        packet.startswith(b"LOG ") or packet.startswith(b"ERR ")
    )


def print_diagnostic(packet: bytes, started: float | None = None) -> None:
    prefix = ""
    if started is not None:
        prefix = f"[{time.perf_counter() - started:8.3f}s] "
    print(prefix + packet.decode("ascii", errors="replace").rstrip())


def print_trace(started: float, text: str) -> None:
    print(f"[{time.perf_counter() - started:8.3f}s] TRACE {text}")


def drain_stale_input(device, verbose: bool) -> int:
    drained = 0
    while drained < 128:
        try:
            packet = read_packet(device, 100)
        except Exception as exc:
            if exc.__class__.__name__ == "USBTimeoutError":
                break
            raise
        drained += 1
        if verbose and is_diagnostic_packet(packet):
            print(f"STALE {packet.decode('ascii', errors='replace').rstrip()}")
    if drained:
        print(f"drained {drained} stale USB packet(s) before benchmark")
    return drained


def read_batch(device, request: bytes, expected_pages: int, timeout: float,
               verbose: bool, usb_read_size: int = 65536,
               skip_crc: bool = False) -> tuple[bytes, int, float]:
    started = time.perf_counter()
    device.write(EP_OUT, request, timeout=1000)
    if verbose:
        print_trace(started, "USB batch request submitted")
    deadline = time.perf_counter() + timeout
    unexpected_binary_packets = 0
    unexpected_binary_bytes = 0

    header = None
    while time.perf_counter() < deadline:
        try:
            packet = read_packet(device, min(1000, max(1, int(timeout * 1000))))
        except Exception as exc:
            if exc.__class__.__name__ == "USBTimeoutError":
                continue
            raise
        if packet.startswith(RESPONSE_MAGIC):
            header = packet
            break
        if packet.startswith(b"CH5K") and len(packet) >= 28:
            _, frame_size, _, error_status, error_sequence = \
                struct.unpack_from("<4sHBBI", packet)
            if frame_size == len(packet) and error_status:
                name = ERROR_NAMES.get(
                    error_status, f"unknown error {error_status}"
                )
                raise RuntimeError(
                    f"CH568 mailbox returned {name} before CHB1 "
                    f"(CH5K seq={error_sequence})"
                )
        if packet.startswith(b"ERR USB command already pending"):
            print_diagnostic(packet, started)
            raise RuntimeError(
                "device mailbox is still busy; stale response was not released"
            )
        if is_diagnostic_packet(packet) and (
                verbose or packet.startswith(b"ERR ")):
            print_diagnostic(packet, started)
    if header is None:
        raise TimeoutError("timeout waiting for CHB1 response header")
    if verbose:
        print_trace(started, "CHB1 header received")
    if len(header) != RESPONSE_HEADER_SIZE:
        raise RuntimeError(f"invalid CHB1 header length {len(header)}")

    magic, header_size, version, initial_status, sequence = struct.unpack_from(
        "<4sHBBI", header, 0
    )
    page_count = struct.unpack_from("<H", header, 12)[0]
    expected_length, trailer_size, flags = struct.unpack_from("<III", header, 16)
    if (magic != RESPONSE_MAGIC or header_size != RESPONSE_HEADER_SIZE or
            version != 1 or initial_status != 0 or
            page_count != expected_pages or
            expected_length != expected_pages * PAGE_SIZE or
            trailer_size != RESPONSE_TRAILER_SIZE or not (flags & 1)):
        raise RuntimeError("invalid or stale CHB1 response header")

    payload = bytearray()
    trailer = None
    while len(payload) < expected_length and time.perf_counter() < deadline:
        try:


            packet = read_packet(
                device, 1000,
                min(usb_read_size, expected_length - len(payload)),
            )
        except Exception as exc:
            if exc.__class__.__name__ == "USBTimeoutError":
                continue
            raise


        if len(packet) >= RESPONSE_TRAILER_SIZE:
            possible_trailer = packet[-RESPONSE_TRAILER_SIZE:]
            if possible_trailer.startswith(TRAILER_MAGIC):
                _, candidate_sequence, received, candidate_crc, _, pages = \
                    struct.unpack("<4sIIIII", possible_trailer)
                data_before_trailer = packet[:-RESPONSE_TRAILER_SIZE]
                if (candidate_sequence == sequence and
                        received == len(payload) + len(data_before_trailer) and
                        pages == expected_pages and
                        (skip_crc and candidate_crc == 0 or
                         zlib.crc32(data_before_trailer,
                                    zlib.crc32(payload)) & 0xFFFFFFFF
                         == candidate_crc)):
                    packet = data_before_trailer
                    trailer = possible_trailer
        if is_diagnostic_packet(packet):
            if verbose or packet.startswith(b"ERR "):
                print_diagnostic(packet, started)
            continue
        if len(payload) + len(packet) > expected_length:
            raise RuntimeError("batch payload exceeded declared length")
        payload.extend(packet)
        if trailer is not None:
            break
    if len(payload) != expected_length and trailer is None:
        raise TimeoutError(
            f"timeout after {len(payload)}/{expected_length} payload bytes"
        )
    if verbose and len(payload) == expected_length:
        print_trace(started, f"payload complete ({len(payload)} bytes)")

    while trailer is None and time.perf_counter() < deadline:
        try:
            packet = read_packet(device, 1000)
        except Exception as exc:
            if exc.__class__.__name__ == "USBTimeoutError":
                continue
            raise
        if packet.startswith(TRAILER_MAGIC):
            trailer = packet
            break
        if is_diagnostic_packet(packet) and (
                verbose or packet.startswith(b"ERR ")):
            print_diagnostic(packet, started)
        elif not is_diagnostic_packet(packet):
            unexpected_binary_packets += 1
            unexpected_binary_bytes += len(packet)
    if trailer is None:
        raise TimeoutError("timeout waiting for CEND trailer")
    if verbose:
        print_trace(started, "CEND trailer received")
    if len(trailer) != RESPONSE_TRAILER_SIZE:
        raise RuntimeError(f"invalid CEND trailer length {len(trailer)}")

    magic, trailer_sequence, received, expected_crc, status, trailer_pages = \
        struct.unpack("<4sIIIII", trailer)
    if magic != TRAILER_MAGIC or trailer_sequence != sequence:
        raise RuntimeError("stale or malformed CEND trailer")
    ready = None
    while time.perf_counter() < deadline:
        try:
            packet = read_packet(device, 1000)
        except Exception as exc:
            if exc.__class__.__name__ == "USBTimeoutError":
                continue
            raise
        if packet.startswith(READY_MAGIC):
            ready = packet
            break
        if is_diagnostic_packet(packet) and (
                verbose or packet.startswith(b"ERR ")):
            print_diagnostic(packet, started)
        elif not is_diagnostic_packet(packet):
            unexpected_binary_packets += 1
            unexpected_binary_bytes += len(packet)
    if ready is None:
        raise TimeoutError("timeout waiting for CHBR ready handshake")
    if verbose:
        print_trace(started, "CHBR ready handshake received")
    if len(ready) != READY_SIZE:
        raise RuntimeError(f"invalid CHBR length {len(ready)}")
    ready_magic, ready_sequence, ready_status, sata_flags, rx_length = \
        struct.unpack("<4sIIII", ready)
    if (ready_magic != READY_MAGIC or ready_sequence != sequence or
            ready_status != status):
        raise RuntimeError("stale or malformed CHBR ready handshake")

    if verbose:
        print(
            f"DIAG SATA_FG=0x{sata_flags:04X}, RX_LEN={rx_length}"
        )
    if unexpected_binary_packets:
        print(
            f"Ignored {unexpected_binary_packets} unexpected binary USB "
            f"packet(s), {unexpected_binary_bytes} bytes total while "
            "finishing the batch"
        )

    if status:
        name = ERROR_NAMES.get(status, f"unknown error {status}")
        raise RuntimeError(
            f"batch failed: {name}; received {received}/{expected_length} bytes; "
            f"SATA_FG=0x{sata_flags:04X}, RX_LEN={rx_length}"
        )
    if (received != expected_length or len(payload) != expected_length or
            trailer_pages != expected_pages):
        raise RuntimeError(
            f"CEND byte/page count mismatch: payload={len(payload)}, "
            f"received={received}, expected={expected_length}"
        )
    actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if not skip_crc and actual_crc != expected_crc:
        raise RuntimeError(
            f"CRC mismatch: got {actual_crc:08X}, expected {expected_crc:08X}"
        )
    return bytes(payload), sequence, time.perf_counter() - started


def load_usb_backend():
    """Resolve the pip-installed libusb-1.0 DLL for PyUSB on Windows."""
    import ctypes.util
    import glob
    import os
    import sysconfig

    if ctypes.util.find_library("libusb-1.0"):
        return None
    machine = {
        "AMD64": "x86_64", "ARM64": "arm64", "x86": "x86", "IA64": "*",
    }.get(os.environ.get("PROCESSOR_ARCHITEW6432")
          or os.environ.get("PROCESSOR_ARCHITECTURE"), "*")
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "libusb-1.0.dll"),
        os.path.join(sysconfig.get_paths()["purelib"], "libusb", "_platform",
                     "windows", machine, "libusb-1.0.dll"),
        os.path.join(sysconfig.get_paths()["purelib"], "libusb", "_platform",
                     "windows", "*", "libusb-1.0.dll"),
    ]
    for pattern in candidates:
        for path in sorted(glob.glob(pattern)):
            from usb.backend import libusb1
            return libusb1.get_backend(find_library=lambda name, _p=path: _p)
    print("libusb-1.0.dll not found: run  py -m pip install libusb", file=sys.stderr)
    raise SystemExit(2)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", nargs="?", type=parse_address,
                        default=0x100000)
    parser.add_argument("--pages", type=int, default=16,
                        help="pages per batch, 1..16 (default: 16)")
    parser.add_argument("--batches", type=int, default=64,
                        help="number of batches (default: 64)")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="per-batch timeout in seconds (default: 5)")
    parser.add_argument("--same", action="store_true",
                        help="repeat the same physical pages instead of advancing")
    parser.add_argument(
        "--require-identical", action="store_true",
        help="with --same, fail if a later batch differs byte-for-byte",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--linear", action="store_true",
        help="one 0x1341 linear command per batch instead of a 0x133B page list",
    )
    parser.add_argument(
        "--no-crc", action="store_true",
        help="skip the device-side stream CRC32 (SATA/USB CRC still apply)",
    )
    parser.add_argument(
        "--usb-read-size", type=int, default=65536,
        help="payload bytes per USB read, 512..65536 (default: 65536)",
    )
    parser.add_argument(
        "--inter-batch-delay", type=float, default=0,
        help="diagnostic pause after CHBR, before the next request (seconds)",
    )
    args = parser.parse_args()
    page_limit = 128 if args.linear else MAX_PAGES
    if not 1 <= args.pages <= page_limit:
        parser.error(f"--pages must be in range 1..{page_limit}"
                     f"{' for linear' if args.linear else ''}")
    if args.batches < 1 or args.timeout <= 0:
        parser.error("--batches and --timeout must be positive")
    if args.require_identical and not args.same:
        parser.error("--require-identical requires --same")
    if not 512 <= args.usb_read_size <= 65536 or args.usb_read_size % 512:
        parser.error("--usb-read-size must be a multiple of 512 in 512..65536")
    if args.inter_batch_delay < 0:
        parser.error("--inter-batch-delay must be nonnegative")

    try:
        import usb.core
        import usb.util
    except ModuleNotFoundError:
        print("PyUSB is required: py -m pip install pyusb", file=sys.stderr)
        return 2

    device = usb.core.find(idVendor=VID, idProduct=PID, backend=load_usb_backend())
    if device is None:
        print(f"CH568 mailbox {VID:04x}:{PID:04x} not found", file=sys.stderr)
        return 2
    device.set_configuration()
    usb.util.claim_interface(device, 0)
    drain_stale_input(device, args.verbose)

    durations: list[float] = []
    total_bytes = 0
    reference_payload: bytes | None = None
    reference_crc: int | None = None
    overall_start = time.perf_counter()
    try:
        for batch_index in range(args.batches):
            if batch_index and args.inter_batch_delay:
                if args.verbose:
                    print(f"TRACE waiting {args.inter_batch_delay:g}s after CHBR")
                time.sleep(args.inter_batch_delay)
            batch_base = args.address if args.same else (
                args.address + batch_index * args.pages * PAGE_SIZE
            )
            if args.linear:
                request = make_linear_request(
                    batch_base, args.pages, args.no_crc)
            else:
                request = make_request(
                    [batch_base + index * PAGE_SIZE
                     for index in range(args.pages)], args.no_crc)
            payload, sequence, duration = read_batch(
                device, request, args.pages, args.timeout, args.verbose,
                args.usb_read_size, args.no_crc,
            )
            payload_crc = zlib.crc32(payload) & 0xFFFFFFFF
            if args.same and reference_payload is None:
                reference_payload = payload
                reference_crc = payload_crc
            elif args.same and payload != reference_payload:
                first_difference = next(
                    index for index, (left, right) in
                    enumerate(zip(reference_payload, payload))
                    if left != right
                )
                message = (
                    f"repeated range changed at +0x{first_difference:X}: "
                    f"reference CRC={reference_crc:08X}, "
                    f"current CRC={payload_crc:08X}"
                )
                if args.require_identical:
                    raise RuntimeError(message)
                print(f"WARNING: {message}", file=sys.stderr)
            durations.append(duration)
            total_bytes += args.pages * PAGE_SIZE
            if args.verbose or batch_index == 0 or batch_index + 1 == args.batches:
                mib_s = args.pages * PAGE_SIZE / duration / (1024 * 1024)
                print(
                    f"batch {batch_index + 1}/{args.batches} seq={sequence} "
                    f"{duration * 1000:.2f} ms {mib_s:.4f} MiB/s "
                    f"CRC={payload_crc:08X}"
                )
    except (TimeoutError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    finally:
        usb.util.release_interface(device, 0)

    overall = time.perf_counter() - overall_start
    steady_duration = sum(durations[1:]) if len(durations) > 1 else durations[0]
    steady_bytes = (len(durations) - 1 if len(durations) > 1 else 1) * \
        args.pages * PAGE_SIZE
    print(
        f"total: {total_bytes / (1024 * 1024):.4f} MiB in {overall:.3f}s = "
        f"{total_bytes / overall / (1024 * 1024):.4f} MiB/s"
    )
    print(
        f"steady (first idle-poll batch excluded): "
        f"{steady_bytes / steady_duration / (1024 * 1024):.4f} MiB/s"
    )
    steady_samples = durations[1:] if len(durations) > 1 else durations
    ordered = sorted(steady_samples)
    p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    print(
        f"latency: median={statistics.median(steady_samples) * 1000:.2f} ms, "
        f"p95={ordered[p95_index] * 1000:.2f} ms, "
        f"max={max(steady_samples) * 1000:.2f} ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
