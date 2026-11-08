# Physical SATA completion path in the reference image

This is a behavioral map for an independent driver. Addresses and control
flow were obtained from the local stock-image disassembly and the opt-in
Unicorn SSD fixture. Register values synthesized by the fixture are not
board measurements.

| Event | CPU address / register | Observed stock behavior |
| --- | --- | --- |
| Internal ATA issue | RAM `0x00004BAC` → `0x8000A938` | Sets one bit in port-0 command issue; slot 0 carries `0xEC` IDENTIFY, then slots 1 and 2 carry `0x25` READ DMA EXT. |
| Global interrupt | `0xD0020200` bit 0 | IRQ vector at RAM `0x000143B0` dispatches via the table at `0x040002B0`. The bit-0 callback is RAM `0x0000229C`. |
| Backend port interrupt | RAM `0x000060D4` / IDA `sub_36194` | Reads global backend status at `0x8000A808`, then port-0 interrupt status at `0x8000A910`, enabled mask at `0x8000A914`, and command issue at `0x8000A938`. |
| Command retirement | RAM `0x000060D4` / IDA `sub_36194` | Computes completed slots from the software active mask and cleared hardware issue bits, then calls the completion routine at RAM `0x00004224` (`sub_342E4` in IDA). |
| Waiting caller | RAM `0x00004BD8` onward / IDA `sub_34C98` | Waits for the internal command result and reports timeout or ATA failure if the completion path does not signal success. |

The address of the completion routine in the preceding table is the function
entry at RAM `0x00004224` (IDA `0x342E4`); its exact call sites vary inside
the port interrupt handler. The `0x8000A9xx` block is for physical port 0,
with a stride of `0x80` bytes per port in the observed initialization path.

The request for the first IDENTIFY command is at `0x3006D400` in this run.
Its word at offset `0x80` is `0x0006E081`, a tagged local SRAM address;
masking the low address tag bit and restoring the `0x30000000` RAM window
gives `0x3006E080`. Feeding a synthetic IDENTIFY sector there produces the
observed SSD, ATA major-version, rotation, and TRIM lines. The READ DMA EXT
requests carry a different tagged pointer (`...D9`), whose target is
`0x3006E0D8`, not `0x3006E0D0`: address bit 3 is significant. The stock
emulator leaves that memory intact. Overwriting it as a 512-byte sector
corrupted the ROM's
heap; successful completion without READ DMA payload transfer reproduces
`DISK0, DDF not found.` This is a control-flow checkpoint, not proof that the
metadata parser works with a real sector.

The fixture currently assumes successful commands: it sets the global and
per-port interrupt status bits, clears the issued slot bit, and enters the
stock IRQ vector with ARM IRQ mode state. Hardware-generated FIS contents,
DMA transfer mechanics, error status, interrupts under load, and timeouts
still need separate evidence before implementing a driver.

## Board measurements from the open polling path

C-stage v3 completed physical IDENTIFY on the owner's board with all CPU and
port IRQs masked. The port command issue bit cleared before the next UART
line; `PxIS` read `0x2`, `PxTFD` read `0x50`, and the global IRQ status read
zero. The 512-byte destination had been initialized to `0xA5` and contained
valid ATA IDENTIFY words after completion. The open IRQ handler's original
`PxIS & 1` completion test was therefore inconsistent with this observed
interrupt status; it is changed to test bit 1, but IRQ delivery itself has
not been validated on the board.

V4 prepared the first stock-style READ DMA EXT request:
slot 1 at `0x3006B040`, request table at `0x3006F100`, and a 512-byte SRAM
destination at `0x3006E0D8`. It reads only LBA 0. The descriptor and request
table match the stock Unicorn trace byte-for-byte. On the board, `CI` cleared,
`PxIS=1`, `PxTFD=0x50`, and 504 bytes changed in the incorrectly placed v4
inspection window (`0x3006E0D0..0x3006E2CF`). The untouched first eight bytes
support the corrected target offset of +8. V5 inspects the corrected target
and guards both edges. V4 stopped midway through the IRQ marker, so actual
CPU interrupt delivery remained unverified at that point. V5 reported all
512 bytes changed in the corrected destination, an `0xAA55` final word, and
intact pre/post guards. Its masked CPU phase observed global pending bit 0;
after unmasking, the open IRQ vector ran, recorded `PxIS=2` and cleared `CI`,
and returned to print a successful acknowledgment. The loader left SCTLR
high-vector bit `0x2000` set; v5 cleared it before using its own low vectors.
