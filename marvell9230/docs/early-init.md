# Early stock-firmware initialization

These observations come from disassembly of the supplied IDA database. They
describe register accesses and call arguments, not proven register semantics.
The open diagnostic reads only the previously used identity, strap and SPI
addresses; it does not run these initialization routines.

## Interrupt initialization

`sub_5FCCC` prints `Interrupt initialization.`. It clears RAM word
`0x040002AC`, zeroes `0x80` bytes at `0x040002B0` via `sub_46258`, clears registers
`0xD0020204` and `0xD0020208`, then writes `0xFFFFFFFF` to `0xD0020200`.
The purpose of the `0xD00202xx` registers remains to be established.

## PUNIT initialization

`sub_5FD30` prints `PUNIT initialization.`. It writes to the `0xD0020000`
register block at offsets `0`, `0x10`, `0x110`, `0x114`, `0x300`, `0x310`,
`0x314`, `0x318`, and `0x31C`. It sets bits 0–3 of offset `0x300` in two
steps, and calls `sub_4809C(0x04000330, 0x20000, 0x00001780)`.
Disassembly of `sub_4809C` shows it stores the mask and callback address
into the structure at its first argument and enables the mask in
`0xD0020204`; this is interrupt registration, not a memory copy. Later the
routine accesses `0xD0071058`, `0xD0071028`, and `0xD0071024`. The exact
hardware meanings of these registers and the callback remain unknown.

IDA disassembly at `0x5FD30` gives the ordered writes below. The `0x300`
register is read between its writes, so these are register observations,
not a proven recipe for safely restarting an already initialized PUNIT.

| Address | Written value or operation |
| --- | --- |
| `0x80003818` | `0` |
| `0xD0020114` | `0`, then later `4` |
| `0xD0020110` | `0xF` |
| `0xD0020300` | `0`, then OR `3`, then OR `0xC` |
| `0xD0020000`, `0xD0020010` | `0` |
| `0xD0020310`, `0xD0020314` | `0xFFFFFFFF` |
| `0xD0020318`, `0xD002031C` | `0x01C9C380` |
| `0xD0071058` | preserve bits 15–31, set low 15 bits to `0x5B6D` |
| `0xD0071028`, `0xD0071024` | `0xFFFFFFFF` |

The independent C stage now reads the PUNIT control words and all four SATA
port statuses in a single UART report. Those values will show whether the
SPI loader has already configured any part of PUNIT before CODE1 runs.

## Scratchpad RAM

`sub_5FE08` gets `0x30060280` from `sub_48168` and computes the available
length to `0x30080000`: `0x1FD80` bytes (130432), matching the owner's
stock UART log. It stores the start at `0x04000044`, then calls
`sub_47F30(0x30060280, 0x1FD80)` to initialize the heap.

## Device ID and revision

`sub_5FB28` reads `0xD0030000` and shifts the word right by 16 to get the
device ID. It separately reads one byte from `0x04000028` for the revision
printed in `Magni device id: %04X, rev: %02X`. The owner's stock log reports
ID `9230` and revision `61` in hexadecimal formatting. The earlier boot
routine at RAM `0x00000C48` fills that RAM byte by reading `0xD0030008`,
adding `0x50`, and keeping the low byte. The observed revision therefore
implies a low byte of `0x11` in the register, pending direct measurement.

## AHCI host setup and the `early post spd` log

`sub_60624` prints `ahci_host_init.`. Before printing `Gigabyte early post
spd: %02X`, it reads words at `0x8000A928` and `0x8000A9A8`, masks each
with `0xF0`, and prints the maximum of those results and `0x20`.
Consequently the log values `20` and `30` reflect this register calculation;
their physical meaning and reason for varying between the two captures still
need measurement.

The same routine reads the low five bits of the word at `0x80002800`, adds
one, and compares that count with a per-device value looked up after reading
the ID at `0xD0030000`. It allocates per-port structures and uses a
`0x30003000` register window with a `0x40` stride. These addresses are
candidate targets for later read-only diagnostics, after the current UART
probe verifies the simpler identity and strap reads on the board.
