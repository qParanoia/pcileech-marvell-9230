#!/usr/bin/env python3
"""Run one raw READ4K request and display every CH568 diagnostic message."""

import argparse
import struct
import sys
import time
import zlib

VID = 0x4348
PID = 0x5637
EP_OUT = 0x01
EP_IN = 0x81
FRAME_MAGIC = b"CH5K"
READY_MAGIC = b"CH5R"
FRAME_HEADER_SIZE = 32
READY_SIZE = 12
READ_SIZE = 4096

ERROR_NAMES = {
    1: "mailbox timeout",
    2: "SATA receive CRC error",
    3: "invalid SATA Data FIS length",
    4: "SATA transmit error",
    5: "SATA PHY/link error",
    6: "USB bus reset",
}


def is_diagnostic_packet(packet: bytes) -> bool:
    return packet.startswith(b"LOG ") or packet.startswith(b"ERR ")


def diagnostic_text(packet: bytes) -> str:
    return packet.decode("ascii", errors="replace").rstrip()


def parse_address(value: str) -> int:
    try:
        result = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a hexadecimal address") from exc
    if not 0 <= result <= 0xFFFFFFFFFFFFFFFF:
        raise argparse.ArgumentTypeError("address is outside the 64-bit range")
    if result & 0xFFF:
        raise argparse.ArgumentTypeError("READ4K address must be 4-KiB aligned")
    return result


def hexdump(data: bytes, address: int, length: int = 64) -> None:
    for offset in range(0, min(length, len(data)), 16):
        row = data[offset : offset + 16]
        hex_column = " ".join(f"{value:02X}" for value in row)
        text_column = "".join(chr(value) if 32 <= value < 127 else "." for value in row)
        print(f"{address + offset:016X}  {hex_column:<47}  {text_column}")


def drain_stale_input(device, usb_core, verbose: bool = True) -> int:
    drained = 0
    while drained < 64:
        try:
            packet = bytes(device.read(EP_IN, 512, timeout=100))
        except usb_core.USBTimeoutError:
            break
        drained += 1
        if verbose and is_diagnostic_packet(packet):
            print(f"[stale] {diagnostic_text(packet)}")
    if drained:
        print(f"Drained {drained} stale USB packet(s) before request")
    return drained


