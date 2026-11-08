# Basic AHCI target

## V20: four physical AHCI ports and independent backend commands

V20 maps host SATA ports 0..3 to physical backend ports 0..3. Each owns its
host-slot selection, pending command, CFIS, DMA probe, logical-sector geometry,
reset bookkeeping and issue/completion/error counters. A round-robin poller
allows one active non-NCQ command on each physical port concurrently; each
host port accepts all 32 AHCI slot indices. A busy backend does not prevent
another port from issuing or completing a command.

The host implemented-port mask is `0x8F`: four physical SATA sockets plus the
existing virtual management endpoint at port 7. CAP.NP remains 7, the highest
implemented index, and CAP.NCS advertises 32 slots. Ports 4..6 are absent.
Startup and controller reset copy link/signature/task-file state from each
physical port rather than only port 0. Additional ports use CPU-window reads
for every host header and CFIS, including slot 0; they do not depend on an
unverified hardware auto-fetch layout. Port 0 retains its proven slot-0 path.

The original port-0 SRAM layout is preserved. Ports 1..3 own banks at
`0x30068000`, `0x30069000`, `0x3006A000`: command list at bank+0, RFIS at
bank+0x800, extension at bank+0xC00. Per-port startup IDENTIFY responses are
kept separately at `0x3006E400`, `0x3006E600`, `0x3006E800`; port 0 keeps
`0x3006E080`. Startup IDENTIFY commands use a temporary shared table and run
serially. A still-pending startup command prevents that table from being
reused by the next port. Runtime host DMA uses each request's own host PRDT.
Internal host FIS scratch uses the stock `0x40` per-port stride.

`HOST_IO` and completion details include `PORT`. The UART `?` snapshot includes
four `HOST_SATA PORT=...` lines with link, signature, host/backend CI, task file
and per-port counters even after detailed command tracing is exhausted.

`python tools/emulate_multiport.py` executes the compiled ARM reset/startup
and runtime service against translated host memory and separate disk models.
It verifies all six pairs issuing WRITE/READ concurrently, reversed completion
order, exact data readback, mixed 512/4096-byte logical sectors, four concurrent
backends at each of the 32 host slot indices, independent failure completion,
and reset of an idle port while another disk is active. It also boots and
performs I/O with only port 1 or only port 3 populated. Physical DMA completion,
link changes and IRQ/register effects are modeled. These checks do not prove
the chosen additional SRAM banks, physical IRQs or multi-disk transfers on the
real controller. Reset of an actively transferring port, hot removal and NCQ
remain outside the validated scope.

The delivered V20 diagnostic keeps the legacy Option ROM disabled, as V19.
Boot-from-controller work remains separate. The next board check is cold boot
with two test disks, both visible from live media, then independent writes and
readback on each. No two-disk V20 board result has been received yet.

## V19: virtual console host slots and bounded completion

The owner tested V18 without a SATA disk and reported that Windows still
stalled. Repeated HOST_ALIVE lines showed GHC=80000002, P0CI=0, P7CI=2,
backend CI=0, and no physical I/O. This establishes a live ARM service loop,
an active host AHCI controller and a pending virtual-console slot 1. The
capture does not identify the pending ATA opcode. V18's port-7 poller only
accepted bit zero and only A1/A0, silently ignoring other commands.

V19 selects any of the 32 console CI bits, reads nonzero headers/CFIS directly
through the verified PUNIT CPU window, and retires exactly that bit. Nonzero
slots do not depend on slot-zero auto-fetch shadow; the command engine must
be running. Slot-zero legacy auto-fetch handling remains. A1, A0 and no-data
EF are serviced. Unsupported ATA opcodes, malformed headers, unsupported
PRDT counts, and packet validation failures receive host-visible error
completion instead of leaving CI asserted. PACKET without data is supported.
The virtual console still supports at most one PRD per request.

Known actual transferred byte counts are published to the matching command
header when present. D2H and SDB FIS are written to a valid enabled host RFIS
buffer before completion. HOST_CONSOLE includes SLOT; HOST_ALIVE includes
P7SH, P7OP, P7SLOT and P7STATUS, which describe the latest serviced request.

