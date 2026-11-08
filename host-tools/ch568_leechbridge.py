
"""LeechCore rawtcp bridge: expose the CH568/9230 DMA reader as a pcileech device.

Speaks the leechcore_device_rawtcp wire protocol (Synacktiv contribution,
default port 8888) on top of the USB mailbox transport.  Point MemProcFS or
pcileech at it with:  -device rawtcp://127.0.0.1:8888

Robustness model (board findings, 2026-10-29):
  * A READ-LINEAR into unmapped host physical memory hangs the 9230 DMA
    engine.  Reads are therefore clamped to SAFE_MAX_PHY (RAM below the PCI
    hole, always decodable); anything above answers with a FAILED READ - the
    same way FPGA hardware answers holes in the physical map.  Answering
    0xFF *data* instead made LeechCore's address auto-detection scan a
    48-bit FF desert probe by probe and never terminate.
  * After any transport failure the USB pipe is drained of stale frames
    (CH5K error, CH5R, CHB1/CEND/CHBR leftovers) so the mailbox releases,
    then the read is retried once; a second failure becomes a failed read.

Packet framing (little-endian, 24 bytes): cmd u32, pad u32, addr u64, cb u64.
  STATUS(0): server replies {0,0,1} + one ready byte
  MEM_READ(1): server replies {1,addr,cb} + cb data bytes; a reply with a
    foreign cmd value (0xFF) means the read failed - the plugin then reports
    "Memory read fail" and LeechCore treats the range as unmapped.
  MEM_WRITE(2): not supported by the transport yet; the reply carries a
    foreign cmd value so the client reports a write failure honestly.
"""
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")

import read_memory_batch as rmb
from read_memory_batch import load_usb_backend

PKT = struct.Struct("<IIQQ")
CMD_STATUS, CMD_READ, CMD_WRITE = 0, 1, 2
LINEAR_MAX_PAGES = 128
LISTEN_PORT = 8888


SAFE_RANGES = ((0x0, 0xC0000000), (0x100000000, 0x440000000))


def discover_safe_ranges(transport):
    """Learn the physical memory map from the SMBIOS tables in the F-segment.

    Type 19 (Memory Array Mapped Address) entries carry usable ranges; this
    is the same source the OS loader consumes.  Falls back to the bootstrap
    ranges when no table is found."""
    try:
        rom = transport.read(0xE0000, 0x20000)
    except Exception as exc:
        print(f"[bridge] SMBIOS scan failed: {exc}", flush=True)
        return list(SAFE_RANGES)
    pos = rom.find(b"_SM_")
    if pos < 0 or rom[pos + 0x10:pos + 0x14] != b"_DMI":
        print("[bridge] no SMBIOS anchor found; bootstrap ranges kept",
              flush=True)
        return list(SAFE_RANGES)
    table_len = int.from_bytes(rom[pos + 0x16:pos + 0x18], "little")
    table_addr = int.from_bytes(rom[pos + 0x18:pos + 0x1C], "little")
    table = transport.read(table_addr, table_len)
    ranges = []
    cursor = 0
    while cursor + 4 <= len(table):
        entry_type = table[cursor]
        entry_len = table[cursor + 1]
        if entry_len < 4 or cursor + entry_len > len(table):
            break
        if entry_type == 19 and entry_len >= 0x0F:
            start_kb = int.from_bytes(table[cursor + 4:cursor + 8], "little")
            end_kb = int.from_bytes(table[cursor + 8:cursor + 12], "little")
            if entry_len >= 0x1F and (start_kb == 0xFFFFFFFF or
                                      start_kb == 0 and end_kb == 0):
                start = int.from_bytes(table[cursor + 0x0F:cursor + 0x17],
                                       "little")
                end = int.from_bytes(table[cursor + 0x17:cursor + 0x1F],
                                     "little")
            else:
                start, end = start_kb << 10, end_kb << 10
            if end > start:
                ranges.append((start, (end + 1) & ~0xFFF))
        cursor += entry_len
    if not ranges:
        print("[bridge] SMBIOS had no mapped ranges; bootstrap kept", flush=True)
        return list(SAFE_RANGES)
    print("[bridge] SMBIOS physical map:", flush=True)
    for start, end in ranges:
        print(f"[bridge]   {start:#14x} - {end:#14x} "
              f"({(end - start) / (1 << 20):.0f} MiB)", flush=True)
    return ranges


LIVE_RANGES = list(SAFE_RANGES)


