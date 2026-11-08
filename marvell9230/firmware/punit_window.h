
#ifndef OPEN9230_PUNIT_WINDOW_H
#define OPEN9230_PUNIT_WINDOW_H

#include <stddef.h>
#include <stdint.h>

#define PUNIT_REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))


static inline volatile uint8_t *punit_window_map(
    uint32_t register_base, uint32_t cpu_base, uint32_t low, uint32_t high,
    uint32_t size, unsigned busy_limit) {
    if (!size) return NULL;
    while (PUNIT_REG32(register_base) & 0x20u) {
        PUNIT_REG32(register_base) = 0u;
        if (!--busy_limit) return NULL;
    }

    uint32_t size_code = 0u;
    uint32_t mask;
    for (;;) {
        mask = 0xFFFFu | (size_code << 16);
        const uint32_t offset = low & mask;
        if (size - 1u <= mask - offset) break;
        size_code = (size_code << 1) | 1u;
        if (size_code >= 0x10000u) return NULL;
    }

    PUNIT_REG32(register_base + 4u) = cpu_base;
    PUNIT_REG32(register_base + 8u) = low & ~mask;
    PUNIT_REG32(register_base + 12u) = high;
    PUNIT_REG32(register_base) = 0x5923u | (size_code << 16);
    (void)PUNIT_REG32(register_base);
    return (volatile uint8_t *)(uintptr_t)(cpu_base | (low & mask));
}

static inline void punit_window_unmap(uint32_t register_base) {
    PUNIT_REG32(register_base) = 0u;
}

#endif