`emulate_host_slots.py` covers port 7 all 32 indices with A1, EF/03, INQUIRY,
PRDBC, D2H/SDB and exact CI/SACT writes; it additionally covers no-data PACKET,
bad/unsupported requests, no-shadow slot 1, neighboring header preservation
and CLB carry across 4 GiB. No physical SATA command is permitted in these
virtual-console cases. The nine-command legacy Option ROM sequence and stock
A1 response comparison pass, alongside the full disk/stripped-runtime suite.

The full-image fixture now models the observed ARM-facing port-7 CI clear-mask
semantics: writing ~mask preserves other pending bits rather than creating
31 new synthetic requests. Register-write traces still retain raw bus writes.

The delivered diagnostic variant keeps the Option ROM erased, as in V18, to
test the console-slot correction without reintroducing legacy ROM execution.
The owner subsequently reported that the Windows 11 USB installer boots with
V19 and can sometimes create an NTFS volume. Installing to that disk is still
blocked: Setup reports that the computer hardware may not support booting to
the disk. The latest UART excerpt ends at ISSUED=DONE=0x238 (568), both port
queues and backend CI empty, TFD=0x50 and ERR unchanged at 1 throughout the
excerpt. This does not show a pending-command stall, but does not prove data
integrity, successful installation, or firmware-level boot support. The detailed
I/O trace allowance is exhausted before the later partitioning attempts.

Boot mode, GPT/MBR layout and Setup's Panther logs must be collected before
attributing this message to a particular cause. The no-ROM variant cannot
supply the removed card's legacy BIOS disk services; UEFI boot would require
a suitable motherboard or add-in UEFI storage driver exposing the disk. An
AHCI disk visible through Windows' driver is not by itself a firmware boot test.

## V18 diagnostic: Windows installer startup with Option ROM excluded

The owner reports that the Windows 11 installer USB hangs with the V17 card
present, including with the SATA disk disconnected, and boots when the card
is removed. The no-disk UART remains at GHC=0. Static inspection of the supplied
StorAHCI 10.0.22621.2506 shows early GHC writes in FindAdapter, which are not
visible in that capture. This implicates card presence but does not locate the
failure in StorAHCI or prove an Option ROM fault.

`build_c_stage.py --basic-boot-probe --no-option-rom` builds V18 with the
legacy x86 Option ROM region 0x20000..0x2FFFF replaced by FF. Autoload, ARM
loader, MAGIIMGF header and the other vendor segments are preserved. The
image prints `OPEN9230 BASIC BOOT V18` and `OPTION_ROM=DISABLED`. This erases
the known ROM content; it does not reprogram the PCI ROM BAR. Legacy BIOS
boot services from this card will be unavailable if the BIOS skips that ROM.
Test startup from the installer USB first, with no SATA disk attached.

`HOST_ALIVE` is emitted every 4194304 service-loop iterations (not a calibrated
time interval) and on receiving UART `?`. It reports GHC, port-0 CI/shadow,
port-7 CI, backend CI/TFD and cumulative issue/completion/error counts after
detailed tracing is exhausted. It does not initiate SATA commands. This can
distinguish a still-running firmware loop from silence during a host stall;
absence of output by itself does not identify a specific ARM fault.

The no-ROM full-image and stripped-runtime suites, read-only UART query,
32-slot regression and stock reset comparison pass offline. Hardware PCI
enumeration, motherboard ROM handling and Windows startup remain unverified
for this variant. The successful V17 hardware result is retained separately.

## V17: arbitrary non-NCQ host slot indices

The V16 board capture from Arch Linux completed physical and host IDENTIFY,
including a 512-byte host-buffer match and PRDBC=512. Linux subsequently
issued READ DMA C8 with tag 22 and timed out. UART showed CI=00400000, then
other nonzero CI bits, without a corresponding HOST_IO C8 issue. V16 polled
only bit zero and always retired host slot zero.

V17 selects a pending bit from host CI and its issue shadow, retains that
slot until backend completion, and serializes requests on physical slot zero.
For nonzero slots it reads CLB+32*slot and the selected CFIS using the PUNIT
CPU window, rather than assuming the unverified hardware auto-fetch SRAM
layout for those slots. PRDBC targets the selected 32-byte header. CI and
SACT completion masks target the selected bit. The host CAP advertises 32
slot indices with NCQ disabled. UART prints BASIC BOOT V17 and SLOT= on
HOST_IO lines. Existing slot-zero Option ROM handling is retained.

