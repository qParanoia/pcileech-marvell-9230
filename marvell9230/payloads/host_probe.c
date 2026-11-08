

#include <stdint.h>

#define REG8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

static void tx(uint8_t byte) {
    while (!(REG8(0xD0072014u) & 0x20u)) {
    }
    REG8(0xD0072000u) = byte;
}

static void puts(const char *text) {
    while (*text) {
        tx((uint8_t)*text++);
    }
}

static void hex32(uint32_t value) {
    static const char digits[] = "0123456789ABCDEF";
    for (int shift = 28; shift >= 0; shift -= 4) {
        tx((uint8_t)digits[(value >> shift) & 15u]);
    }
}

static void report(uint32_t address) {
    puts("MMIO ");
    hex32(address);
    tx('=');
    hex32(REG32(address));
    puts("\r\n");
}

__attribute__((section(".text.entry"), used)) void payload_entry(void) {
    static const uint32_t addresses[] = {
        0x80002800u, 0x80002804u,
        0x80003008u, 0x8000300Cu, 0x80003010u, 0x80003014u,
        0x80002910u, 0x80002914u, 0x80002918u, 0x80002920u,
        0x80002924u, 0x80002928u, 0x80002930u, 0x80002934u,
        0x80002938u, 0x8000293Cu, 0x80002940u,
        0x8000A800u, 0x8000A804u, 0x8000A808u, 0x8000A80Cu,
    };
    puts("OPEN9230 HOST-PROBE V1\r\n");
    for (unsigned i = 0; i < sizeof addresses / sizeof addresses[0]; ++i) {
        report(addresses[i]);
    }
    puts("HOST-PROBE DONE\r\n");
}
