# Second board experiment: read known registers over UART

The initial `OPEN9230` probe has been confirmed on the revision-61 board.
`tools/build_diag.py` builds a second local hybrid image using the same exact
`88.bin` template and the open ARM source in `firmware/mmio_diag.s`:

```text
python tools/build_diag.py --template ../88.bin --output build/diag.bin
```

The program initializes UART0, prints a banner, reads three registers that the
vendor loader or firmware already reads, prints their raw 32-bit values in hex,
and stops. No SATA disk is needed.

```text
OPEN9230 DIAG
CHIP=????????
STRAP=????????
SPI0=????????
```

- `CHIP` reads `0xD0030000`. The loader and stock firmware use its upper 16
  bits to distinguish device IDs such as 9230; the full expected word is not
  yet known. The stock `rev: 61` value comes from a separate RAM byte at
  `0x04000028`, so do not infer the revision from the low half of `CHIP`.
- `STRAP` reads `0xD0071054`. The stock serial initialization uses bits 4–5 to
  decide whether to enable UART; the exact board value remains to be measured.
- `SPI0` reads `0xF8064000`, the start of the SPI mapping. Its first four bytes
  in the reference dump are `A5 A5 A5 A5`, so `A5A5A5A5` is expected if the
  mapping is still active after the loader.

The program also writes the same optional RAM marker as the first probe.
The owner booted the image on the spare SPI and received:

```text
OPEN9230 DIAG
CHIP=92301B4B
STRAP=0000002F
SPI0=A5A5A5A5
```

No further physical test is needed for these three reads. The next steps use
the offline Unicorn model documented in [emulator.md](emulator.md).
