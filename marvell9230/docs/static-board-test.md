# Static 88SE9230 board diagnostic V2

`build/static-board-test-v2.bin` runs automatically after power-on. The only
hardware test step is to flash the spare SPI and capture the whole UART log.
This image contains the original SPI loader and Option ROM with an open CODE1
diagnostic stage. It is not a complete replacement firmware.

Build and check offline:

```text
python tools/compare_open_host_reset.py ../88.bin
python tools/emulate_static_board_test.py ../88.bin
python tools/build_c_stage.py --template ../88.bin --output build/static-board-test-v2.bin --static-board-test
python tools/inspect_image.py build/static-board-test-v2.bin
```

The image is 512 KiB. SHA-256:
`06152071a924209e87c1c5fe78992c30a5adaaa83975892b3fa3a1ab981c19f6`.
Connect the disposable SSD to physical SATA port 0. Boot the PC from another
controller and capture UART at 115200 8N1 from power-on through
`STATIC_TEST_END`. If it never appears, capture the last printed line and
whether the board rebooted.

V2 repeats the verified physical IDENTIFY, read-only LBA-0 and CPU IRQ checks.
It then takes the host register snapshot, resets the eight virtual ports if
the PC has not configured them yet, initializes the frontend IRQ masks and DMA
registers, and enables auto-fetch for virtual port 0. These register writes
match the stock firmware trace for both empty ports and one linked SSD. The
program records GHC, command-list base, port command/issue, issue shadow,
frontend IRQ status, and auto-fetch at changes and three progress points. It
handles up to four host GHC reset requests. A single host IDENTIFY request may
reach physical port 0 when all host prerequisites are observed. No ATA write
command is issued to the SSD.

`HOST_RESULT=NOT_READY` means the PC did not configure the observed host AHCI
registers during the bounded window. `NO_ISSUE` means the registers were
configured but no host command was seen. `PENDING`, `COMPLETE`, and `ERROR_...`
describe the single-command experiment. `COMPLETE` alone does not prove that
the PC received DMA data or accepted the disk. RAID, HyperDuo, and full AHCI
operation remain unfinished.

Board follow-up: with V2 and a disk attached, the PC did not reach BIOS;
without the disk it did. The V2 diagnostic stops servicing commands after
`STATIC_TEST_END`, and its virtual completion sequence omits a stock-observed
write to global host `IS`. Keep this image as a regression fixture, not as a
working host firmware.
