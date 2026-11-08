# Reference board observations

Reported by the board owner on 2026-10-07. The board is attached to a separate
Windows computer. UART is available at 115200 8N1; JTAG is not currently
available. The owner has a spare SPI flash chip.

## Stock image, no disk

- Firmware: `2.3.0.1041`, built 2012-07-04 18:55:01.
- Chip reports `Magni device id: 9230, rev: 61`.
- SPI device reports `Winbond/W25X40`, size `0x80000`, block size `0x1000`.
- `Gigabyte early post spd: 20` (see the exact register calculation in
  [early initialization](early-init.md)).
- DMA, IDE host, AHCI host, core, SPI and RAID initialization all log success.
- Front and backend threads start; `AHCI controller started.` appears.
- `port 7 Auto-fetch enable` and console device 12 mapping to virtual port 7
  appear at the end of the captured log.

## Stock image, one SSD on port 0

- Same firmware, chip revision and SPI identification. The capture begins
  mid-line (`version ...`), so its first few characters are missing.
- `Gigabyte early post spd: 30` in this boot; the physical meaning of this
  field has not been established.
- `port 0 pmp 15 srst successfully.` and device signature `00000101`.
- The firmware identifies an SSD, notes TRIM support, and reports
  `DISK0, DDF not found.` This disk is not a RAID compatibility test.
- Both `port 0 Auto-fetch enable` and `port 7 Auto-fetch enable` appear.
- The host disables and re-enables AHCI, resets the AHCI host, enters BIOS UI,
  releases UI memory at `0x30073000`, and resets AHCI again.

## Open ARM probe on spare SPI

The image generated from the analyzed `88.bin` by `tools/build_probe.py` was
flashed to the spare chip and **printed exactly `OPEN9230` over UART**. This
confirms that the stock loader transfers control to the open ARM entry code and
that the reconstructed UART initialization works on this revision-61 board.
The RAM marker write was not independently checked because JTAG is unavailable.
The probe does not initialize storage or run the original main firmware.

## Open UART register diagnostic on spare SPI

The owner flashed `build/diag.bin` and reported:

```text
OPEN9230 DIAG
CHIP=92301B4B
STRAP=0000002F
SPI0=A5A5A5A5
```

These values confirm that the three reads in the open ARM diagnostic execute
on this board. `CHIP` encodes device ID `9230` in its upper 16 bits. The stock
revision string is derived from a separate register: early code adds `0x50`
to the low byte at `0xD0030008`, so the stock `rev: 61` implies `0x11` there.

## Open C stage v1 on spare SPI

The owner flashed the 524288-byte image with SHA-256
`feaf6a2c65e516f0050311802a8427eb11720de061b5a11c7f79399b1227fdb9`.
The full [no-disk](../fixtures/open-c-stage-v1-no-disk.uart.txt) and
[one-disk](../fixtures/open-c-stage-v1-one-disk.uart.txt) UART captures are
preserved verbatim. With no disk, all four physical port link registers were
zero and signatures were `FFFFFFFF`. With one disk on port 0, `SSTS=00000133`
and `SIG=00000101`, showing that the open stage can read physical link and
signature state on the board. In both captures, PUNIT words `0x110`, `0x114`,
`0x300`, and `0x318` were zero at entry to open CODE1.

The open stage built an IDENTIFY descriptor, but the hardware did not retire
the command: `CI=1`, `IS=0`, `TFD=0x150` at timeout. The descriptor match and
synthetic completion in Unicorn do not predict real command execution. The
next stage implements observed stock PUNIT and backend controller setup and
reports state both before and after those writes.

## Open C stage v2 on spare SPI

