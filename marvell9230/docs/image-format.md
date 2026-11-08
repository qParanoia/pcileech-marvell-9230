# Observed SPI image layout

Reference: `../88.bin`, SHA-256
`dd2ab739e4776d4687a1c067e2a85f17c39a3a6d96fb1ee711221560e989694f`,
524288 bytes. The matching IDA database contains ARM loader code at SPI offset
`0xC000`. The observations below apply to this image; they are not yet a complete
vendor format specification.

| SPI offset | Observed content |
| --- | --- |
| `0x00000` | Autoload records, beginning with `A5 A5 A5 A5` |
| `0x01000` | PCI vendor/device configuration text |
| `0x02000` | Version and section manifest |
| `0x0C000` | ARM loader |
| `0x20000` | PCI Option ROM, beginning with `55 AA` |
| `0x30000` | `MAGIIMGF` firmware container |

The manifest reports autoload `200015`, loader `21001004`, BIOS `1.0.0.1012`,
and firmware `2.3.0.1041`.

## Firmware container

Disassembly of loader function `sub_C18C` in the supplied IDA database shows
that it looks for `MAGIIMGF` in SPI space mapped from `0xF8064000`. It reads
the segment count at container offset `+0x18`, descriptor stride at `+0x1C`,
and descriptor table relative offset at `+0x20`. For each descriptor it reads
the destination at `+0x10`, size at `+0x14`, and source offset at `+0x18`; the
source offset is relative to the container start. The copy loop rounds each
segment size up to a multiple of 8, then moves pairs of ARM registers (8 bytes
per iteration). Segment 0 has a declared size of `0x15AA4`, so the loader
actually copies `0x15AA8` bytes: its four SPI padding bytes at `0x45B64`–
`0x45B67` are `FF FF FF FF`. The offline stripped-runtime fixture clears these
padding bytes as well as the unused stock code. At `0xC044` the loader calls
this copy routine; at `0xC048` it sets PC to `0`, entering the first loaded segment.
Other header fields, checksums, and validation rules remain unverified.
The patched `probe.bin` booted on the board without changing any header fields,
which shows that the initial loader handoff accepts a modified CODE1 prefix.
`python tools/emulate_loader_copy.py ../88.bin` executes the stock loader's
segment-copy function in Unicorn and checks all four RAM destinations against
their SPI sources. The same check passes the already delivered V13 image and
an in-memory image with the unused stock runtime sections zeroed. This
isolates the copy routine; it does not emulate the boot ROM or motherboard.

| Segment | SPI source | Length | RAM destination | Observed tag |
| --- | ---: | ---: | ---: | --- |
| 0 | `0x300C0` | `0x15AA4` | `0x00000000` | `CODE1_HDR` |
| 1 | `0x45B70` | `0x20020` | `0x30040000` | `CODE2_HDR` |
| 2 | `0x65B90` | `0x0C680` | `0x30073000` | `CODE3_HDR` |
| 3 | `0x72210` | `0x00368` | `0x04000000` | `DATA1_HDR` |

The lengths and destinations above are directly parsed from the dump. The
`CODE*`/`DATA*` names are tag bytes in the descriptors, not inferred names for
functions. These are **load addresses**; the exact CPU memory mapping and any
relocation performed later still need hardware confirmation.

## Next measurements on the reference board

1. Read SPI at least twice and compare full hashes. Save the original chip.
2. Record PCI configuration space, BARs, firmware boot log and register state
   for every selectable controller mode.
3. Record behavior for each physical port with a sacrificial drive. Capture
   error, hot-plug, reset, suspend, and resume cases.
4. Record RAID metadata and rebuild behavior on sacrificial drives before
   implementing compatibility. A clean boot alone cannot establish RAID data
   compatibility.
