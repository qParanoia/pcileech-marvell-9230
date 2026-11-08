# Static host boot research after V7

The experimental SPI images execute one fixed program at power on and take no
UART commands. They retain the stock loader, Option ROM, CODE2, and CODE3;
CODE1 is open code. The board has a spare SPI chip and a disposable SSD.

## What the board established

V5 completed host `EC` and `EF/03` through physical port 0, but the PC stopped
before BIOS. V6 enabled auto-fetch on virtual port 7 and exposed a pending
`A1` (`IDENTIFY PACKET DEVICE`). V7 copied the same 512-byte response and
completion sequence as the stock firmware. Its UART showed
`HOST_CONSOLE_A1 EVENT=00000001`, followed by another active slot on port 7:

```text
HOST_CONSOLE_SRAM=00000000 00010065 00000000 0009C200 00000000 01A08027 40006300 00000000 00000063
```

The new FIS is ATA `A0` (`PACKET`) with a 99-byte transfer. The PC still did
not reach BIOS. The V7 code handled only `A1`. It also latched `seen` until a
poll observed `CI=0`, so a fresh request arriving immediately after completion
could be missed. Both issues were addressed before the V8 board test.

## Offline packet chain

The Option ROM's 99-byte `A0` request at x86 offset `0x4C2D` uses CDB `1D`.
Its management payload starts with `E0`, contains `FD` at byte 8 and `A4` at
byte `0x3C`, and carries BIOS time at bytes `0x56..0x59`. The stock handler
stores that time and changes the saved response marker to `E1`. A subsequent
CDB `1C` retrieves the response. The ROM also emits `E1/10` management
requests. Subcommand `03` with nonzero low flag bits enters the RAID BIOS UI;
subcommand `01` updates or queries an existing UI. See
[`option-rom-console.md`](option-rom-console.md) for the decoded switch table.

The development handler now covers the observed `A1`, `FD/A4`, `E1/10/09`
version notification, the inactive `E1/10/01` response, `F3/03` for one
connected SSD, and the `1C` response path. The host CI bit identifies a new
slot even if polling misses an idle interval. These checks pass in
Unicorn:

```text
python tools/compare_console_a1.py
python tools/compare_console_packet.py
python tools/probe_bios_ui.py
python tools/probe_option_rom_sequence.py
python tools/compare_option_rom_sequence.py
```

The packet comparison injects `A1 -> FD/A4 -> 1C` as one sequence and verifies
that all three commands complete, the OS time is stored, and the response
buffer is returned. It compares the `FD/A4`, `F3/03` one-SSD, and SCSI `03`,
`12`, `46`, and `5A` replies with the stock image byte for byte. The emulator
does not execute the motherboard BIOS, and
the CODE3 RAID UI callback depends on state that the open CODE1 has not yet
implemented. The last probe enters the **stock** BIOS UI with a dedicated
synthetic worker stack; the sequence probe then completes nine selected
stock Option ROM commands in one run. The matching open-stage sequence
completes all slots with status `00`, using a minimal session bit rather than
the stock RAID UI. This does not establish motherboard POST behavior.
`build/static-boot-dev.bin` is a local development image.

## V8 static board candidate

`build/basic-boot-v8.bin` retains the stock loader and Option ROM, and skips
the LBA-0 read and IRQ diagnostics before initializing the host frontend.
`python tools/emulate_static_boot_test.py ../88.bin --basic-boot` checks
single-sector and eight-sector synthetic write/readback, backend errors,
repeated reads, and a late host command in the full V8 image. The separate
console sequence test returns status `00` for nine selected Option ROM
management requests. These checks cannot prove that this motherboard reaches
BIOS POST, or that a real SSD can be safely written.

The V8 board run reached BIOS and Windows with one SSD on physical port 0.
UART showed backend IDENTIFY, host `EC` and `EF/03` completion, and virtual
console `A1` and `A0` completions. Windows listed an unknown disk-class device
with no model or volumes and no Device Manager error. No Windows read/write
traffic is established by this capture.

A continuation of the V8 UART capture exposed the next blocker: after a
Windows host reset and `EF`, Windows issued ATA `F5` while `PxCI=1`. V8
logged `EVENT=FFFFFFFE`, its builder's unsupported-opcode result, and did
not retire the host slot. The stock firmware forwards `F5` with an empty PRDT.

The V9 static image forwards `F5`, completes no-data commands with a D2H FIS,
and retires rejected commands with `PxIS.TFES` rather than leaving the host
waiting. A read-only V9 probe also samples the host command table's PRDT, the
host IDENTIFY destination through the PCIe CPU window, and the retained local
IDENTIFY data before host completion. Its COMRESET recovery replays virtual
port 0 status from the linked backend SSD.

On the board, V9 reached Windows and completed `F5`, then another `EF`, but
the SSD was still absent from `Get-Disk`. The IDENTIFY probe read 512 matching
bytes from host memory. A stock completion trace shows that PRDBC can remain
zero for this IDENTIFY path. The confirmed remaining divergence is no-data
completion: the stock firmware uses `PxIS=8` and `PxSACT=1` for `EA`, `E7`,
`EF`, and `F5`; V9 used `PxIS=1` and did not set `PxSACT` for these commands.
V10 applied the stock sequence on the board, but Windows still showed an
unknown disk device absent from `Get-Disk`. A later IDENTIFY transferred the
SSD model and capacity into host memory. V11 additionally publishes the
response FIS entries in host memory and records `HOST_RFIS` readback. The
V11 board log confirms that host-memory write, but Windows still reports an
unknown device. V12 adds the missing host command-header `PRDBC` update before
`PxCI` is cleared; the 512-byte IDENTIFY data transfer had left PRDBC zero.
V13 verifies the host header before this update and forwards 257-entry PRDT
descriptors. Its full-image Unicorn fixture checks a synthetic 128-KiB
WRITE/READ round trip through those descriptors.

## Remaining boot and compatibility work

The current target is basic AHCI disk operation, including host read/write and
OS installation and boot. The ROM's management statuses now match the nine
selected stock commands, but their side effects and the full motherboard POST
path are not modeled. Host enumeration with V13 and disk integrity still need
a board test.
