# Host AHCI control path: static analysis and offline emulation

This note separates the controller's host-facing control path from the
physical SATA backend. All new runs here execute the supplied stock `88.bin`
in Unicorn; no new board image or hardware test is involved.

## IRQ dispatch

The reference image registers global IRQ bit 8 for the frontend handler at
RAM `0x00008020` (IDA `sub_380E0`). This handler checks the host status word
at `0x80002808` against an enabled mask of `2`, acknowledges the observed
bits, and calls IDA `sub_3781C`. The same callback also processes global
IRQ bits 9–16 as virtual-port events. Global IRQ bit 0 belongs to the
physical SATA backend; the frontend and backend are distinct paths.

`sub_3781C` reads the host-control word at `0x80002804` and branches on two
bits:

| Host-control input | Observed stock behavior in the synthetic event |
| --- | --- |
| bit 0 set (`0x00000001`) | Reinitializes virtual-port software state, logs `AHCI host reset started.` and `AHCI host reset done.`, then clears host control. |
| bit 31 set, bit 0 clear (`0x80000000`) | Enables AHCI mode if not already enabled; logs `AHCI mode enabled by host.` and releases IDE resources. |
| both bits clear (`0x00000000`) | Logs `AHCI mode disabled by host.` and clears the mode flag. |

The function tests reset first, so `0x80000001` follows the reset branch.
The reset branch calls other routines and writes multiple frontend port
registers; the table above is a control-flow summary, not a complete host
reset specification. In particular, a fabricated `0x80002808=2` and injected
IRQ bit 8 are inputs to the emulator, not measurements of PCIe traffic.

Reproduce these branches offline:

```text
python tools/compare_host_control.py ../88.bin
```

The comparison checks the IRQ vector, the expected UART lines, and the final
clear of the host-control register in the reset case. Its inputs are derived
from the IDA disassembly at `0x380E0` and `0x3781C`. It also injects the
disable → enable → reset sequence in one emulated boot and obtains the same
five control lines, in order, that appear in the owner's stock one-disk UART
capture. This extends the stock emulator beyond the boot prefix without
another SPI flash. The OS time and Option ROM lines still need a host PCIe
transaction model and are outside this synthetic sequence.

## Host initialization context

IDA `sub_60624` reads the low five bits of `0x80002800`, adds one, allocates
virtual-port state, and initializes a bank at `0x80003008` plus eight-byte
slot pairs. Separate frontend routines initialize per-port registers in
`0x80002900 + 0x80*i`. The no-disk Unicorn trace reaches four frontend
ports with modeled 1, 2, or 4 host slots, and seven with modeled eight slots;
the eighth virtual port is the console mapping in this fixture. This is a
fixture result, not proof of physical host-port availability.

The next open implementation milestone is a frontend dispatcher that handles
host reset, mode switching, and per-port requests while preserving the
physical backend's independent command path. The current C stage has none of
that host-visible behavior. Synthetic register writes can validate branch
selection and register effects, but PCIe enumeration, DMA, OS driver
interactions, and compatibility with real arrays remain unverified offline.

## Virtual-port register events and auto-fetch

The same frontend callback at IDA `sub_380E0` treats global IRQ bit 9 as
virtual-port 0. It reads a port status word at `0x80003010`, acknowledges the
observed bits, and dispatches based on a mask set to `0x104F` during host
initialization. Independent synthetic events in Unicorn give this map:

| Port status bit | Register words read by stock code |
| --- | --- |
| `0x0001` or `0x0002` | command-list base `0x80002900` and `0x80002904` |
| `0x0004` or `0x0008` | received-FIS base `0x80002908` and `0x8000290C` |
| `0x0040` | port command/control `0x80002918` |
| `0x1000` | SATA status `0x8000292C` |

Reproduce the mapping with `python tools/compare_host_port_irq.py ../88.bin`.
These injected events are read/acknowledgment probes; they do not contain a
host command table or move disk data.

