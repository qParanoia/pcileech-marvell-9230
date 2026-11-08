# CH568 diagnostic companion, OPEN9230 V21

## V24j/v31g2: firmware-enforced memory map, board-validated 2026-10-30

Board finding: a PRDT addressing unmapped host memory hangs the 9230 PCIe
master beyond any port- or controller-level recovery - the wedge is a
hardware dead-end. The fix removes the cause instead of chasing the effect:
mailbox command `0x1342` SET-MAP installs up to 8 physical ranges in the
controller (wire: {magic, 1342, count, 0, (low, high, end-low, end-high)*}),
and READ64/READ4K/READ-BATCH/READ-LINEAR all validate addresses against the
map BEFORE arming the DMA engine. An out-of-map address costs one rejected
request; the service and the disk port continue. Board proof: the address
that previously killed the rig until reboot (0x426000000) is now rejected
and the very next reads succeed.

Delivery: the CH568 firmware (build 31G2) accepts a 12-byte-header binary
USB frame 'CHSM' carrying the ranges and queues mailbox 0x1342; a `VERS`
text command answers the running build tag so flash-tool mishaps are
observable. The bridge arms the map at startup from its cached/discovered
ranges; its own address clamp remains as a second layer.

The complete pcileech workflow is now one command per host:
`MemProcFS.exe -device "rawtcp://127.0.0.1:8888"` - DTB, memory map, kernel
PDB (registry-enabled symbol server) and the Dokany-mounted `M:\` forensic
VFS all come up automatically; process virtual memory, registry, handles
and minidumps are served through the CH568 transport at LINEAR speeds.

## V24 final: READ-LINEAR at 25 MiB/s, board-validated 2026-10-28

The speed path is closed end to end. `0x1341` READ-LINEAR (wire
`{magic, 1341, addr high, addr low, pages, 0}`, 1..128 pages) issues one
WRITE DMA EXT (pages*8 sectors at LBA `0x7D0`) whose single PRDT entry
carries the host physical address directly: `{DBA low, DBAU high, reserved,
bytes-1}`, bit 0 clear. The backend engine DMAs host RAM over PCIe itself -
no CPU window, no SRAM staging, no copy. Board evidence: the zero page
returns byte-identical data through the direct path and the staged 0x133B
path at the same instant, distinct addresses return distinct pages, and
three 512-KiB streams pass the device-side CRC32.

Board results (v24f Marvell + v31f CH568): ten consecutive 512-KiB
READ-LINEAR streams at **24.99 MiB/s steady** (median 20.0 ms per stream,
device CRC skipped); CRC-verified mode at 4.9 MiB/s (the NDS32 CRC32 over
512 KiB costs ~80 ms). Session start baseline was 2.81 MiB/s.

Hardware findings recorded in this effort:

- The backend engine does not traverse the PUNIT CPU window; a window-
  aperture address in the PRDT reads the wrong memory. Host physical
  addresses in the PRDT are DMA'd over PCIe directly.
- The engine fetches command tables from the service SRAM bank only; a
  table relocated to 0x30014000 is never issued.
- Multi-entry PRDTs are refused in this descriptor flavor regardless of
  count encoding (DW0 shifted counts and DW1 counts were both tried). The
  stock firmware itself splits backend data at 0x1000 with one entry per
  command (IDA: write-descriptor builder at raw 0x646D8, constant pool
  0x649A0), so multi-entry never occurs in stock traffic.
- The stock WRITE descriptor is DW0=0x00010045 constant, DW1=0 always.
- The engine chunks Data FISes to 8-KiB payloads, pads the final FIS of a
  stream past the command byte count (observed +4), and does not wait for
  DMA Activate between FISes - it streams back-to-back. The CH568 peer
  (v31f) ping-pongs two 8320-byte SATA buffers, re-arms the receiver before
  each activate, and forwards only the bytes the command owes.
- CH568 v31f also adds: zero-copy USB IN streaming from the SATA buffer
  (endpoint RX NAKed while the DMA base is repointed), and a request flag
  that disables the device-side stream CRC32 for speed mode.

The staged V23 paths (READ64, READ4K, READ-BATCH through the PUNIT window)
remain unchanged and working; the service owns window 0
(`0xD0020000`/`0x40000000`), the host frontend window 1.

Host: `read_memory_batch.py --linear --pages N [--no-crc]`. Benchmark
capture: `fixtures/open-basic-v24-linear-benchmark.usb.txt`. Not yet
board-tested: long-duration reliability, concurrent disk traffic during
linear streams, and read stability while the target OS is booting.

## V24 (superseded intermediate notes)

V24 adds `0x1341` READ-LINEAR and moves the service to its own PUNIT CPU
window. Wire layout: `{magic, 1341, address high, address low, pages, 0}` with
1..128 pages; the controller maps one window over the whole linear range and
issues a single WRITE DMA EXT (pages*8 sectors at LBA `0x7D0`) whose PRDT
entry addresses the window aperture directly (bit 0 clear). No SRAM staging
copy and no 64-KiB staging limit: 512 KiB per command. The window cannot span
the 4-GiB host boundary; such requests and page counts outside 1..128 are
rejected. PING/STATUS report version 24.

Window separation: the service now owns window index 0 (registers
`0xD0020000`, CPU aperture `0x40000000`, the aperture the original Habr
firmware used on this chip), while the basic host frontend keeps window 1 for
disk PRDT staging. V23 mapped the service onto window 1 as well, which was
safe only because its copies were synchronous inside one poll; a READ-LINEAR
stream holds its mapping across poll iterations, so the two users must never
share a window. READ64/READ4K/READ-BATCH keep their staged V23 behavior on
window 0.

The matching CH568 firmware (3.1 of the mailbox tree) accepts the linear
WRITE35 at `0x7D0`, and adds three streaming improvements for every batch or
linear stream: a request flag (CHBQ reserved byte 8 bit 0, or CHLQ byte 8)
disables the device-side stream CRC32 — about half of the previous 22-ms
64-KiB batch budget — while SATA FIS CRC and USB packet CRC still protect
every segment; IN payload packets are transmitted by hardware directly from
the SATA receive buffer (endpoint RX is NAKed while the DMA base is
repointed); and Data FISes ping-pong between the two 8-KiB SATA buffers so
the link receives the next FIS while USB drains the previous one.

Host: `read_memory_batch.py --linear --pages N [--no-crc]` sends one CHLQ
command per batch; `--no-crc` works for both 0x133B and 0x1341.

Offline validation (`python tools/emulate_ch568_diag.py`): READ-LINEAR of 128
direct pages and of a single page returns exact host data; a port-0 disk
command completes exactly while a direct stream runs (separate windows);
page-count, wrap and legacy rejections are counted; every prior V23 path is
rechecked. Not verified on hardware: DMA-engine reads through the window-0
aperture (the direct PRDT entry), the CH568 zero-copy/ping-pong changes, and
real throughput. The first board check is a linear read whose data is
cross-checked against a 0x133B batch of the same range.

## V23: host-memory read commands

V23 extends the service with the mailbox memory-read dispatch that the CH568
3.0 firmware and its host scripts already speak. PING/STATUS behavior, wire
format, identity checks, and the port layout are unchanged from V22; the
STATUS/PING version field now reports 23.

| Command | Wire arguments | Return path |
|---|---|---|
| `0x1337` PING | none | one F1/A5 chunk (chip ID, version) |
| `0x1340` STATUS | none | eight F1/A5 chunks (64-byte SD21 snapshot) |
| `0x1338` READ64 | address high, address low | eight F1/A5 chunks (64 bytes) |
| `0x133A` READ4K | address high, address low | WRITE DMA EXT, 8 sectors at LBA 0x7F0 |
| `0x133B` READ-BATCH | page count, sequence, low/high pairs | WRITE DMA EXT, count*8 sectors at LBA 0x7E0 |

READ64 maps a 64-byte host range through the PUNIT CPU window (index 1,
registers `0xD0020010`, CPU aperture `0x50000000`) and returns it as reply
chunks. READ4K and READ-BATCH stage each 4-KiB host page into the 64-KiB SRAM
buffer at `0x30004000` (clear of every virtual-host bank, port bank, and
loaded segment) and hand the buffer to one WRITE DMA EXT: a single PRDT entry
with slot flags `0x10045` (5-dword FIS, W direction, one entry), the same
W-bit convention the proven basic-frontend host header uses for WRITE DMA EXT.
The window is unmapped after every page. Batch requests accept 1..16 pages and
stage them before issuing the single data command the CH568 peer expects.

Unsupported opcodes, the legacy FIS-chunked READ4K (`0x1339`), out-of-range
batch counts, and argument words on PING/STATUS are rejected with an error
count and no data reply. A failed window map rejects the request instead of
disabling the service; only command timeout disables the channel as before.

The CH568 side requires the mailbox firmware from the 3.0 tree (READ64,
READ4K-DMA, READ-BATCH, DMA Activate flow control). Its IDENTIFY model string
matches the service identity check, so the 3.1 PING/STATUS-only fork is not
needed for memory reads. Host clients: `host/read_memory.py` (READ64),
`host/read_memory4k_diag.py` (READ4K), `host/read_memory_batch.py` (BATCH).

Offline validation (`python tools/emulate_ch568_diag.py`): the compiled ARM
stage returns exact synthetic host memory for READ64 below and above 4 GiB,
READ4K on an aligned and a 64-KiB-crossing page, and READ-BATCH of sixteen
scattered pages and of mixed low/high pages, while a port-0 disk command is
outstanding; the PUNIT window is verified unmapped after each request; all
rejection paths are counted and touch no buffers.

### V23 board result, 2026-10-28

With `marvell-9230-v23.bin` on the 9230, the CH568 3.0 mailbox firmware on
the service device, and the kit host clients, all three memory-read commands
completed on the physical chain USB -> CH568 -> SATA mailbox -> open stage ->
PUNIT window -> PCIe -> target RAM:

- READ4K of `0x0`: 31 ms first request, sub-millisecond repeat, matching
  CRC32 and duplicate frame. The returned page is a real real-mode IVT (NMI
  at `0070:0008`, handlers in `F000:EEF3`/`F000:FF54`). Capture:
  `fixtures/open-basic-v23-ch568-read4k-ivt.usb.txt`.
- READ64 of `0x0`: eight F1/A5 chunks; the 64 bytes are identical to the
  READ4K page at the same address.
- READ-BATCH: 4-page batches at 2.69 MiB/s (5.8 ms) and 16-page batches at
  2.81 MiB/s (22.2 ms), valid CRC32 per batch.

This confirms the backend WRITE DMA EXT slot flags `0x10045` and real PCIe
window reads on this board. Remaining untested on hardware: long-duration
reliability and concurrent disk traffic on port 0 during reads.

## V22: service moved to physical port 2

The V21 board capture in `fixtures/open-basic-v21-ch568-on-port2.uart.txt`
has a real disk on physical port 0 (SSTS=133), no link on port 1, and a second
ATA device on port 2 (SSTS=113, startup IDENTIFY succeeds). V21's hard-coded
service socket 1 leaves CH568_DIAGNOSTICS_READY=0. The owner confirms CH568
is on port 2 and socket 1 is physically damaged.

V22 reserves physical port 2 for the fixed PING/STATUS service. Host PI changes
to `0x8B`; the disk path on port 0 is retained. STATUS/PING report version 22
and service socket 2. The 64-byte STATUS wire format and SD21 protocol magic
are unchanged. CH568 3.1 firmware is byte-for-byte unchanged; only the Marvell
image needs flashing. The standalone Test.exe checks the new firmware hash,
version, port map and service socket. It reports USB discovery once per
connection rather than once per SATA reply retry.

The compiled ARM synthetic-peer test uses socket 2 at SSTS=113 and verifies
PING/STATUS during outstanding disk writes/reads on socket 0, with exact disk
data readback and private service disabled for an absent or wrong-identity
device. The following sections
describe the original V21 layout; replace service socket 1/PI=8D/version 21
with socket 2/PI=8B/version 22 for the current build.

### V22 board result, 2026-10-28

The owner supplied a successful PING followed by eight STATUS snapshots at
17:38:00..17:38:07. The CH568 request count increases from 2 to 9 and its error
count remains zero. The controller reports a connected disk on port 0, with
zero host disk requests/completions/errors throughout this capture. This is
physical evidence for the fixed USB-to-CH568-to-Marvell diagnostic exchange
on port 2, while port 0 retains a physical SATA link. It does not yet establish
concurrent disk data transfer, file integrity or long-duration reliability.
The supplied excerpt is saved as `fixtures/open-basic-v22-ch568-status.usb.txt`.

The supplied CH568 source is a USB/SATA device mailbox implementation whose
historical READ64/READ4K/BATCH commands request arbitrary physical host memory.
V21 integrates only a fixed diagnostic protocol: PING (`0x1337`) and STATUS
(`0x1340`). The diagnostic Marvell handler neither accepts an address/range
argument nor maps host memory for these requests. Unknown commands and nonzero
argument fields are rejected. Ordinary host-owned AHCI disk DMA is unchanged.

Physical socket 1 is reserved for CH568; physical socket 0 remains a real disk.
AHCI PI is `0x8D` (disk ports 0/2/3 and management endpoint 7). Socket 1 is
absent from OS disk enumeration and from the host ATA poller. A positive ATA
model match for `CH568 MV9230 USB SATA MAILBOX` is required before service.
An ordinary disk or an absent peer leaves the private service disabled.

The service uses a separate port-1 command/FIS bank, local table at
`0x3006EA00` and 512-byte poll buffer at `0x3006EC00`. A nonblocking poller
performs F0/37 and sends fixed response bytes with F1/A5. Empty polls have a
cooldown; command timeout disables only this service without recycling an
active DMA buffer. No controller-wide or port-0 reset is initiated. Startup
IDENTIFY and its geometry buffer remain separate from runtime mailbox memory.

STATUS is 64 bytes, little-endian: magic `SD21`, version 21, chip ID, host GHC,
host PI, physical backend PI, service port, request count, four SSTS values,
port-0 issued/completed/error counters, and service error count. PING returns
the fixed chip ID and version. USB is an observation channel; UART remains
available as fallback and no UART commands are needed by the diagnostic client.

The CH568 3.1 diagnostic fork retains the original SATA PHY/SRST/IDENTIFY and
USB endpoints. Its USB parser accepts only `1337` and `status`; legacy
address/batch parsers are removed and queue functions disabled. It is a separate
source copy: the supplied CH568 3.0 tree remains untouched.

Build Marvell:

```
python tools/build_c_stage.py --template ../88.bin --output build/v21.bin --basic-boot-probe --no-option-rom --ch568-diagnostics
```

Validation:

```
python tools/emulate_ch568_diag.py
python tools/emulate_static_boot_test.py ../88.bin --basic-boot-probe --no-option-rom --ch568-diagnostics --stripped-stock-runtime
```

The first test executes ARM startup and the service with a modeled SATA peer,
including STATUS/PING during an outstanding port-0 write/read, exact disk data
readback, invalid-request rejection, and absent/wrong-identity peers. The second
runs the existing full-image disk regression with diagnostics enabled but no
physical CH568. The NDS32 companion is compiled and linked, with BSS ending at
`0x206640` and stack starting at `0x208000` (6592 bytes of separation). Its USB
and SATA interrupt state machines have not been run on hardware for this fork.
The host client parser and packaged libusb backend are checked locally.

The delivered images keep the legacy Option ROM disabled. OS installation/boot
from the controller, hot removal and reset during active service have not been
validated by these tests. Cold boot with CH568 on socket 1 and a test disk on
socket 0 is the next physical check.
