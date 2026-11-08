
"""PCI-ESP service: exposes target process memory over TCP via the DMA chain.

Companion to FamilyEspPci (C#).  Speaks line commands, binary responses:

  F <name>                 find process by name      -> "<pid>\n" or "0\n"
  M <pid>                  module list               -> u32 count, then per
                                                      module: u32 nameLen,
                                                      name, u64 base, u64 size
  H <pid>                  committed private RW maps -> u32 count, then per
                                                      region: u64 base, u64 sz
  R <pid> <addr> <size>    process read              -> u32 len, then bytes
                                                      (len 0 on failure)

Requires the bridge (ch568_leechbridge.py) to be running first.
"""
import socket
import struct
import sys
import threading

sys.path.insert(0, r"<home>\Desktop\pcileech\bin")
import vmmpyc

LISTEN_PORT = 8890


class Service:
    def __init__(self):
        self.vmm = None
        self.lock = threading.Lock()
        self.processes = {}

    def ensure_vmm(self):
        with self.lock:
            if self.vmm is None:
                self.vmm = vmmpyc.Vmm(
                    ['-device', 'rawtcp://127.0.0.1:8888', '-waitinitialize'])
                print("[pciserv] vmm initialized", flush=True)
            return self.vmm

    def process(self, pid):
        with self.lock:
            if pid not in self.processes:
                self.processes[pid] = self.vmm.process(pid)
            return self.processes[pid]

    def cmd_find(self, name):
        for p in self.ensure_vmm().process_list():
            try:
                if p.name.lower().rstrip('.exe') == name.lower().rstrip('.exe'):
                    return str(p.pid).encode()
            except Exception:
                continue
        return b"0"

    def cmd_modules(self, pid):
        out = bytearray()
        mods = self.process(pid).module_list()
        entries = []
        print(f"[pciserv] module_list -> {len(mods)} entries; "
              f"attrs: {[a for a in dir(mods[0]) if not a.startswith('_')][:14]}"
              if mods else "[pciserv] module_list empty!", flush=True)
        for m in mods:
            try:
                name = getattr(m, 'name', None) or getattr(m, 'uszText', '')
                base = getattr(m, 'base', None) or getattr(m, 'va', 0)
                size = getattr(m, 'image_size', None) or getattr(m, 'size', 0)
                entries.append((str(name).encode(), int(base), int(size)))
            except Exception as exc:
                print(f"[pciserv] module entry error: {exc}", flush=True)
                continue
        out += struct.pack("<I", len(entries))
        for name, base, size in entries:
            out += struct.pack("<I", len(name)) + name
            out += struct.pack("<QQ", base, size)
        return bytes(out)

    def cmd_maps(self, pid):
        out = bytearray()
        regions = []
        try:
            raw = self.process(pid).maps.maps()
        except Exception:
            raw = []
        for entry in raw:
            if isinstance(entry, dict):
                va = entry.get('va', 0)
                size = entry.get('size', 0)
                info = str(entry.get('info', ''))
            else:
                continue
            if not (0x10000 <= va < 0x7FFFFFFFFFFF) or size < 0x10000:
                continue

            if 'w' not in info.lower():
                continue
            if '-' in info and 'rw' not in info.replace('-', ''):
                continue
            regions.append((va, size))
        out += struct.pack("<I", len(regions))
        for va, size in regions:
            out += struct.pack("<QQ", va, size)
        return bytes(out)

    def cmd_read(self, pid, addr, size):
        try:
            data = self.process(pid).memory.read(addr, size)
            return struct.pack("<I", len(data)) + data
        except Exception:
            return struct.pack("<I", 0)

    def handle(self, conn):
        buf = b""
        try:
            while True:
                part = conn.recv(65536)
                if not part:
                    return
                buf += part
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    args = line.decode("ascii", errors="replace").split()
                    if not args:
                        continue
                    cmd, rest = args[0].upper(), args[1:]
                    if cmd == "F":
                        conn.sendall(self.cmd_find(rest[0]) + b"\n")
                    elif cmd == "M":
                        conn.sendall(self.cmd_modules(int(rest[0])))
                    elif cmd == "H":
                        conn.sendall(self.cmd_maps(int(rest[0])))
                    elif cmd == "R":
                        pid, addr, size = map(lambda x: int(x, 0), rest)
                        conn.sendall(self.cmd_read(pid, addr, size))
                    else:
                        conn.sendall(b"\n")
        except ConnectionError:
            pass
        finally:
            conn.close()


def main():
    service = Service()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", LISTEN_PORT))
    server.listen(8)
    print(f"[pciserv] listening on 127.0.0.1:{LISTEN_PORT}", flush=True)
    while True:
        conn, peer = server.accept()
        threading.Thread(target=service.handle, args=(conn,),
                         daemon=True).start()


if __name__ == "__main__":
    main()