def discover_remap_top(transport, floor, ceiling):
    """Binary-search the real top of the remapped-above-4GiB RAM window.

    Needs v24g firmware: a probe into unmapped space hangs the 9230 engine,
    the firmware recovers the port, and the next probe tells the truth."""
    import time as _time
    good, bad = floor, ceiling
    while bad - good > 0x10000000:
        mid = (good + bad) // 2 & ~0xFFF
        for attempt in range(3):
            try:
                transport.read_linear(mid, 1)
                good = mid
                print(f"[bridge] probe {mid:#x}: RAM", flush=True)
                break
            except Exception:
                print(f"[bridge] probe {mid:#x}: no (attempt {attempt + 1})",
                      flush=True)
                _time.sleep(1.0)
        else:
            bad = mid
    top = good + 0x1000000
    print(f"[bridge] remap top resolved: {top:#x} "
          f"({(top - 0x100000000) / (1 << 30):.1f} GiB above 4 GiB)", flush=True)
    return top


def safe_limit(address: int):
    """Return the end of the live safe range containing address, else None."""
    for start, end in LIVE_RANGES:
        if start <= address < end:
            return end
    return None


class OutOfRange(Exception):
    pass


class Transport:
    """Serial access to the CH568 mailbox device, with self-healing."""

    def __init__(self):
        import usb.core
        import usb.util
        self.usb_core = usb.core
        self.usb_util = usb.util
        self.lock = threading.Lock()
        self.device = self.usb_core.find(idVendor=0x4348, idProduct=0x5637,
                                         backend=load_usb_backend())
        if self.device is None:
            raise SystemExit("CH568 mailbox 4348:5637 not found")
        self.device.set_configuration()
        self.usb_util.claim_interface(self.device, 0)
        try:
            import time as _t
            n = 0
            while n < 1024:
                bytes(self.device.read(0x81, 512, timeout=200))
                n += 1
        except Exception:
            pass

    def drain(self, quiet_ms=400, limit=512):
        """Consume stale USB frames until the pipe falls silent."""
        drained = 0
        try:
            while drained < limit:
                bytes(self.device.read(0x81, 512, timeout=quiet_ms))
                drained += 1
        except Exception:
            pass
        return drained

    def read_linear(self, base: int, pages: int) -> bytes:
        """One READ-LINEAR command with one drain-and-retry on failure."""
        for attempt in (1, 2):
            try:
                data, _, _ = rmb.read_batch(
                    self.device, rmb.make_linear_request(base, pages), pages,
                    8, False, 65536, True)
                return data
            except Exception as exc:
                print(f"[bridge] read {base:#x}x{pages}p attempt {attempt} "
                      f"failed: {exc}", flush=True)
                if attempt == 1:
                    self.drain()
        raise RuntimeError(f"transport stuck at {base:#x}")

    def set_firmware_map(self, ranges):
        """Push the safe ranges into the 9230 (mailbox 0x1342 via CHSM) so
        out-of-map addresses are rejected before the DMA engine is armed."""
        import struct as _s
        import time as _t
        frame = _s.pack("<4sBBH4x", b"CHSM", 1, len(ranges), 12)
        for start, end in ranges:
            frame += _s.pack("<IIII", start & 0xFFFFFFFF, start >> 32,
                             end & 0xFFFFFFFF, end >> 32)
        with self.lock:
            self.device.write(0x01, frame, timeout=1000)
            deadline = _t.time() + 10
            while _t.time() < deadline:
                try:
                    packet = bytes(self.device.read(0x81, 512, timeout=500))
                except Exception:
                    continue
                if b"set-map ack received" in packet:
                    print("[bridge] firmware map armed "
                          f"({len(ranges)} ranges)", flush=True)
                    return True
                if packet.startswith(b"ERR"):
                    print("[bridge] set-map rejected:", packet, flush=True)
                    return False
        print("[bridge] set-map ack not observed", flush=True)
        return False

    def read(self, address: int, size: int) -> bytes:
        """Read a range inside SAFE_RANGES; everything rides READ-LINEAR."""
        if size == 0:
            return b""
        limit = safe_limit(address)
        if limit is None:
            raise OutOfRange(address)
        chunks = []
        cursor = address
        remaining = size
        with self.lock:
            while remaining:
                limit = safe_limit(cursor)
                if limit is None:
                    raise OutOfRange(cursor)
                base = cursor & ~0xFFF
                span = max(min(limit - base, LINEAR_MAX_PAGES << 12) >> 12, 1)
                pages = min((remaining + (cursor - base) + 0xFFF) >> 12, span)
                if 0 < (pages << 12) - (cursor - base) - remaining < 8:
                    pages -= 1
                if pages == 0:
                    pages = 1
                data = self.read_linear(base, pages)
                take = min(remaining, len(data) - (cursor - base))
                chunks.append(data[cursor - base:cursor - base + take])
                cursor += take
                remaining -= take
        return b"".join(chunks)