`python tools/emulate_host_slots.py` executes the compiled ARM frontend with
a translated 64-bit synthetic PCIe bus. It checks all 32 indices, slot changes,
queued requests, READ/WRITE descriptors, 4096-byte PRDBC, untouched neighboring
headers, completion masks, backend ATA failure, NCQ rejection, and CLB carry
across 4 GiB. Backend completion and bus accesses are modeled; hardware IRQ,
PCIe ordering and physical multi-slot behavior still require a board run.

The existing stripped-runtime full-image regression and stock reset-register
comparison must also pass. These tests do not establish OS installation or
boot reliability on the real controller.

### V17 board result, 2026-10-27

The owner booted Arch Linux live media, partitioned/formatted the attached
disk as NTFS and created text files with content. After moving the disk to
the main PC, the files and contents were readable. This is evidence for
persistent basic filesystem I/O through the physical controller on port 0;
it is not a hash-based large-file integrity test or a boot test from that disk.

The original UART capture is saved without modification as
`fixtures/open-basic-v17-arch-ntfs.uart.txt`. It shows the late-signature path
working: initial SIG=FFFFFFFF, P0_SIGNATURE_ENGINE=1, then SIG=101 and
P0_DESC=1. Ten logged host IDENTIFY completions have PRDBC status 0 and
512-byte counts. The later host RFIS readbacks succeed using addresses above
4 GiB. Logged SET FEATURES completions have no data, so PRDBC status 1 with
zero bytes is the intentional no-update result.

The capture also contains ten HOST_PORT0_RESET_DONE records and repeated
IDENTIFY/SET FEATURES initialization. Nine IDENTIFY comparisons match 509
of 512 bytes against the startup response; the model/capacity words shown
remain equal. The capture does not contain all response bytes, so it cannot
distinguish changing ATA feature state from other causes of this difference.
The bounded shared service logger exhausts its allowance during startup:
there are 59 HOST_IO lines (all slot zero), but no detailed C8/CA file-I/O
records. Later nonzero CI/shadow bits are observed. The owner's independent
readback supports successful file writes, but the UART alone does not prove
error-free startup, every-slot completion, or long-duration reliability.

The current target is an SSD/HDD visible to the host as an AHCI disk, with
reliable reads and writes and the ability to install and boot an operating
system. RAID, HyperDuo, AES, and the RAID setup menu are outside this target.

The stock SPI image contains a legacy x86 Option ROM at `0x20000`: its `PCIR`
header is at `0x2001C` and reports code type `00` (PC-AT). AHCI host
enumeration does not require that ROM, but legacy BIOS boot from a drive on
this card may depend on it. V17 and builds without `--no-option-rom` preserve
the stock Option ROM; the delivered V18/V19 diagnostic variants erase it.
The board's boot mode and disk boot support have not been established.

## Offline evidence

- `tools/probe_host_rw.py` captures stock backend descriptors for host `35`
  (WRITE DMA EXT) and `EA` (FLUSH CACHE EXT), as well as the modelled stock
  completion. This is an ARM firmware run with synthetic host and SATA events;
  it is not a motherboard BIOS or a disk model.
- `tools/compare_open_host_descriptor.py` compares the ARM open builder's
  64-byte descriptors byte for byte with stock for `EC`, `25`, `EF/03`, `35`,
  `EA`, `06` (DSM), `B0` (SMART), `E7` (legacy flush), `C8`/`CA`
  (28-bit DMA read/write), and `F5` (SECURITY FREEZE LOCK).
- `tools/emulate_open_read_only.py` exercises the open backend issue and host
  completion for those commands. `tools/emulate_static_boot_test.py` exercises
  them in the full open-stage Unicorn image. Its persistent synthetic disk
  model now checks a 512-byte WRITE to LBA 1 followed by a READ of the same
  LBA and compares all returned bytes with the original pattern. The model
  also checks an eight-sector 4096-byte WRITE/READ and compares all returned
  bytes. It still does not reproduce physical SATA or PCIe DMA timing.
