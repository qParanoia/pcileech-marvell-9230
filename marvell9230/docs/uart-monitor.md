# Resident UART monitor and RAM payloads

C-stage v6 adds a monitor to the open CODE1 stage. After the startup SATA
diagnostic completes, it prints `OPEN9230 MONITOR READY` and accepts commands
at 115200 8N1. With no disk it enters the monitor immediately. The monitor is
designed to keep later diagnostic iterations off the SPI flash: a payload can
be checked and run from SRAM, then return to the monitor.

The commands are ASCII, uppercase, and terminated by Enter:

| Command | Action |
| --- | --- |
| `?` | Show command syntax. |
| `H` | Print a selected read-only host/backend register snapshot. |
| `Rxxxxxxxx` | Read one aligned 32-bit word at eight-digit hexadecimal address `xxxxxxxx` from whitelisted RAM/MMIO ranges. |
| `Ullllllllcccccccc` | Receive exactly `llllllll` raw bytes into `0x30070000`, verifying CRC-32 `cccccccc`. Length must be 4–65536 and a multiple of four. |
| `X` | Run the last successfully uploaded ARM-state payload at `0x30070000`; print `EXEC_RETURN` if it returns. |

The `--experimental-frontend` image also accepts `F`: it arms the single
host-IDENTIFY experiment once, then prints `HOST_EXPERIMENT_ARMED`,
`HOST_FRONTEND_PORTS`, and (if port 0 is linked) `HOST_AUTOFETCH`.
Before `F`, this image runs the same physical SATA diagnostics and monitor
as the default build. A power cycle disarms it. `R8000C044` reads the
auto-fetch control word; the read-only whitelist includes `0x8000C000`–
`0x8000C0FC`.

For `U`, the monitor replies `UPLOAD_READY llllllll` before the raw bytes and
`UPLOAD_OK` or `UPLOAD_BAD_CRC` afterward. It discards execution permission
when a new upload starts or CRC fails. `X` will then answer `ERR NO_PAYLOAD`.
The monitor has no arbitrary register-write command. An uploaded payload is
executable code, so the supplied host probe is deliberately read-only.

Build everything from the project directory:

```text
python tools/build_c_stage.py --template ../88.bin --output build/c-stage-v6.bin
python tools/build_host_probe.py
python tools/emulate_c_stage.py ../88.bin
```

The 504-byte `build/host-probe.payload.bin` has CRC-32 `9FD2D213` in the
current build. It prints selected host and backend MMIO words and returns. The
payload ABI is a no-argument ARM function at `0x30070000`, called in supervisor
mode with the monitor's stack. It should return with `bx lr` and must not
assume initialized `.data` or `.bss`. `payloads/payload.ld` enforces those
constraints for the supplied example. Before the call, the monitor drains
UART, drains the CPU write buffer, and invalidates the instruction cache. The
board's measured SCTLR has the data cache disabled.

## First board check

1. Flash `build/c-stage-v6.bin` to the spare SPI and boot with the disposable
   disk on port 0. Capture the full startup UART log through
   `OPEN9230 MONITOR READY`.
2. Send `?` followed by Enter. Expect the `COMMANDS` line.
3. Send `H` followed by Enter. Expect `HOST_BEGIN`, register lines, and
   `HOST_END`.
4. Send the host probe as a binary file. In a terminal capable of binary file
   send, type `U000001F89FD2D213` and Enter, wait for
   `UPLOAD_READY 000001F8`, send `build/host-probe.payload.bin` with binary
   mode and no text conversion, then wait for `UPLOAD_OK`. Type `X` and Enter;
   expect `OPEN9230 HOST-PROBE V1`, `HOST-PROBE DONE`, and `EXEC_RETURN`.

Alternatively, close the serial terminal and use the uploader from the
Windows machine holding the UART adapter:

```text
py -m pip install -r requirements-uart.txt
py tools/uart_upload.py --port COM4 --image build/host-probe.payload.bin
```

Replace `COM4` with the actual port. The uploader sends `?`, waits for the
monitor, transfers the image with CRC verification, runs it, and prints the
result. Copy the script, requirements file, and payload to the UART-connected
PC if this workspace is on a different computer.

The code path and UART protocol have passed Unicorn tests, including a valid
payload return and a bad-CRC rejection. UART reception and RAM execution have
not yet been tested on the physical board.
