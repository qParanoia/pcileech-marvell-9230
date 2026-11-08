"""Probe-free physical memory map discovery for the CH568 bridge.

Walks the System process page tables (kernel half) and collects the highest
physical page referenced by any PTE/PDE.  The kernel maps its PFN database
over all installed RAM, so the maximum referenced PFN equals the top of
usable memory - discovered without ever touching an unmapped address.

All reads stay inside RAM by construction: page tables live in mapped pages,
and the walk never dereferences a data PTE, only collects its target.
"""
import struct
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")
import read_memory_batch as rmb
from read_memory_batch import load_usb_backend

MASK = 0x000FFFFFFFFFF000


class MapWalker:
    def __init__(self):
        import usb.core
        import usb.util
        self.device = usb.core.find(idVendor=0x4348, idProduct=0x5637,
                                    backend=load_usb_backend())
        if self.device is None:
            raise SystemExit("CH568 mailbox 4348:5637 not found")
        self.device.set_configuration()
        usb.util.claim_interface(self.device, 0)
        try:
            import time as _t
            n = 0
            while n < 1024:
                bytes(self.device.read(0x81, 512, timeout=200))
                n += 1
        except Exception:
            pass

    def read(self, base, pages):
        data, _, _ = rmb.read_batch(
            self.device, rmb.make_linear_request(base, pages), pages,
            30, False, 65536, True)
        return data

    def find_dtb(self):
        """Scan low RAM for the System PML4 (kernel half present, user half
        nearly empty, self-consistent upper entries)."""
        for base in range(0x100000, 0x8000000, 0x80 << 12):
            try:
                blob = self.read(base, 128)
            except Exception:
                continue
            for off in range(0, len(blob) - 0x1000, 0x1000):
                page = blob[off:off + 0x1000]
                e_hi = struct.unpack_from("<Q", page, 0xFF8)[0]

                if not ((e_hi & 1) and (e_hi & MASK)):
                    continue
                e_f0 = struct.unpack_from("<Q", page, 0x1F0 * 8)[0]
                e_f1 = struct.unpack_from("<Q", page, 0x1F1 * 8)[0]
                if (e_f0 & 1) and (e_f1 & 1) and (e_f0 & MASK) and (e_f1 & MASK):
                    return base + off, page
        return None, None

    def walk_max_pfn(self, dtb):
        """Collect the max physical page referenced by the kernel-half walk."""
        max_pfn = 0
        tables = 0
        pml4 = self.read(dtb, 1)
        for i4 in range(0x100, 0x200):
            e4 = struct.unpack_from("<Q", pml4, i4 * 8)[0]
            if not (e4 & 1):
                continue
            pdpt = self.read(e4 & MASK, 1)
            tables += 1
            for i3 in range(512):
                e3 = struct.unpack_from("<Q", pdpt, i3 * 8)[0]
                if not (e3 & 1):
                    continue
                if e3 & 0x80:
                    max_pfn = max(max_pfn, ((e3 & 0x000FFFFFC0000000)
                                            >> 12) + (1 << 18) - 1)
                    continue
                pd = self.read(e3 & MASK, 1)
                tables += 1
                for i2 in range(512):
                    e2 = struct.unpack_from("<Q", pd, i2 * 8)[0]
                    if not (e2 & 1):
                        continue
                    if e2 & 0x80:
                        max_pfn = max(max_pfn, ((e2 & 0x000FFFFFFFE00000)
                                                >> 12) + (1 << 9) - 1)
                        continue
                    pt = self.read(e2 & MASK, 1)
                    tables += 1
                    for i1 in range(512):
                        e1 = struct.unpack_from("<Q", pt, i1 * 8)[0]
                        if e1 & 1:
                            pfn = (e1 & MASK) >> 12
                            if pfn > max_pfn:
                                max_pfn = pfn
        return max_pfn, tables


def main():
    walker = MapWalker()
    dtb, _ = walker.find_dtb()
    if dtb is None:
        print("no System DTB found in low 128 MiB")
        return 1
    print(f"System DTB: {dtb:#x}")
    max_pfn, tables = walker.walk_max_pfn(dtb)
    top = (max_pfn + 1) << 12
    print(f"walked {tables} table pages; max referenced PFN {max_pfn:#x}")
    print(f"physical top: {top:#x} ({top / (1 << 30):.2f} GiB)")
    low_top = 0xC0000000
    print(f"map: 0x0-{low_top:#x} + 0x100000000-{top:#x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