- Consecutive identical host READs are reissued using the host CI bit as the
  new-command condition. A synthetic backend ATA failure now retires the host
  slot with task-file status and `PxIS.TFES`, so the host can retry or report
  the error instead of waiting forever. A stock error injection in Unicorn
  did not expose the physical error as host `PxIS.TFES`; the synthetic stock
  error path is therefore not a reliable byte-for-byte oracle for this case.
- The V17 host CAP register advertises 32 slot indices and no NCQ,
  with commands executed serially on backend slot zero. The other 117 host-reset
  writes retain the stock order and value, as checked by
  `tools/compare_open_host_reset.py`.
- Two-entry host PRDT headers for READ and WRITE match the stock backend
  descriptors byte for byte. `tools/compare_large_prdt.py` also confirms
  that the stock ARM code forwards 33- and 257-entry PRDT headers unchanged,
  and that the open ARM builder matches both. The current source accepts up
  to 257 entries. The synthetic disk model checks a 257-entry 128-KiB
  WRITE/READ round trip with non-contiguous PRDT addresses. It models their
  bytes as one aggregate buffer and does not reproduce PCIe DMA timing.

## V8 board candidate

`build/basic-boot-v8.bin` removes the LBA-0 and IRQ diagnostics from startup.
It initializes physical port 0, then starts the one-slot host service and
virtual-console responder. The V8 Unicorn image checks nine basic ATA command
paths, 512-byte and 4096-byte synthetic write/readback, consecutive identical
READs, backend error retirement, late host commands, and the EF/03/console
sequence. The nine selected Option ROM management exchanges also complete in
the V8 Unicorn image with status `00`. The stock Option ROM is retained byte
for byte.

The image is a board-test candidate, not a validated disk firmware. Current
code services only physical port 0 and one host slot; the other three physical
SATA ports are unsupported. PCIe DMA timing, motherboard POST, and real disk
data integrity remain unproven by Unicorn.

On the board, V8 completed physical IDENTIFY and the BIOS's `EC`, `EF/03`,
`A1`, and several `A0` requests. The PC reached BIOS and Windows. Windows
listed a disk-class "unknown device" with no reported model or volumes, and
`Get-Disk` did not list the SSD. The continuation of the UART capture showed
Windows issuing `F5` with `EVENT=FFFFFFFE` and host slot 0 still pending.
The V8 builder rejected that opcode and returned without retiring PxCI. The
stock firmware's backend descriptor probe confirms it forwards `F5` to the
drive. This is a confirmed enumeration blocker; the board may expose further
issues after this command completes.

## V9 static candidate

`build/basic-boot-v9.bin` forwards `F5` and other ordinary ATA commands to
the physical port after checking the AHCI header. Rejected commands produce a
host-visible ATA error and retire PxCI. A busy physical port defers the host
request until it is idle. No-data commands stage a Register D2H FIS before
host completion. V9 also prints read-only host IDENTIFY DMA telemetry and
replays virtual port 0 status after a host COMRESET release. The same stock
loader, Option ROM, CODE2, CODE3, and data regions are retained byte for byte.

Unicorn verifies the F5 descriptor against the stock image, F5 completion,
rejection retirement, a busy backend retry, ten ATA opcode paths in the full
image, write/readback, and virtual port reset. On the board, V9 completed
`F5` and a subsequent `EF`, but `Get-Disk` still did not show the SSD. The
read-only IDENTIFY probe found all 512 bytes in host memory identical to the
physical SSD response. Its host command header PRDBC remained zero; a stock
firmware completion trace takes the same path and does not update PRDBC for
IDENTIFY, so this is not by itself evidence of a transfer failure.

## V10 board result and V11 static candidate

Stock firmware completes successful `EA`, `E7`, `EF`, and `F5` commands with
`PxSACT=1`, `PxIS=8`, and a clear mask for slot 0 in `PxCI`. V9 instead used
`PxIS=1`, left `PxSACT` clear for commands with no data, and staged a D2H FIS
in frontend scratch. V10 aligns this success path with the stock register
sequence. Backend errors still produce `PxIS.TFES`, and malformed host
requests still retire the slot. V10 reached Windows and transferred IDENTIFY
data into host memory, including the model and capacity, but the drive still
appeared as an unknown device and was absent from `Get-Disk`. The late
IDENTIFY buffer matched 509 of 512 bytes against the retained startup data;
those three differences have not been localized.