IDA `sub_384F8` prints `port %d Auto-fetch enable` and calls `sub_38C28`.
That helper sets bit `port+4` in the word at `0x8000C044` in this run; the
stock no-disk trace ends with `0x0000080D` after enabling console virtual
port 7. This suggests a hardware-assisted fetch path for host requests, so
the software port IRQ mapping above is insufficient to implement host I/O.
The exact descriptor format and PCIe memory translation are still open.

## Frontend DMA submission and completion

The stock image registers global IRQ bits 2 and 3 with the same frontend DMA
handler, IDA `sub_38D40` (runtime `0x00008C80`). Its status word is
`0x8000C040`: bit 0 processes completions, bit 2 reports a parity error,
and bit 3 reports an unsupported-request error. The handler acknowledges the
observed status by writing it back to that address. Synthetic IRQs reproduce
each UART diagnostic; see `python tools/compare_dma_irq.py ../88.bin`.

The DMA context root at RAM `0x040054FC` points to `0x8000B700` in this
fixture. IDA `sub_389D4` allocates one of eight software tags from a bitmap
at `0x04005500`; two 16-byte records per tag start at `0x30060F50` and
`0x30060FD8`. IDA `sub_4011C` fills these records and `sub_38AB0` pushes
the tag into the nine-entry submission ring at `0x30060EF4`, then writes its
producer index to `0x8000C01C`. The ring index wraps after 8.

On completion, IDA `sub_38B18` reads the hardware producer index at
`0x8000C030`. It consumes completion words through a separate ring whose
first entry is at `0x30060F24`, extracts a tag from bits 0–12, and looks up
the associated software context at `0x0400551C + 4*tag`. The context's byte
at offset 1 becomes `0x02` for success or `0x81` when completion bit 18 is
set. The context slot is cleared and an optional callback is invoked. The
offline comparison injects one success, one error, and two consecutive
completions across the ring's wrap point; all reach those stock-code effects.

These runs construct completion words and contexts directly in emulated RAM.
They establish the firmware's bookkeeping and IRQ path. They do not establish
the PCIe address format, actual host DMA transfers, command-table fetch, or
coherency rules. Implementing a host-visible disk requires those missing
pieces as well as the physical SATA backend.

## Command-list fetch boundary

IDA `sub_37B20` is the frontend worker behind a function pointer installed
by `sub_60624`. It checks a per-port command-issue shadow through
`sub_38C48`, which reads `0x8000C060 + 4*port` in this fixture. For each
new issue bit, it walks 32 command headers spaced 32 bytes apart, extracting
the command-table base from header offsets 8 and 12 and aligning the low
address to 64 bytes.

There are two paths to the command headers. If a flag at the virtual-port
context's offset `0x70` has bit `0x20` set, the worker uses SRAM at
`0x30000000 + port*0x400`. The stock `Auto-fetch enable` function sets that
bit for mapped ports, including port 0 in the one-SSD fixture. This is the
normal hardware-assisted path in that run. Otherwise, the worker calls
`sub_4011C` with the host command-list base pair and a `0x400`-byte local
buffer at `0x30055780`, then processes that copy. Thus the direct DMA
submission is a fallback, not the normal path for the owner's mapped port.

The Unicorn fixture does not schedule the frontend worker automatically
after a synthetic host port command. A deliberately invoked worker does read
the injected command-issue shadow and updates its internal issued mask, but
the SRAM auto-fetch window remains empty because that hardware action is not
modeled. The completion-ring comparison above bypasses this gap by placing
completion records directly in emulated RAM.

`python tools/compare_autofetch_worker.py ../88.bin` reproduces this
boundary: after a modeled SSD mapping, host enable/reset, and port event,
it invokes the stock worker once. The worker reads command issue `1`, takes
the auto-fetch branch, and records issued mask `1`; the SRAM header window
is still empty in the first fixture. A second run places a synthetic 32-byte
AHCI header in that SRAM window. The stock worker copies its flags
`0x00010005` and command-table base `0x30002000` into an internal command
object and points to the header at `0x30000010`. This verifies header parsing,
not a host-memory fetch, FIS decode, or disk command. Invoking the worker
directly is an emulator aid, not evidence that its scheduler timing has been
reproduced.

