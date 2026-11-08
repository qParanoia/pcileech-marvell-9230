# Option ROM to virtual-console command map

The dump's Option ROM starts at SPI offset `0x20000`. Its `55 AA` header and
`PCIR` structure at `0x2001C` describe one final PC-AT image for vendor
`1B4B`, device `9230`. Both length fields give 66 blocks of 512 bytes
(`0x8400` bytes, ending at `0x28400`), and the image's byte checksum is zero.
This is a legacy BIOS image; the dump does not contain a UEFI Option ROM at
that location. The in-memory stripped-runtime test in
`docs/basic-ahci-target.md` does not establish whether this card will boot
from an attached drive on a legacy BIOS without the ROM.

This map comes from the local 88SE9230 SPI dump's x86 Option ROM and the
stock ARM packet handler in the IDA database. Offsets are relative to the
extracted `build/option-rom.bin`. It describes requests the ROM can build;
it does not establish their exact runtime order on the owner's motherboard.

| ROM offset | CDB | Transfer | Management payload | Purpose seen in stock handler |
| --- | --- | ---: | --- | --- |
| `0x4BFF` | `1D` | 62 | `E1 10 09 00` at byte 8 | BIOS version notification |
| `0x4CBD` | `1D` | 99 | `FD` at byte 8, `A4` at `0x3C` | Transfer BIOS time |
| `0x4DA3` | `1D` | 62 | `E1 10 07 00` | UI host-address/control path |
| `0x4ED8` | `1D` | 591 | `F3 03` at byte 8 | RAID management exchange |
| `0x4F41` | `1C` | 591 | CDB byte 2 `E1` | Read saved management response |
| `0x50E8` | `1D` | 62 | `E1 10 06 00` | BGA/host-memory configuration |
| `0x5177` | `1D` | 62 | `E1 10 03`, dynamic flags/address | Enter BIOS UI |
| `0x5293` | `1D` | 62 | `E1 10 01`, dynamic UI fields | Update/query active RAID BIOS UI |
| `0x5338` | `1D` | 62 | `E1 10 01`, dynamic UI fields | Update/query active RAID BIOS UI |
| `0x53D0` | `1D` | 62 | `E1 10 03`, flags masked with `FC` | Release BIOS UI |

The stock `A0` dispatcher recognizes CDBs `00`, `03`, `12`, `1B`, `1C`,
`1D`, `1E`, `46`, and `5A`. Its `1D` branch reads host PRDT data into a
0x1000-byte internal buffer, checks the `E0` marker, invokes the management
dispatcher, and stores an `E1` response. Its `1C` branch returns that
response to the host PRDT. The management dispatcher recognizes `E1`, `F0`,
`F1`, `F2`, `F3`, `F4`, `F7`, `FB`, and `FD`. The `FD/A4` path sets OS time;
`E1/10` calls the BIOS UI callback. Its third byte is an index into an
inlined 8-bit switch table at SPI offset `0x715D4`. The decoded entries are
`01→0x7167E` (update/query existing UI), `03→0x715E0` (enter if the low two
bits of the next byte are nonzero, otherwise release), `06→0x716C2`
(host-memory configuration), `07→0x716E6` (host-address operation),
`08→0x71708`, and `09→0x7174E` (BIOS version notification). Other indices
return the default error `FF`. Earlier notes incorrectly attributed UI entry
to subcommand `01`; that interpretation treated the switch table as ARM
instructions and ignored the relocated `__rt_switch8` target.

The first synthetic run of `03` corrupted the UI resource pointer at
`0x04000234`: the test injected its frontend worker with a stack only about
800 bytes above that global, and a nested `PUSH` overwrote it. A dedicated
synthetic worker stack and an external UI memory window remove that fixture
fault. `python tools/probe_bios_ui.py` now reaches the stock `BIOS UI entered.`
message, returns status `00`, and retires the host slot in Unicorn. This is a
stock-firmware reference run; it does not mean the open CODE1 implements UI.

`python tools/probe_option_rom_sequence.py` exercises nine selected ROM
commands in one stock-firmware Unicorn run: `09`, `FD/A4`, `07`, `F3/03`,
`1C`, `06`, active `03`, active `01`, release `03`. Each command returns an
`E1` response with status `00`; `1C` transfers the preceding 591-byte
`F3/03` response to host memory. The stock UART also reports UI entry and
release. This is a deliberately assembled coverage sequence. The extracted
ROM establishes that these requests can be sent but does not establish their
exact order on the owner's motherboard.

`python tools/compare_option_rom_sequence.py` feeds the same packets to the
open CODE1 in one Unicorn run, preceded by `A1`. It completes all host slots,
and now returns status `00` for all nine. The open code keeps only a minimal
session bit for active UI requests; it does not allocate, display, or operate
the proprietary RAID BIOS UI. Matching status codes do not prove that the
legacy ROM will return to motherboard POST on the owner's PC.

The current open CODE1 implements the `A1` identify response, basic SCSI
responses, the `FD/A4` time transfer, `E1/10/09` version acknowledgement,
the inactive `E1/10/01` query response, `F3/03` physical-disk
enumeration, and the `1C` response. It acknowledges the observed `E1/10`
UI and host-memory requests for basic boot compatibility. Other `F3` modes
and management classes would need separate work for RAID and HyperDuo
compatibility; they are outside the current basic AHCI target.