The V10 UART capture showed the frontend SRAM response area at
`0x30003038` containing uninitialized-looking data, while stock CODE1's
completion path copies eight bytes from this location and signals a Set
Device Bits FIS with `PxIS=8`. V11 writes an eight-byte Set Device Bits FIS
there and, using the same PUNIT host-memory window used for the read-only
IDENTIFY probe, publishes PIO Setup, D2H, and Set Device Bits FIS entries to
the host's 256-byte received-FIS buffer before retiring the command. This
targets a concrete missing host response, but the exact cause of Windows'
unknown-device state is not yet proven. The V11 UART `HOST_RFIS` line checks
the buffer address and immediate readback. Unicorn verifies writes to a
synthetic 64-bit host buffer for ten ATA commands and an error completion;
it does not model PCIe ordering or Windows enumeration.

## V11 board result and V12 static candidate

V11 reached Windows and reported `HOST_RFIS STATUS=0` for the Windows
commands: the Set Device Bits FIS was written to and read back from the host
received-FIS buffer at `0xCEDC1100`. Windows still showed an unknown disk
device and did not list it in `Get-Disk`. The captured sequence after the
Windows reset contains `EF`, `F5`, and `EF`, with no later `EC` in that log.

The earlier V10 board log confirms that the host received all 512 IDENTIFY
bytes, while its command header's `PRDBC` remained zero. This violates the
[AHCI 1.3.1 requirement](https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/serial-ata-ahci-spec-rev1-3-1.pdf),
section 5.4.1: a non-NCQ command must have an accurate byte count before
`PxCI` is cleared. The stock CODE1 software consumer does not update PRDBC
in the synthetic run; actual stock frontend hardware may do it. The open
direct physical-DMA path bypasses that bookkeeping.
Microsoft's [StorAHCI sample completion path](https://github.com/microsoft/Windows-driver-samples/blob/main/storage/miniports/storahci/src/io.c)
compares PRDBC with the requested transfer length for non-NCQ commands and
reports the smaller PRDBC on an underrun. This makes the board's zero count
a concrete explanation for the empty IDENTIFY data reported by Windows,
although only a board test can establish that it is the sole cause here.

V12 writes the data byte count into the host command header through the
PUNIT PCIe CPU window before signaling completion. It reads the backend slot
counter when available and uses the known ATA transfer length on successful
commands if hardware left that counter at zero. It also updates the local
auto-fetch copy of the header, in case hardware writes that copy back. UART
reports `HOST_PRDBC` status, CLB, old value, new value, local value, and
readback. Unicorn confirms 512-byte
and 4096-byte counts in synthetic 64-bit host command-list memory. The board
has not tested V12; whether this fixes Windows enumeration is still open.

## V13 static candidate

`build/basic-boot-v13.bin` contains the V12 PRDBC repair plus a host-header
check before writing that count. The check accepts the board's observed
32-byte-aligned CLB and tries the 1-KiB-aligned base only if the first header
does not match the fetched command. This avoids writing an unrelated host
buffer when the controller presents an unusual CLB. The V13 ARM builder also
accepts up to 257 PRDT entries; the stock ARM code was observed forwarding
both 33 and 257 entries.
The 524288-byte SPI image has SHA-256
`701d2a6c2fd62ac1344d794cb38f08135f417556b96f8c580d738fc65f09b318`.

