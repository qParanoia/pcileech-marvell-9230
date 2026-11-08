# Compatibility inventory for the reference board

The target is observable behavior of the supplied firmware 2.3.0.1041, not
merely the presence of an AHCI device in PCI enumeration. The public Marvell
datasheet describes a 88FR111 Revision 3 Feroceon CPU, a two-lane PCIe 2.0
endpoint, four SATA ports, and hardware RAID 0/1/10. It also lists NCQ, port
multiplier switching, power management and AES. The product brief mentions
HyperDuo. These documents describe chip capabilities; which modes this board
actually enables must be measured.

| Subsystem | Evidence in supplied IDA database | Required observation |
| --- | --- | --- |
| Boot and board setup | `MAGIIMGF` loader at `0xC18C`; version text at SPI `0x2000` | SPI reads, boot log, GPIO straps, resets |
| PCIe / AHCI / IDE | `ahci_host_init` at `0x60914`; source path `platform/frontend/ahci/ahcihost.c` at `0x48C8C`; `ide_host_init` in boot log | PCI config, BAR registers, interrupts, driver discovery in each mode |
| SATA ports / requests | `platform/backend/core/ahci.c` at `0x34788`; port and PMP messages near `0x326F0` and `0x36B20` | Four-port discovery, SATA commands, reset, hot-plug, NCQ, PMP |
| DMA / memory | `platform/frontend/dma/dma.c` at `0x38C78` | Host transfer correctness, scatter/gather, bounds and faults |
| RAID | `platform/backend/raid/tinyraid/ddf.c` at `0x4E6A4`; RAID 0/1/10 UI strings | Disk layout, DDF records, virtual disk identity, degraded and rebuild behavior |
| HyperDuo | HyperDuo and `HYPERDUO_REMAP_SEGMENT` strings near `0x452DC` | Capacity/safe/hybrid modes, on-disk metadata, failure recovery |
| AES | `platform/backend/isolate/aes.c` at `0x586BC`; AES settings strings | Key handling and ciphertext compatibility, only with disposable data |
| Option ROM | `55 AA` signature at SPI `0x20000` | Boot menu, disk presentation, firmware settings and boot paths |

Strings and source paths are evidence that code or diagnostics for a feature
exist; they do not prove the feature is enabled or correct on this particular
board. Where available, IDA cross-references link the strings to functions.

## Acceptance gates

1. **Boot:** achieved for a hybrid test image. A separately flashed SPI chip
   started open ARM code and emitted `OPEN9230` on UART. Replacing the vendor
   autoload, loader, and Option ROM remains future work.
2. **AHCI:** the host sees the same PCI identity and AHCI capability set; each
   physical port can read, write, reset and recover under a standard driver.
3. **RAID:** existing arrays can be discovered read-only before any write is
   attempted. Writes, degraded operation and rebuild require separate tests
   against disposable drives and image-level comparisons.
4. **Remaining modes:** HyperDuo, AES and Option ROM each need their own
   compatibility suite. Passing AHCI tests does not imply these modes work.

## References

- Marvell 88SE9230 datasheet:
  https://www.marvell.com/content/dam/marvell/en/public-collateral/storage/marvell-storage-88se9230-datasheet-2018-08.pdf
- Marvell 88SE92xx product brief:
  https://www.marvell.com/content/dam/marvell/en/public-collateral/storage/marvell-storage-88se92xx-product-brief-2011-12.pdf
