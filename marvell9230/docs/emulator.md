# Offline ARM emulation

`tools/emulate_stock.py` runs the RAM segments from the exact local `88.bin`
in Unicorn. It maps the RAM and SPI image, then models enough 88SE9230 MMIO
to execute the no-disk startup path. It never writes to a real controller or
to the input file. `tools/compare_boot.py` compares its UART output with the
board owner's captured stock log in `fixtures/stock-no-disk.uart.txt`.

```text
python -m pip install -r requirements-dev.txt
python tools/compare_boot.py ../88.bin
python tools/compare_backend_dispatch.py ../88.bin
python tools/emulate_stock.py ../88.bin --steps 2000000
python tools/emulate_diag.py
```

Current comparison: **40 of 40 UART lines match** for the owner's no-disk
capture. The fixture specifies eight host virtual slots at `0x80002800` and
four physical backend ports at `0x8000A800`/`0x8000A80C`; the stock code then
maps the console to virtual port 7 as on the board. Boot reaches
`AHCI controller started.` in the model. This is a UART-output comparison,
not proof of functional SATA or RAID behavior.

The same MMIO fixture can run experimental images. For example,
`python tools/emulate_image.py build/diag.bin --steps 20000` reproduces the
board's measured `OPEN9230 DIAG` output. To record the stock image's MMIO
accesses, run `python tools/emulate_stock.py ../88.bin --steps 2000000
--mmio-trace build/stock-no-disk-mmio.json`. The trace includes the PC, access
size, address and observed/modelled value. Frequent timer, UART data, and SPI
data accesses are omitted to keep it manageable. See [host-registers.md](host-registers.md)
for register-window findings.

For the one-SSD path,
`python tools/compare_ssd_prefix.py ../88.bin` checks 37 captured UART lines
through `Start detect device ... sig 00000101` and confirms that stock code
issues IDENTIFY DEVICE. The model seeds a *hypothetical* port-0 status word
`0x133`, supplies the observed ATA signature, clears command-issue bit 0 for
the internal SRST, and skips calibrated busy-loop delays. The opt-in command
`python tools/compare_ssd_prefix.py ../88.bin --experimental-sata-io`
adds a synthetic SSD response and three synthetic SATA command completions.
It matches 55 UART checkpoints through the virtual-port and channel mapping.
See
[ssd-emulation.md](ssd-emulation.md).

The model handles the early interrupt timer, IDE FIFO completion, UART TX,
and a small set of SPI commands. SPI read command `0x14` returns words from
the input dump. The model uses measured `CHIP` and `STRAP` values and inferred
configuration values for the revision, eight host slots and four physical
ports. Unknown MMIO
pages are zero-filled and listed in the JSON report. This permits controlled
execution, but an exact UART log alone does not prove correct SATA, DMA,
interrupt, PCIe, RAID, or disk behavior. The SSD fixture currently models
only a successful command path without READ DMA payload transfer. Host PCIe traffic, error
handling, RAID creation, HyperDuo, Option ROM interaction, and real disk
timing remain outside its coverage.

QEMU can emulate an ARM CPU too, but the firmware expects 88SE9230-specific
memory and device behavior. A generic QEMU ARM machine would need a custom
device model for the same registers. Unicorn's hooks make the incremental
MMIO model here smaller and faster to develop. QEMU remains an option if a
full machine model becomes useful later.

Primary tool documentation: [Unicorn](https://github.com/unicorn-engine/unicorn)
and [QEMU system emulation](https://www.qemu.org/docs/master/system/introduction.html).