def load_usb_backend():
    """Resolve the libusb-1.0 backend on Windows.

    PyUSB's default discovery only sees DLLs on PATH, but ``py -m pip install
    libusb`` places them inside site-packages. Return None when the default
    discovery already works; otherwise hand PyUSB the DLL path explicitly.
    A libusb-1.0.dll next to this script also wins.
    """
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
    parser.add_argument("address", nargs="?", type=parse_address, default=0x100000)
    parser.add_argument(
        "--timeout", type=float, default=300.0,
        help="seconds to wait (default: 300)",
    )
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")

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
    drain_stale_input(device, usb.core)
    start = time.monotonic()
    saw_command = False
    saw_data = False
    saw_dma = False
    frame = bytearray()
    frame_started = False
    expected_crc = 0
    unexpected_binary_packets = 0
    unexpected_binary_bytes = 0
    duplicate_frame = bytearray()
    duplicate_frame_started = False
    duplicate_expected_crc = 0
    try:
        request = (
            f"R4K {(args.address >> 32) & 0xFFFFFFFF:08X} "
            f"{args.address & 0xFFFFFFFF:08X}\n"
        ).encode("ascii")
        print(f"Sending {request.decode().strip()} with {args.timeout:g}s timeout")
        device.write(EP_OUT, request, timeout=1000)
        deadline = start + args.timeout
        while time.monotonic() < deadline:
            try:
                packet = bytes(device.read(EP_IN, 512, timeout=1000))
            except usb.core.USBTimeoutError:
                continue

            if not frame_started and packet.startswith(FRAME_MAGIC):
                if len(packet) < FRAME_HEADER_SIZE:
                    print("Invalid short CH5K header", file=sys.stderr)
                    return 3
                header_size = int.from_bytes(packet[4:6], "little")
                version = packet[6]
                status = packet[7]
                sequence = int.from_bytes(packet[8:12], "little")
                response_address = (
                    int.from_bytes(packet[16:20], "little") << 32
                ) | int.from_bytes(packet[12:16], "little")
                payload_length = int.from_bytes(packet[20:24], "little")
                expected_crc = int.from_bytes(packet[24:28], "little")
                if header_size != FRAME_HEADER_SIZE or version != 3:
                    print(
                        f"Unsupported CH5K header: size={header_size}, version={version}",
                        file=sys.stderr,
                    )
                    return 3
                if status:
                    error = ERROR_NAMES.get(status, f"unknown error {status}")
                    print(
                        f"READ4K failed: {error}; sequence={sequence}, "
                        f"address={response_address:#x}",
                        file=sys.stderr,
                    )
                    return 4
                if response_address != args.address:
                    print(
                        f"Stale CH5K response address {response_address:#x}; "
                        f"expected {args.address:#x}",
                        file=sys.stderr,
                    )
                    return 3
                if payload_length != READ_SIZE:
                    print(f"Invalid CH5K payload length: {payload_length}", file=sys.stderr)
                    return 3
                frame_started = True
                frame.extend(packet[FRAME_HEADER_SIZE:])
                print(
                    f"[{time.monotonic() - start:8.3f}s] CH5K frame started "
                    f"(sequence {sequence})"
                )
            elif frame_started:
                frame.extend(packet)
            elif is_diagnostic_packet(packet):
                message = diagnostic_text(packet)
                print(f"[{time.monotonic() - start:8.3f}s] {message}")
                saw_command |= "command 133" in message and "sent to Marvell" in message
                saw_data |= "memory-data F1/A5 received" in message
                saw_dma |= "READ4K-DMA WRITE35 received" in message
            else:
                unexpected_binary_packets += 1
                unexpected_binary_bytes += len(packet)
                print(
                    f"[{time.monotonic() - start:8.3f}s] "
                    f"Ignored unexpected binary USB packet before CH5K "
                    f"({len(packet)} bytes, prefix={packet[:8].hex()})"
                )

            if frame_started and len(frame) >= READ_SIZE:
                if len(frame) != READ_SIZE:
                    print(f"Oversized CH5K payload: {len(frame)} bytes", file=sys.stderr)
                    return 3
                actual_crc = zlib.crc32(frame) & 0xFFFFFFFF
                if actual_crc != expected_crc:
                    print(
                        f"CH5K CRC mismatch: got {actual_crc:08X}, "
                        f"expected {expected_crc:08X}",
                        file=sys.stderr,
                    )
                    return 3
                ready = None
                while time.monotonic() < deadline:
                    try:
                        ready_packet = bytes(
                            device.read(EP_IN, 512, timeout=1000)
                        )
                    except usb.core.USBTimeoutError:
                        continue
                    if ready_packet.startswith(READY_MAGIC):
                        ready = ready_packet
                        break
                    if ready_packet.startswith(FRAME_MAGIC):
                        if duplicate_frame_started:
                            print(
                                "More than one duplicate CH5K header received",
                                file=sys.stderr,
                            )
                            return 3
                        if len(ready_packet) < FRAME_HEADER_SIZE:
                            print("Short duplicate CH5K header", file=sys.stderr)
                            return 3
                        duplicate_header_size = int.from_bytes(
                            ready_packet[4:6], "little"
                        )
                        duplicate_version = ready_packet[6]
                        duplicate_status = ready_packet[7]
                        duplicate_sequence = int.from_bytes(
                            ready_packet[8:12], "little"
                        )
                        duplicate_address = (
                            int.from_bytes(ready_packet[16:20], "little") << 32
                        ) | int.from_bytes(ready_packet[12:16], "little")
                        duplicate_length = int.from_bytes(
                            ready_packet[20:24], "little"
                        )
                        duplicate_expected_crc = int.from_bytes(
                            ready_packet[24:28], "little"
                        )
                        if (
                            duplicate_header_size != FRAME_HEADER_SIZE or
                            duplicate_version != 3 or
                            duplicate_status != 0 or
                            duplicate_sequence != sequence or
                            duplicate_address != args.address or
                            duplicate_length != READ_SIZE
                        ):
                            print(
                                "Unexpected non-matching duplicate CH5K frame",
                                file=sys.stderr,
                            )
                            return 3
                        duplicate_frame_started = True
                        duplicate_frame.extend(
                            ready_packet[FRAME_HEADER_SIZE:]
                        )
                    elif is_diagnostic_packet(ready_packet):
                        message = diagnostic_text(ready_packet)
                        print(f"[{time.monotonic() - start:8.3f}s] {message}")
                        saw_command |= (
                            "command 133" in message and
                            "sent to Marvell" in message
                        )
                        saw_data |= "memory-data F1/A5 received" in message
                        saw_dma |= "READ4K-DMA WRITE35 received" in message
                    elif duplicate_frame_started and len(duplicate_frame) < READ_SIZE:
                        duplicate_frame.extend(ready_packet)
                        if len(duplicate_frame) > READ_SIZE:
                            print(
                                f"Oversized duplicate CH5K payload: "
                                f"{len(duplicate_frame)} bytes",
                                file=sys.stderr,
                            )
                            return 3
                    else:
                        unexpected_binary_packets += 1
                        unexpected_binary_bytes += len(ready_packet)
                if ready is None:
                    print(
                        "Timeout waiting for CH5R ready handshake",
                        file=sys.stderr,
                    )
                    return 3
                if len(ready) != READY_SIZE:
                    print(
                        f"Invalid CH5R length: {len(ready)}",
                        file=sys.stderr,
                    )
                    return 3
                ready_sequence, ready_status = struct.unpack_from(
                    "<II", ready, 4
                )
                if ready_sequence != sequence or ready_status != 0:
                    print(
                        f"Invalid CH5R: sequence={ready_sequence}, "
                        f"status={ready_status}",
                        file=sys.stderr,
                    )
                    return 3
                if duplicate_frame_started:
                    if len(duplicate_frame) != READ_SIZE:
                        print(
                            f"Incomplete duplicate CH5K payload: "
                            f"{len(duplicate_frame)}/{READ_SIZE} bytes",
                            file=sys.stderr,
                        )
                        return 3
                    duplicate_crc = zlib.crc32(duplicate_frame) & 0xFFFFFFFF
                    if duplicate_crc != duplicate_expected_crc:
                        print(
                            f"Duplicate CH5K CRC mismatch: got "
                            f"{duplicate_crc:08X}, expected "
                            f"{duplicate_expected_crc:08X}",
                            file=sys.stderr,
                        )
                        return 3
                    if duplicate_frame != frame:
                        first_difference = next(
                            index for index, (left, right) in
                            enumerate(zip(frame, duplicate_frame))
                            if left != right
                        )
                        print(
                            f"Duplicate CH5K differs from original at "
                            f"+0x{first_difference:X}; original CRC="
                            f"{actual_crc:08X}, duplicate CRC="
                            f"{duplicate_crc:08X}",
                            file=sys.stderr,
                        )
                        return 3
                    print(
                        f"Duplicate CH5K frame matched original "
                        f"(CRC={duplicate_crc:08X})"
                    )
                if unexpected_binary_packets:
                    print(
                        f"Ignored {unexpected_binary_packets} unexpected "
                        f"binary USB packet(s), {unexpected_binary_bytes} "
                        "bytes total while completing this request"
                    )
                elapsed = time.monotonic() - start
                print(f"READ4K completed in {elapsed:.3f}s; first 64 bytes:")
                hexdump(bytes(frame), args.address)
                return 0
    finally:
        usb.util.release_interface(device, 0)

    print(f"READ4K timed out after {args.timeout:g}s.", file=sys.stderr)
    if not saw_command:
        print("No mailbox-command delivery log: the request did not reach the 9230 poll path.", file=sys.stderr)
    elif saw_dma:
        print(
            "WRITE DMA EXT reached CH568, but the 4-KiB Data FIS did not complete. "
            "Keep the full SATA diagnostic log.",
            file=sys.stderr,
        )
    elif not saw_data:
        print(
            "Command 1339 reached the 9230, but no F1/A5 data returned. "
            "Verify that the 9230 is flashed with the matching READ4K image.",
            file=sys.stderr,
        )
    else:
        print(
            "At least one F1/A5 data chunk arrived, but the 4-KiB transfer did not finish. "
            "Keep the complete timestamped log for the next patch.",
            file=sys.stderr,
        )
    print("Power-cycle both boards before issuing another mailbox command.", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
