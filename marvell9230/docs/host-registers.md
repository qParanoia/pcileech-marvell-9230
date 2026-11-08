# Host and backend register windows

These addresses come from stock-code disassembly and a Unicorn trace of the
no-disk boot path. The trace uses a synthetic MMIO fixture, so returned values
are inputs to the model unless independently measured on the board. The
owner's UART log confirms the resulting port counts and console mapping.

| CPU address | Stock-code use | Evidence |
| --- | --- | --- |
| `0x80002800` | low five bits plus one give host virtual-slot count | `sub_60624` at IDA `0x606C0`–`0x606D4` |
| `0x80002900 + 0x80*i` | host-visible per-slot register block | `sub_60624` at `0x60764`–`0x60770`; trace reads slots 0–7 |
| `0x80003010 + 8*i` | per-slot register pair used in host setup | `sub_60624` at `0x60774`–`0x60780`, `0x60870`–`0x60894` |
| `0x8000A800` | low five bits plus one give physical backend-port count | routine at RAM `0x00003E60`; `sub_60174` at `0x60248`–`0x60268` |
| `0x8000A80C` | physical backend-port bitmap | routine at RAM `0x00003E58`; `sub_60174` at `0x601F8`–`0x60210` |
| `0x8000A808` | global backend interrupt status; bit 0 leads to physical port 0 in the synthetic completion path | RAM `0x000060D4` / IDA `sub_36194`; controlled IRQ fixture |
| `0x8000A900 + 0x80*i` | backend port register block, `i=0..3` in model | routine at RAM `0x00003EB8` onward; trace writes four blocks |
| `0x8000A910` | port-0 interrupt status (backend register block + `0x10`) | `sub_36194` reads and acknowledges it on IRQ0 |
| `0x8000A924` / `0x8000A928` | port-0 signature / link-status words | `sub_35BA0` and `sub_340A4`; SSD-path trace |
| `0x8000A938` | port-0 command-issue word; bit 0 is polled for internal command completion | SSD-path trace at RAM PCs `0x00006538` and `0x00004BAC` |
| `0x30003000 + 0x40*i` | another per-host-slot window | `sub_60624` at `0x607DC`–`0x607F4` |

The fixture uses `0x80002800=7` for eight host slots,
`0x8000A800=3` for four physical ports, and `0x8000A80C=0xF` as their
bitmap. With those inputs, stock code prints `Core allocated 26624 bytes.`
(`4 * 0x1A00`) and places the console on virtual port 7. The firmware's
reported four physical SATA ports and `port 7 Auto-fetch enable` are thus
consistent with separate backend and frontend counts. Exact power-on values
of these three registers have **not** been directly read from the board.

The trace is suitable for finding initialization order and candidate register
semantics. It is not a write sequence that can safely be replayed as a new
driver: zero-filled unknown registers can change control flow. The optional
SSD fixture injects successful SATA completion interrupts, but it does not
model real controller timing, PCIe transactions, RAID behavior, or SATA error
states.

The one-SSD path and its current completion gap are documented in
[ssd-emulation.md](ssd-emulation.md).

## Stock host initialization trace in Unicorn

The reference image reaches its host initialization code at RAM
`0x3005ABxx` in the no-disk fixture. It reads `0x80002800=7` (eight virtual
slots) and then writes `0x80003008=0xFFFFFFFF`, `0x8000300C=2`. It writes
`0xFFFFFFFF` and `0x0000104F` to each eight-byte pair starting at
`0x80003010` through `0x80003048`. For the first host slot it writes, among
other words, `0x80002918=0x00140006`, `0x80002920=0x7F`,
`0x80002930=0x00010000`, then `0x80002910=0x80400000`. These are **observed
writes in a synthetic no-disk run**. They are not yet a validated standalone
initialization sequence: called routines set up other state, and the host
driver's PCIe behavior is not modeled.

The v6 read-only [host probe](uart-monitor.md) is designed to measure selected
registers after the open stage has set up PUNIT and backend SATA but before
any open host initialization. Its physical run remains unverified. Comparing
a future snapshot with the stock trace may identify registers that need
explicit setup.

The separate [host-control study](host-control.md) maps the stock frontend
IRQ bit, host mode transitions, and reset branch using only static analysis
and Unicorn. It does not require the host probe or a board run.

## PUNIT PCIe CPU-window mapper

Stock CODE1 function `sub_318F0` in the raw IDA database (runtime `0x00001830`)
maps a 64-bit host range into one of two CPU windows. Its arguments are the
host low word, host high word, requested byte count, and window index. Window
zero uses CPU address `0x40000000` and registers at `0xD0020000`; nonzero
indices use `0x50000000` and advance the register block by `0x10` bytes.

The function begins with a 64-KiB mask. If `(low & mask) + size` crosses the
window boundary, it grows the mask to 128 KiB, 256 KiB, and so on. It writes
the CPU base at `+4`, the aligned host low word at `+8`, the high word at
`+0xC`, and `0x5923 | (size_code << 16)` to the control word. The returned
pointer is the CPU base ORed with the offset inside the selected mask.

The open PUNIT helper now follows this sizing algorithm instead of assuming a
fixed 64-KiB window. This matters when a small command structure or response
straddles a 64-KiB host-address boundary. The behavior is derived from stock
disassembly; PCIe ordering and bridge timing still require hardware evidence.