The full-image Unicorn run covers no-disk boot, host IDENTIFY with model and
capacity, ten host ATA opcodes, 512-byte, 4-KiB, and 128-KiB synthetic
WRITE/READ round trips, a backend ATA error, repeated reads, late host
commands, a virtual port reset, and the legacy console exchange. The 128-KiB
fixture uses 257 non-contiguous PRDT addresses. It does not prove real
PCIe scatter/gather DMA, Windows enumeration, or disk data integrity.
`python tools/emulate_static_boot_test.py ../88.bin --basic-boot-v13
--frozen-v13-image` runs these checks against the exact delivered
SPI file without rebuilding from later source. It verifies the file hash and
locates the idle hook in the frozen ARM payload. The delivered
file passes the modeled discovery, transfer, error, and reset scenarios,
including a second run with unused stock runtime sections zeroed only in
memory. The post-V13 native-4K adjustment is tested separately on the rebuilt
source and is not attributed to the delivered file.
Additional full-image checks deliberately corrupt the host command header:
V13 leaves its PRDBC untouched rather than writing an unrelated buffer. With
the matching header at the 1-KiB-aligned base and a bad header at the observed
CLB offset `0xC0`, it updates only the matching aligned header. Both checks
use modeled PUNIT host-memory windows; they do not establish which address
layout the board's PCIe bridge presents.

V13 is a new build; the delivered V12 image remains unchanged. A single board
run is needed to see whether Windows now enumerates the SSD and to capture
the new `HOST_PRDBC` telemetry. Only physical port 0 and one outstanding host
command are supported. The image still contains the stock loader, Option ROM,
CODE2, CODE3, and remaining CODE1 bytes, so it is a hybrid development image
rather than a fully open-source distribution.

## Post-V13 source check

The source now derives READ/WRITE PRDBC from ATA IDENTIFY logical-sector size
(word 106 and words 117-118, as interpreted by
[Linux libata](https://github.com/torvalds/linux/blob/master/include/linux/ata.h)),
with a 512-byte fallback for invalid geometry.
A full-image Unicorn fixture models a native-4K SSD and verifies a one-sector
4096-byte WRITE/READ round trip and PRDBC=4096. The previously delivered V13
SPI image is unchanged and does not include this source adjustment. Physical
4K-sector drives and PCIe DMA timing remain untested.

The synthetic disk fixture now decodes the device-register high nibble for
28-bit DMA commands. It verifies a WRITE/READ round trip at LBA `0x01234567`.
For every modeled WRITE/READ round trip, it overwrites the host data buffer
before the READ, so passing requires the read path to refill that buffer from
the modeled disk. This still cannot validate physical drive transfers.

The synthetic error injection now fails before its modeled data phase. The
rebuilt image retires failed READ and WRITE commands with `PxIS.TFES` while
leaving PRDBC at zero; the modeled disk stays unchanged after the failed
WRITE. This checks software error reporting, not partial physical DMA or the
state of a real drive after a failed write.

The working-tree source also re-arms slot 0 immediately after rejecting a
malformed or unsupported command. A Unicorn unit check repeats the same
rejected command without an intervening shadow-low poll and confirms that
both attempts retire with a host error. The delivered V13 image is unchanged.

## V14 offline candidate

`build/basic-boot-v14.bin` includes the post-V13 native-4K and command-rearm
changes plus a PUNIT PCIe CPU-window mapper derived from stock CODE1 function
`sub_318F0` (runtime `0x00001830`). Unlike the earlier fixed 64-KiB helper, it
grows the mapped range when a requested host structure crosses a 64-KiB
boundary. `python tools/compare_punit_window.py ../88.bin` executes the stock
and open implementations in Unicorn and compares their four PUNIT register
words and returned CPU pointer for ordinary and crossing ranges.

The 524288-byte image has SHA-256
`d9e2f4a0307d752a5c7d70046cd67ba5060dd2f3ad00654d813970eba8afd5d1`.
The full stripped-runtime V13-configuration regression passes against the
same working-tree source. V14 has not been run on the board.

`python tools/emulate_static_boot_test.py ../88.bin --basic-boot-v13
--stripped-stock-runtime` rebuilds the open stage, zeroes the unused stock
CODE1 tail, CODE2, CODE3, DATA1, and the entire Option ROM region in the
in-memory image, then repeats the discovery, I/O, error, reset, and console
checks. A separate Unicorn fixture executes the stock loader's MAGIIMGF copy
routine on that stripped image and verifies all four copied RAM segments byte
for byte. The command-path fixture then loads those segments into RAM and all
its runs stay inside the open-stage code. Neither fixture emulates the boot
ROM, PCI enumeration, or motherboard BIOS. This establishes loader-copy and
software-path independence in Unicorn, not a safe flash image or legacy boot
without the Option ROM.
