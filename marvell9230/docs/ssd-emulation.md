# One-SSD path in the offline model

The board owner's stock UART capture with an SSD on physical port 0 supplies
an independent checkpoint for disk discovery. The capture begins mid-line,
so `fixtures/stock-one-ssd-prefix.uart.txt` reconstructs its first firmware
version line from the complete no-disk capture. The remaining lines through
the device signature are taken from the SSD capture.

Run:

```text
python tools/compare_ssd_prefix.py ../88.bin
python tools/compare_ssd_prefix.py ../88.bin --experimental-sata-io
```

With only link status modeled, the stock image matches **37 UART lines** through:

```text
port 0 pmp 15 srst successfully.
Start detect device @ port 0 pmp 0 sig 00000101.
```

It also observes stock code writing bit 0 to `0x8000A938` from RAM PC
`0x00004BAC` after constructing a Register FIS beginning `27 80 EC`; the
`0xEC` command is IDENTIFY DEVICE. The opt-in synthetic I/O fixture supplies
a 512-byte ATA IDENTIFY response and injects a SATA IRQ through the ROM's
actual vector and IRQ0 handler. The ROM parses the response, identifies the
device as an SSD, and reports TRIM. It then issues two `0x25` READ DMA EXT
commands while checking RAID metadata. The fixture completes both without
transferring disk payload, so the existing RAM data contains no DDF signature.
This reaches **55 UART checkpoints** through
`Console device 12 mapping to ch 1, dev:1`, compared with the owner's SSD
capture; the device model/serial line is intentionally variable.

The IRQ0 callback at RAM `0x0000229C` calls the physical-port interrupt
handler at `0x000060D4` (IDA `sub_36194`). It reads the global backend
status at `0x8000A808`, port-0 status at `0x8000A910`, and port-0 command
issue at `0x8000A938`. For the first internal command, its request lives at
`0x3006D400`; the tagged local data pointer at request offset `0x80`
resolves to `0x3006E080` in this run. The later READ DMA EXT request has a
different tag; the model leaves its target memory intact. Treating that
tagged pointer as a plain 512-byte destination corrupted the ROM's heap in
an earlier experiment.

The host-driven lines after device mapping (AHCI disable/enable, host reset,
Option ROM UI) still require a PCIe/host transaction model. The synthetic
IDENTIFY payload, absent READ DMA payloads, IRQ status, and completion timing are
emulator inputs; they are **not** measurements of the physical SSD or
proof that a replacement firmware handles real disk I/O.

See [the physical SATA command path](sata-command-path.md) for the IRQ and
command-retirement control flow that this experiment exposed.

The synthetic status word `0x133` at `0x8000A928` is sufficient to reproduce
the stock `early post spd: 30` and link-present path. It is an emulator input,
not a direct measurement of the board register. `0x00000101` at
`0x8000A924` is the ATA signature reported by the board. Clearing bit 0 of
`0x8000A938` on an internal-command poll models completion only for the SRST
step. The model uses `--fast-delays` to skip timer busy loops; it does not
claim accurate elapsed time.

The offsets `+0x24`, `+0x28`, and `+0x38` align with the standard AHCI
PxSIG, PxSSTS, and PxCI register layout, respectively. The Marvell backend
also uses proprietary controls, so that alignment alone does not establish
full AHCI semantics. See the [Intel AHCI 1.3.1 specification](https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/serial-ata-ahci-spec-rev1-3-1.pdf)
and the local [host register map](host-registers.md).
