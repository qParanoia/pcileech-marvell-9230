# First board experiment: prove control reaches open ARM code

`tools/build_probe.py` creates a 512 KiB local image using the user's original
dump as a template. It requires the analyzed dump's exact SHA-256. The first
160 bytes of `CODE1` are replaced by independently assembled ARM code. The
vendor autoload, loader, Option ROM, and remaining code and data remain
present. The generated file is ignored by Git.

The probe has an ARM vector table, stores `0x9230B007` at CPU address
`0x04001000`, initializes UART0 as observed in the reference firmware, sends
`OPEN9230` followed by CR/LF, then loops. The marker address is above the
vendor image's DATA1 range `0x04000000..0x04000368` and below the loader's
observed stack pointer `0x04004000`. The UART pins must already be enabled by
the board's power-up straps. The stock firmware produces a log on this UART
at 115200 8N1.

## Expected test

1. Keep the original SPI chip and program `build/probe.bin` into a spare chip.
2. Open the existing UART terminal at 115200 8N1 and boot the board with no
   SATA disks connected.
3. The board owner observed `OPEN9230` on the terminal. The normal vendor boot log is not
   expected: the probe replaces the first instructions executed by the main
   firmware.
4. If a repeat test does not show the message, restore the original chip and
   verify that its usual log still appears. Header fields beyond the segment
   table remain undocumented.
5. Restore the original SPI chip before normal disk use.

An optional second check uses JTAG to read `0x04001000` and expect
`0x9230B007`. The article reports JTAG pins TST2=TRST, TST3=TMS, TST4=TDI,
TST5=TCK, and TST6=TDO. A target-only OpenOCD configuration is in
`debug/88se9230-target.cfg`; the interface/adapter configuration depends on
the actual JTAG probe. The article reports TAP ID `0x140003d3`.

With an adapter configuration named `adapter.cfg`, the JTAG read would be:

```text
openocd -f adapter.cfg -f debug/88se9230-target.cfg -c "init; halt; mdw 0x04001000 1; shutdown"
```

Run it after powering the board with the spare SPI. The exact adapter file
must match the connected probe.

This experiment does not initialize AHCI or RAID and intentionally does not
make a functioning PCI storage device. Its outcome will decide the next
implementation step.