The fixture can now keep a command list in separate synthetic host memory at
64-bit CLB `0x0000000110000000`. When CI is posted, a narrowly scoped
auto-fetch model copies its 1 KiB into the port-0 SRAM window. The stock IRQ
handler reads both CLB words, and the worker creates the same command object
as in the direct-SRAM run. This checks the software side of the transfer; the
actual PCIe address translation and timing are still assumptions of the
fixture.

IDA `sub_31E2C` then reads the ATA command byte from the worker's local
pointer `0x30000010 + 2` when the command has the auto-fetch flag. A further
fixture supplies the first 16 bytes of a synthetic command-table Register
Host-to-Device FIS at that SRAM position. The stock callback decodes `0xEC`
(IDENTIFY DEVICE) and enqueues the resulting request through the stock list
insertion helper at IDA `sub_33748`. The 16-byte placement
is a **hypothesis about the hardware prefetch format** derived from this
software read, not a measured PCIe transfer. The full command table and
hardware prefetch timing are still unverified.

## Backend dispatch of a host command

`python tools/compare_backend_dispatch.py ../88.bin` continues the same
synthetic host IDENTIFY request. The host callback inserts it into the
intrusive request list at `0x04000060`. The backend task queue at
`0x04003690` holds a task whose callback is IDA `sub_33D24` (runtime
`0x3C64`). The Unicorn fixture explicitly invokes the stock task-drain helper
IDA `sub_38EB8` (runtime `0x8DF8`) after the frontend worker returns. The
stock callback removes the host request from the list, reaches physical
backend command preparation (runtime `0x4844`), and issues ATA `0xEC` through
the physical SATA command path (runtime `0x4BAC`, slot 0). Both task and
request lists are empty after dispatch. This is software-path evidence; the
manual task-drain call is a scheduler fixture.

The physical command uses the same 64-bit command-table address as the
synthetic host header, with low address flag bits added by the stock code.
The fixture now includes a standard one-entry AHCI PRDT at table offset
`0x80`, pointing to a separate 512-byte host buffer above 4 GiB. It models
the SATA data transfer by placing a synthetic IDENTIFY sector in that buffer.
This data movement is **emulator behavior**, not evidence that the Marvell
bridge uses standard PRDT DMA without additional translation.

The synthetic physical completion must clear both the slot bit in physical
`PxCI` (`0x8000A938`) and `PxSACT` (`0x8000A934`). With only `PxCI` cleared,
IDA `sub_36194` calls its retirement helper with a zero slot mask and the
host request remains pending. With both cleared, the stock code retires the
request through IDA `sub_342E4`, invokes the host completion callback
(runtime `0x88B4`), and the front thread runs the completion consumer
(runtime `0x854C`). The consumer writes `0xFFFFFFFE` to virtual-port
`PxCI` at `0x80002938`, `0x8` to virtual-port `PxIS` at `0x80002910`, and
`1` to frontend interrupt register `0x8000C084`. These are measured
software writes in Unicorn. The fixture treats MMIO as plain RAM, so it does
not establish the resulting hardware readback, host interrupt delivery, or
correct PCIe DMA. The input command-issue shadow `0x8000C060` retaining
`1` is not the virtual-port `PxCI` readback.

## First open command-descriptor component

`firmware/host_command.c` builds a physical 64-byte SATA slot from the
32-byte command-header/FIS prefix used in the stock auto-fetch path. For the
validated `IDENTIFY DEVICE` case it keeps the AHCI flags and 64-bit CTBA,
adds low CTBA bit 2 for a host-bus table, and copies the first 16 FIS bytes
into the slot. It rejects unsupported opcodes and malformed headers before
touching the output. `python tools/compare_open_host_descriptor.py ../88.bin`
compiles this C function for ARM, executes it in Unicorn, and compares all
64 output bytes with the stock backend slot from the same synthetic command.
The default v6 stage does not call this function. An opt-in experimental build
does, as described below. Real data DMA remains unverified.

## Opt-in open frontend experiment

