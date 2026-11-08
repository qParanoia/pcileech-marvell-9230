# Early register map from the reference firmware

This is a working map, not a chip programming manual. Addresses are CPU-visible
values observed in the supplied IDA database. Access width and side effects
must be verified on hardware before they are used by replacement code.

| Address | Current interpretation | Evidence |
| --- | --- | --- |
| `0xF8064000` | SPI flash mapping | loader `sub_C18C` at `0xC258` |
| `0xD0030000` | device identity; firmware uses upper 16 bits as device ID | loader `sub_C18C` at `0xC1B8`; `sub_5FB28` at `0x5FB28` |
| `0xD0030008` | boot code adds `0x50` to its low byte to form printed revision | early code at RAM `0x00000C64`–`0x00000C70` |
| `0x04000028` | RAM byte printed as chip revision | `sub_5FB28` at `0x5FB44` |
| `0xD0020200` | early interrupt-controller register, written `0xFFFFFFFF` | `sub_5FCCC` at `0x5FD04` |
| `0xD0020204`, `0xD0020208` | early interrupt-controller registers, cleared | `sub_5FCCC` at `0x5FCF8` |
| `0xD0020000` | base used by stock PUNIT initialization | `sub_5FD30` at `0x5FD4C` |
| `0xD0071054` | GPIO strap/configuration snapshot | serial init `sub_5FF58` at `0x5FF66`; Habr hardware experiment |
| `0xD0072000` | UART channel 0 register base | `sub_5FF58` at `0x5FF7E` |
| `0xD0072100` | UART channel 1 register base | `sub_5FF58` at `0x5FF88` |
| `0x04000048` | RAM location storing UART base pointers | `sub_5FF34` at `0x5FF34` |
| `0x04000050` | RAM flag set when serial init finishes | `sub_5FF58` at `0x5FF92` |

`sub_5FF58` checks bits 4–5 of the value read from `0xD0071054` and initializes
the UARTs only when that field equals 2. It calls `sub_5FF34` with divisor
`0xA2`. That routine writes UART offsets `+4` (interrupt enable / divisor MSB),
`+0xC` (line control), `+0` (divisor LSB), and `+8` (FIFO control). The final
line-control value is `3` and FIFO-control value is `7`. The Habr article
reports that changing the GPIO4 strap at power-up changes this mode and enables
UART on TST0/TST1 at 115200 baud. A software write alone did not enable the
pins on the author's board.

The loader's `0x04004000` stack pointer and its DATA1 segment at `0x04000000`
show usable RAM in this region during boot. The probe uses `0x04001000` as a
temporary marker; it has not been read back on the actual board.

The separate [host register window map](host-registers.md) covers the
`0x8000xxxx` frontend and backend addresses inferred from boot disassembly
and the offline MMIO trace.

Source: https://habr.com/ru/articles/532672/