def recv_exact(conn, size):
    data = bytearray()
    while len(data) < size:
        part = conn.recv(size - len(data))
        if not part:
            return None
        data.extend(part)
    return bytes(data)


def serve_client(conn, transport, peer):
    print(f"[bridge] client {peer} connected", flush=True)
    stats = {"reads": 0, "bytes": 0, "fails": 0, "t0": time.time()}
    last_report = 0.0
    try:
        while True:
            header = recv_exact(conn, PKT.size)
            if header is None:
                break
            cmd, _, addr, cb = PKT.unpack(header)
            if cmd == CMD_STATUS:
                conn.sendall(PKT.pack(CMD_STATUS, 0, 0, 1) + b"\x01")
            elif cmd == CMD_READ:
                try:
                    data = transport.read(addr, cb)
                except OutOfRange:
                    stats["fails"] += 1
                    conn.sendall(PKT.pack(0xFF, 0, addr, 0))
                except Exception as exc:
                    stats["fails"] += 1
                    print(f"[bridge] read {addr:#x}+{cb:#x} failed: {exc}",
                          flush=True)
                    conn.sendall(PKT.pack(0xFF, 0, addr, 0))
                else:
                    stats["reads"] += 1
                    stats["bytes"] += len(data)
                    conn.sendall(PKT.pack(CMD_READ, 0, addr, len(data)) + data)
                now = time.time()
                if now - last_report > 5:
                    last_report = now
                    elapsed = now - stats["t0"]
                    print(f"[bridge] {stats['reads']} reads "
                          f"({stats['bytes'] / (1 << 20):.1f} MiB) "
                          f"+ {stats['fails']} unmapped/fail in "
                          f"{elapsed:.0f}s", flush=True)
            elif cmd == CMD_WRITE:
                leftover = cb
                while leftover:
                    part = conn.recv(min(leftover, 0x10000))
                    if not part:
                        return
                    leftover -= len(part)
                print(f"[bridge] write {addr:#x}+{cb:#x} rejected "
                      f"(not implemented)", flush=True)
                conn.sendall(PKT.pack(0xFE, 0, addr, 0))
            else:
                print(f"[bridge] unknown cmd {cmd} from {peer}", flush=True)
                break
    except ConnectionError:
        pass
    finally:
        elapsed = time.time() - stats["t0"]
        print(f"[bridge] client {peer} gone: {stats['reads']} reads, "
              f"{stats['bytes'] / (1 << 20):.1f} MiB, {stats['fails']} "
              f"unmapped/fail in {elapsed:.1f}s", flush=True)
        conn.close()


def main():
    transport = Transport()
    LIVE_RANGES[:] = discover_safe_ranges(transport)


    import os
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "memmap.cache")
    if os.path.exists(cache):
        fields = open(cache).read().split()
        remap_start, remap_top = int(fields[0], 0), int(fields[1], 0)
        LIVE_RANGES[:] = [(0x0, 0xC0000000), (remap_start, remap_top)]
        print(f"[bridge] cached remap map: {remap_start:#x}-{remap_top:#x}",
              flush=True)
    else:
        top = discover_remap_top(transport, 0x100000000, 0x440000000)
        with open(cache, "w") as handle:
            handle.write("0x100000000 " + hex(top) + chr(10))
        LIVE_RANGES[:] = [(r[0], top if r[0] == 0x100000000 else r[1])
                          for r in LIVE_RANGES]
    transport.set_firmware_map(LIVE_RANGES)
    print(f"[bridge] CH568 transport ready; safe ranges "
          f"{[(hex(a), hex(b)) for a, b in LIVE_RANGES]}; "
          f"listening on 0.0.0.0:{LISTEN_PORT}", flush=True)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", LISTEN_PORT))
    server.listen(4)
    while True:
        conn, peer = server.accept()
        serve_client(conn, transport, peer)


if __name__ == "__main__":
    main()
