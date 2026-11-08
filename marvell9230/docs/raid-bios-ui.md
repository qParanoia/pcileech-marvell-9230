# RAID BIOS UI: stock behavior and open implementation gap

The source of truth is the local `88.bin` and its IDA database. Runtime
addresses below use the loaded CODE3 base `0x30073000`; the corresponding IDA
address of the main callback is `0x715B0`.

## Stock dispatch

The CODE2 management dispatcher reads its `E1/10` callback from DTCM
`0x04000248`. In the stock boot this points to CODE3 runtime `0x3007EA21`
(Thumb entry, function body at `0x3007EA20`). The callback dispatches byte 10
of the 62-byte request through the inline `__rt_switch8` table at SPI offset
`0x715D4`:

| Subcommand | Stock action |
| --- | --- |
| `01` | Update/query an existing UI; returns `FF` before entry and `00` after entry. |
| `03` | Enter UI if `(request[11] & 3) != 0`; otherwise release it. |
| `06` | Configure the BGA buffer in host memory. |
| `07` | Set the BIOS UI host address. |
| `08` | Query/write additional UI information; still to characterize. |
| `09` | Record the Option ROM version and print it on UART. |

On entry, CODE3 stores the host address from request bytes `12..15` at
`0x3007F650`, sets up the UI context under `0x3007F648`, initializes resources,
and prints `BIOS UI entered.`. The stock resource base is `0x3005C040` in the
one-SSD Unicorn fixture (`0x04000234`). Release prints
`To release ui memory 30073000 50816 bytes` and returns the BGA buffer to
SRAM. The synthetic run uses a separate frontend worker stack to avoid
overwriting `0x04000234`; its UI display window includes `0x4001C000`.

The sequence snapshots give these first words of the state at
`0x3007F648`:

| After request | `+0` | `+4` | `+8` | `+C` | `+10` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `07` | `0` | `1` | `0` | `0` | `0` |
| `06` | `000A0000` | `1` | `0` | `0` | `0` |
| active `03` | `000A0000` | `1` | `0009C000` | `3007F654` | `300654A4` |
| active `01` | `000A0000` | `1` | `0009C000` | `3007F654` | `300654A4` |
| release `03` | `0` | `1` | `0009C000` | `3007F654` | `300654A4` |

These are observations from one synthetic request sequence, not general
constants for every board or firmware configuration.

`python tools/probe_option_rom_sequence.py` checks a nine-command synthetic
sequence against stock code, including `F3/03` followed by `1C`, UI entry,
update, and release. All nine return status `00` and retire their host slot.
`python tools/compare_option_rom_sequence.py` sends the same sequence through
the open CODE1. It completes the slots with status `00`, using a minimal UI
session bit to support the basic AHCI boot path. The open stage has no UI
resource allocator, renderer, or RAID management effects.

## Implementation boundary

The current open image keeps the stock Option ROM, CODE2, and CODE3 in the
SPI container for research but replaces CODE1. The stock UI callback depends
on boot-time state and services normally initialized by stock CODE1. A
successful status byte alone cannot provide the RAID menu or preserve its
management actions. Those features are outside the current basic AHCI target;
the matching statuses only test that the observed legacy ROM requests retire.