The owner booted v2 (SHA-256
`a2f8f2a88a7c41adb7c1a800182a78363d1d537ea7617f62bf936f593bd6b9df`)
without a disk and with one disk on port 0. The captures are preserved
[without a disk](../fixtures/open-c-stage-v2-no-disk.uart.txt) and
[with a disk](../fixtures/open-c-stage-v2-one-disk.uart.txt); the latter ends
mid-line and the board did not automatically restart. The first line in that
capture is garbled as `U99230 C-STAGE`.

After PUNIT setup, register `0xD0020110` still reads zero on the board even
though the open stage wrote `0xF`; `0xD0020114` reads `4`, `0xD0020300` reads
`0xF`, and `0xD0020318` reads `0x01C9C380`. Backend control changes from zero
to `0x80000002`. Port 0 still reports `SSTS=0x133`, `SIG=0x101` with the disk.
The output stops at `P0_IDENTI`, after the descriptor report and after the
function that issues the command returns. This may be an IRQ-path failure,
but the capture alone does not prove whether the SATA command completed.

## Open C stage v3 on spare SPI

The owner booted v3 with one disk on port 0; the [complete UART
capture](../fixtures/open-c-stage-v3-one-disk.uart.txt) shows a real IDENTIFY
completion with interrupts masked. Immediately after issuing, `CI` already
read zero and `CMD` read `0x00710011`. The polling path reported `IS=2`,
`TFD=0x50`, global interrupt status zero, ATA IDENTIFY word 0 `0x0040`,
major version word 80 `0x07F8`, rotation word 217 `1`, and DATA SET
MANAGEMENT word 169 `1`. The data buffer was initialized to `0xA5` before
the command, so these values provide evidence of physical DMA into SRAM.
This validates one physical-port command path for this board and disk. The
interrupt path remains unverified and v2's mid-line stop remains unexplained.

## Open C stage v4 on spare SPI

The owner booted v4 (SHA-256
`8281db761d9aab71da8d26ed89553eec5e7df7071c7ca8c14e728fdfedd81881`)
with one disk on port 0. The [UART capture](../fixtures/open-c-stage-v4-one-disk.uart.txt)
reports physical IDENTIFY completion as in v3, followed by a READ DMA EXT of
LBA 0 in slot 1. `CI` read zero immediately after issue; polling reported
`PxIS=1`, `PxTFD=0x50`, and global IRQ status zero. Of the 512 bytes inspected
from `0x3006E0D0`, 504 changed from the initial `0xA5`. The first 16-bit word
remained `0xA5A5`; the last inspected word was zero. This strongly suggests
the actual DMA target begins at `0x3006E0D8`, eight bytes later, consistent
with the descriptor's tagged address `0x0006E0D9`. V4 did not inspect the
actual last eight target bytes. Its output stopped at `P0_IRQTES`, during the
subsequent IRQ test. The capture alone does not locate the exact failing
instruction.

## Open C stage v5 on spare SPI

The owner booted v5 (SHA-256
`172c5495abdf3dc775a1d530ad4a849ffb5da469f4c79025cd9d4dc4a6731614`)
with one disk on port 0. The [UART capture](../fixtures/open-c-stage-v5-one-disk.uart.txt)
has one extra `x` before the first stage banner; the following lines are
well-formed. IDENTIFY completed with `PxIS=2`, `PxTFD=0x50`. READ DMA EXT of
LBA 0 completed with `PxIS=1`, `PxTFD=0x50`. The corrected 512-byte buffer at
`0x3006E0D8` changed entirely from `0xA5`; the first word was zero and the
last was `0xAA55`. The eight-byte guards before and after the target remained
`0xA5` and `0x5A`. This validates the corrected DMA address and length for
this disk and command.

The following IDENTIFY completed with port and global interrupt routing
enabled while CPU IRQs were masked: `PxIS=2`, `PxIE=0xFDC000DB`, global pending
bit 0 set, and valid IDENTIFY word 0. Incoming SCTLR `0x00052870` had the
high-vector bit (`0x2000`) set. The reset stub cleared it to `0x00050870`, so
the CPU used the open low-vector table. After unmasking CPU IRQs, the stage
reported one IRQ with pending bit 0, `PxIS=2`, cleared `CI`, successful
acknowledgment, and valid data. This confirms basic IRQ delivery and return
on this board; high load and error paths remain untested. The changed vector
setting is a plausible explanation for v2 and v4 stopping during IRQ tests,
but their exact failure sites were not measured.

