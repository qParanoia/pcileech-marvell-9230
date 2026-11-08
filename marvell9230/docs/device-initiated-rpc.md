# Device-initiated RPC over SATA

## Goal

A special device on a physical SATA port should be able to notify the 88SE9230
that work is available.  The controller then fetches a request such as method
ID `1337` (`0x539`), invokes an approved firmware function with that argument,
and returns a result to the device.  Host-PC memory access is not required;
request and response buffers may remain in the controller's local SRAM.

This is similar to the extension described in the Habr article
["Reversing and improving a SATA controller"](https://habr.com/ru/articles/532672/).
That implementation replaced the stock idle-task entry with an injected ARM
loop and called existing firmware functions through fixed function pointers.

## Stock-firmware evidence

The stock physical-port interrupt handler is raw-image function `0x36194`
(runtime `0x000060D4`).  Its Set Device Bits branch starts at raw `0x362D0`.
When `PxIS.SDBS` (bit 3) is set, the handler:

1. reads `PxSNTF` at physical-port register offset `0x3C`;
2. writes the value back to acknowledge the notification bits;
3. calls raw function `0x32388`, which posts a port-specific event to the
   stock scheduler;
4. separately computes ordinary command completions from the software-active
   mask and `PxCI`/`PxSACT`.

Consequently, the notification path is not inherently dependent on an active
command slot.  A controlled Unicorn run injected `PxIS=8`, a Set Device Bits
FIS in the backend RFIS area and `PxCI=PxSACT=0`; the stock IRQ dispatcher
entered the physical-port handler and acknowledged the event.  This is static
and emulated software evidence, not yet a real-link measurement.

The behavior matches AHCI 1.3.1 section 10.11.  A device may send an
asynchronous Set Device Bits FIS with the Interrupt and Notification flags set
while the port is idle.  The host is then expected to interrogate the device
to learn the reason.  This provides a device-initiated doorbell, not an
arbitrary device-initiated ATA command or bulk DMA transfer.

## Recommended wire protocol

Do not encode method `1337` directly in `PxSNTF`.  `PxSNTF` is a notification
bit field, and the SActive field in a Set Device Bits FIS participates in NCQ
accounting.  Reusing either as an RPC payload risks corrupting the controller's
normal port state.

Use a two-stage exchange instead:

```text
special device                         88SE9230
      |                                    |
      |-- SDB FIS, I=1, N=1 -------------->|  doorbell
      |                                    |  IRQ: acknowledge and queue work
      |<-- VENDOR_READ_REQUEST -------------|  issued after IRQ returns
      |-- request header + arguments ------>|
      |                                    |  validate and dispatch method 1337
      |<-- VENDOR_WRITE_RESPONSE ------------|
      |-- command completion -------------->|
```

A minimal request header should contain a magic value, protocol version,
sequence number, method ID, argument length, response capacity and integrity
check.  A response should repeat the sequence number and contain status,
result length, result data and an integrity check.  Sequence numbers make
retries after a link or controller reset unambiguous.

## Firmware dispatch

The disk must select a small allowlist entry, never supply a raw ARM address.
Conceptually:

```c
static int dispatch(uint32_t method, const void *args, uint32_t size,
                    void *reply, uint32_t *reply_size) {
    switch (method) {
    case 1337:
        return rpc_1337(args, size, reply, reply_size);
    default:
        return RPC_NO_SUCH_METHOD;
    }
}
```

`rpc_1337` may call a known stock function through a typed function pointer,
provided its real ABI and prerequisites have been recovered.  The target may
be ARM or Thumb; an odd stock address is a Thumb entry and must be reached via
an interworking call such as compiler-generated `BLX`.  The wrapper must know:

- which arguments are passed in `r0` through `r3` and on the stack;
- the return convention and clobbered registers;
- required global objects, locks, heap and scheduler state;
- whether the function may sleep, enqueue work or complete asynchronously;
- whether it may issue commands on the same SATA port.

The SATA interrupt handler must only acknowledge the notification and enqueue
an RPC task.  Fetching the request or calling the selected function from the
IRQ context can deadlock if the function waits on the same port, requires an
enabled interrupt, acquires a scheduler lock or takes significant time.

## Integration choices

### Minimal stock patch

This is closest to the Habr experiment and the shortest path to a proof of
concept.  Preserve the stock initialization, scheduler and SATA services;
inject an open RPC worker into an unused region; then hook the asynchronous
notification event consumer or install a task from that event.  Existing
stock functions are most likely to work in this environment because their
global state has been initialized.  The resulting SPI image remains a hybrid
vendor image rather than fully open firmware.

### Current open stage

The open V19 stage can implement the same protocol without touching host-PC
RAM, but currently services one physical backend port and does not initialize
the stock RTOS and its global objects.  It can safely dispatch open functions.
Calling arbitrary preserved CODE2/CODE3 functions is not safe merely because
their bytes and entry addresses still exist: complex functions may depend on
stock state that V19 never created.

For a fully open implementation the required milestones are:

1. bring up physical SATA port 1 with its own descriptor, RFIS and state;
2. enable and verify `PxIS.SDBS`/`PxSNTF` handling while `PxCI=0`;
3. defer notification processing to a worker outside IRQ context;
4. implement request-read and response-write vendor commands;
5. add an allowlisted dispatcher and wrappers for each target function;
6. test sequence retries, malformed requests, resets and simultaneous traffic
   on the ordinary disk;
7. verify the real SDB notification from the special device or FPGA on the
   physical link.

## Current conclusion

The architecture is feasible.  The 88SE9230 hardware and stock firmware have
the required device-initiated notification path.  The notification itself is
only a doorbell; method `1337`, arguments and results should travel through
normal controller-initiated vendor data commands.  Reusing arbitrary stock
functions is practical in a minimal stock patch after their ABI and state
requirements are verified.  In the current independent open stage, functions
with stock-runtime dependencies must first be reimplemented or supplied with
their required initialization.
