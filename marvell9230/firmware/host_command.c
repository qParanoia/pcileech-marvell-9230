
#include "host_command.h"

static uint32_t load32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
           ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static void store32(uint8_t *bytes, uint32_t value) {
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8);
    bytes[2] = (uint8_t)(value >> 16);
    bytes[3] = (uint8_t)(value >> 24);
}

int host_build_identify_slot(const uint8_t fetched[32], uint8_t backend_slot[64]) {
    if (!fetched || !backend_slot) {
        return -1;
    }
    const uint32_t flags = load32(fetched);
    const uint32_t ctba_low = load32(fetched + 8);
    const uint32_t ctba_high = load32(fetched + 12);
    if ((flags & 0x1Fu) != 5u || (flags >> 16) != 1u ||
        (flags & 0x60u) != 0u || (ctba_low & 0x3Fu) != 0u ||
        fetched[16] != 0x27u || (fetched[17] & 0x80u) == 0u ||
        fetched[18] != 0xECu) {
        return -2;
    }
    for (unsigned i = 0; i < 64u; ++i) {
        backend_slot[i] = 0;
    }
    store32(backend_slot, flags);


    store32(backend_slot + 8, ctba_low | 4u);
    store32(backend_slot + 12, ctba_high);
    for (unsigned i = 0; i < 16u; ++i) {
        backend_slot[0x20u + i] = fetched[16u + i];
    }
    return 0;
}

int host_build_basic_slot(const uint8_t fetched[32], uint8_t backend_slot[64]) {
    if (!fetched || !backend_slot) {
        return -1;
    }
    const uint32_t flags = load32(fetched);
    const uint32_t prdt_length = flags >> 16;


    const uint32_t max_prdt_length = 257u;
    const uint32_t ctba_low = load32(fetched + 8);
    const uint32_t ctba_high = load32(fetched + 12);
    const uint8_t opcode = fetched[18];
    const int write_dma = opcode == 0x35u || opcode == 0xCAu || opcode == 0x06u;
    const int read_dma = opcode == 0xECu || opcode == 0x25u || opcode == 0xC8u;
    const int no_data = opcode == 0xEAu || opcode == 0xE7u ||
                        opcode == 0xEFu || opcode == 0xF5u ||
                        opcode == 0xE5u || opcode == 0xE1u;
    const int data_command = write_dma || read_dma;


    const int forbidden = opcode == 0u || opcode == 0x60u ||
                          opcode == 0x61u || opcode == 0xA0u ||
                          opcode == 0xA1u;
    if ((flags & 0x1Fu) != 5u || (flags & 0xA0u) != 0u ||
        (data_command && (!!(flags & 0x40u) != write_dma)) ||
        (opcode == 0xB0u && (flags & 0x40u) && fetched[19] != 0xD6u) ||
        ((!data_command && prdt_length == 0u) && (flags & 0x40u)) ||
        (data_command ? (prdt_length == 0u || prdt_length > max_prdt_length) :
         no_data ? prdt_length != 0u : prdt_length > max_prdt_length) ||
        (ctba_low & 0x3Fu) != 0u ||
        fetched[16] != 0x27u || (fetched[17] & 0x8Fu) != 0x80u ||
        forbidden ||
        ((opcode == 0x25u || opcode == 0x35u) &&
         fetched[28] == 0u && fetched[29] == 0u)) {
        return -2;
    }
    for (unsigned i = 0; i < 64u; ++i) {
        backend_slot[i] = 0;
    }
    store32(backend_slot, flags);
    store32(backend_slot + 8, ctba_low | 4u);
    store32(backend_slot + 12, ctba_high);
    for (unsigned i = 0; i < 16u; ++i) {
        backend_slot[0x20u + i] = fetched[16u + i];
    }
    return 0;
}