## Open static host diagnostic V1 and V2

The owner booted both static images with an SSD on physical port 0. The
[V1 capture](../fixtures/open-static-v1-one-ssd.uart.txt) repeated successful
physical IDENTIFY, read-only LBA-0 DMA, and CPU IRQ tests. Its frontend
remained uninitialized: host GHC, CLB, issue shadow, and auto-fetch were zero,
so the bounded host test ended `NOT_READY`.

The [V2 capture](../fixtures/open-static-v2-one-ssd.uart.txt) came from the
512 KiB image with SHA-256
`06152071a924209e87c1c5fe78992c30a5adaaa83975892b3fa3a1ab981c19f6`.
V2 installed the stock-matching virtual-port reset, IRQ masks, DMA registers,
and port-0 auto-fetch. The host then changed GHC through `0x80000000`,
`0x80000001` (reset requested), and `0x80000002`, supplied command-list base
`0x0009C0C0`, and started virtual port 0. The open stage handled one GHC reset.
The hardware auto-fetch window changed to AHCI header word `0x00010005` and
FIS prefix `0x00EC8027`, identifying a host IDENTIFY DEVICE request. The open
stage issued that request to the physical SSD, observed backend completion,
and cleared the virtual command issue bit. Its final `HOST_RESULT=COMPLETE`
establishes this controller-side path on the board. The owner then reported
that this PC does not reach BIOS with the SSD attached, while BIOS starts
without the SSD. Thus this completion is insufficient for a usable host path.
The V2 stage stopped servicing commands after `STATIC_TEST_END`; it also
omitted the stock write to global host `IS` and used a different order for
completion registers. OS-visible DMA data and PCIe interrupt delivery remain
unobserved.

## Open static host diagnostic V3

The owner booted V3 with the SSD attached and reported that the PC still did
not reach BIOS. The [UART capture](../fixtures/open-static-v3-one-ssd.uart.txt)
shows a successful backend IDENTIFY followed immediately by a second host
command. At the completion snapshot, `P0CI=1` and issue shadow `1`; the SRAM
auto-fetch window had changed from the IDENTIFY FIS to `03EF8027`, identifying
ATA SET FEATURES with feature `03` (set transfer mode). V3 only accepted a new
slot-0 command after observing shadow zero and did not forward this command.
The PC had therefore progressed beyond its first IDENTIFY response even
though the BIOS screen remained unavailable. V4 changed the rearm rule and
forwarded this specific no-data command. Its
[capture](../fixtures/open-static-v4-one-ssd.uart.txt) shows both host commands
completing on the physical SSD, followed by `PxCI=0` and issue shadow zero;
the PC still did not reach BIOS. The physical D2H response from `EF/03` was
present but had not been staged for frontend FIS delivery. V5 adds that copy
and uses the stock non-queued completion register path. Its
[board capture](../fixtures/open-static-v5-one-ssd.uart.txt) confirms
`HOST_20=00504034` after `EF/03`, but the PC still does not reach BIOS. V5
auto-fetch remained `0x1D`, omitting the stock port-7 console bit. V6 enables
that bit and logs all other virtual-port command activity; its hardware result
is pending.

## Remaining baseline captures

- Whether a corrected static host path allows BIOS to complete disk discovery.
- Full PCI configuration and AHCI BAR values in normal and RAID modes.
- One sacrificial drive per physical port, hot-plug/reset/error cases.
- RAID 0/1/10 and HyperDuo metadata and recovery using disposable disks.
- AES setup and data compatibility using disposable disks only.