`firmware/host_frontend.c` now has two small components. Its IRQ setup emits
the same 18 MMIO writes as the stock frontend initialization for eight virtual
ports in the Unicorn fixture. `python tools/compare_open_frontend_init.py
../88.bin` compares the ordered writes, including the cap for an invalid
reported port count. The same comparison checks 18 ordered DMA register
writes and the auto-fetch enable bit for console port 7. Enabling port 0
then port 7 produces `0x1D` then `0x81D` at `0x8000C044`, matching the
one-SSD stock trace.

The `OPEN9230_EXPERIMENTAL_FRONTEND` build enables a slot-0 IDENTIFY poller
only when its UART monitor receives `F` after the physical SATA diagnostics.
It reads a 32-byte header/FIS
prefix from the assumed hardware prefetch window at `0x30000000`, validates
it, constructs the backend slot at `0x3006B000`, and issues physical port-0
slot 0. On physical completion it writes the three virtual-port completion
registers observed in the stock code. It handles one outstanding IDENTIFY
request and rejects unsupported opcodes. It is compiled by the offline test,
not enabled by the default `build_c_stage.py` image.

`python tools/emulate_open_frontend.py ../88.bin` starts with an empty SRAM
prefetch window and seeds a 64-bit host command-list base, command list,
command table, and PRDT in the emulator. When the open stage writes the
port-0 auto-fetch bit, the synthetic hardware model moves the command header
and FIS prefix into SRAM. The test then checks the backend descriptor, one
synthetic 512-byte host transfer, the three completion writes, and rejection
of an unsupported command. The 512 bytes come from the emulator's synthetic
SSD sector. This test does not prove that real hardware populates the SRAM
window, reads the host PRDT, or delivers an interrupt to the PC. The open
path also lacks host GHC enable/reset handling, command-list-base event
handling, DMA queue software state, repeated requests, multiport routing,
NCQ, and RAID. It is not ready for SPI testing as a
host-visible controller.

## Open host-reset register sequence

IDA `sub_3781C` selects reset before AHCI enable, then calls its runtime
reset routine at `0x30042C74`. That routine writes a global register prelude,
resets each virtual port, reinstalls the frontend IRQ masks, and clears GHC
bit 0. The rest of the stock reset also updates software port state and
interrupt handling.

`firmware/host_frontend.c` provides `host_frontend_reset_registers` with an
explicit per-port snapshot. In the no-disk and one-SSD Unicorn fixtures, the
virtual ports produce the same **118 ordered MMIO writes** as the stock reset
branch. Run `python tools/compare_open_host_reset.py ../88.bin` to reproduce
the comparison. The static V2 stage calls this function. On the board, the
host requested GHC reset with `0x80000001`; the open stage replayed the
register sequence, the host then enabled AHCI with `0x80000002`, configured
CLB, and sent one IDENTIFY request. This establishes the real host control
transition for the reference board but does not establish Windows-visible
data or subsequent I/O.

The V2 [board capture](../fixtures/open-static-v2-one-ssd.uart.txt) also
measured `0x00010005` and `0x00EC8027` in the port-0 SRAM auto-fetch window.
Those words are the AHCI slot-0 header and IDENTIFY FIS prefix, so the
hardware-assisted fetch path operates on this board. The open stage observed
physical backend completion and wrote the same three virtual completion
registers identified in the stock Unicorn trace. The [hardware baseline](hardware-baseline.md)
records the precise scope of this result.

An additional read-only builder accepts IDENTIFY DEVICE and READ DMA EXT.
`python tools/compare_open_host_descriptor.py ../88.bin` compares its READ
DMA EXT backend slot against the stock software path, byte for byte.
`python tools/emulate_open_read_only.py` checks backend issue, completion,
slot-0 rearming, and rejection of an ATA write command in Unicorn. This path
is not connected to the V2 board image, and its host data transfer has not
been tested on hardware.

The V3 board capture showed why merely servicing the first command was not
enough. The host sent `EF/03` immediately after IDENTIFY, reusing slot 0 while
the issue shadow remained `1`. Its auto-fetched header had PRDT length zero.
The stock software fixture forwards that command with CTBA low bit 2 set and
the same FIS prefix copied to its physical slot. The open builder now matches
those 64 bytes, and its next static variant recognizes a changed fetched
header/FIS without waiting for a zero-shadow interval. Identical repeated
commands remain a separate case.
