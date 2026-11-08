
#include "console_identify.h"
#include "punit_window.h"

#include <stddef.h>
#include <stdint.h>

#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

enum {
    CONSOLE_PORT = 0x80002C80u,
    CONSOLE_SHADOW = 0x8000C07Cu,
    CONSOLE_FETCH = 0x30001C00u,
    CONSOLE_FIS_SCRATCH = 0x300031F8u,
    PUNIT_WINDOW1 = 0xD0020010u,
    PUNIT_WINDOW1_CPU = 0x50000000u,
};


static const uint16_t identify_packet[256] = {
    [0] = 0x8340,
    [10] = 0x0048, [11] = 0x4B44, [12] = 0x5032, [13] = 0x3231,
    [14] = 0x3531, [15] = 0x3657, [16] = 0x4C20, [17] = 0x2020,
    [18] = 0x2020, [19] = 0x2020, [20] = 0x3453, [21] = 0x0080,
    [23] = 0x312E, [24] = 0x3039, [25] = 0x2020, [26] = 0x2020,
    [27] = 0x4D41, [28] = 0x5256, [29] = 0x454C, [30] = 0x4C20,
    [31] = 0x5649, [32] = 0x5254, [33] = 0x5541, [34] = 0x4C4C,
    [35] = 0x2020, [36] = 0x2020, [37] = 0x2020, [38] = 0x2020,
    [39] = 0x2020, [40] = 0x2020, [41] = 0x2020, [42] = 0x2020,
    [43] = 0x2020, [44] = 0x2020, [45] = 0x2020, [46] = 0x2020,
    [49] = 0x0F00, [50] = 0x4001, [51] = 0x0200, [52] = 0x0200,
    [53] = 0x0006, [64] = 0x0003, [65] = 0x0078, [66] = 0x0078,
    [67] = 0x0078, [68] = 0x0078, [76] = 0x0602, [78] = 0x0040,
    [79] = 0x0040, [80] = 0x00FC, [81] = 0x0021, [82] = 0x0218,
    [83] = 0x4000, [84] = 0x4000, [85] = 0x0218, [87] = 0x4000,
    [88] = 0x101F,
};

static uint8_t management_reply[0x250];
static uint8_t management_ready;
static uint8_t basic_ui_session;
static uint32_t console_opcode;
static uint32_t console_packet_code;
static uint32_t console_status;
static uint32_t console_slot;
static uint32_t console_slot_mask = 1u;
static uint32_t console_header[4];

uint32_t console_last_opcode(void) { return console_opcode; }
uint32_t console_last_packet_code(void) { return console_packet_code; }
uint32_t console_last_status(void) { return console_status; }
uint32_t console_last_slot(void) { return console_slot; }

const uint16_t *console_identify_words(void) {
    return identify_packet;
}

void console_identify_reset(void) {
    management_ready = 0;
    basic_ui_session = 0;
    console_slot = 0;
    console_slot_mask = 1u;
}

static volatile uint8_t *window_map(uint32_t low, uint32_t high, uint32_t size) {
    return punit_window_map(PUNIT_WINDOW1, PUNIT_WINDOW1_CPU,
                            low, high, size, 100000u);
}

static void window_unmap(void) {
    punit_window_unmap(PUNIT_WINDOW1);
}

static int read_prdt(uint32_t table_low, uint32_t table_high,
                     uint32_t *data_low, uint32_t *data_high, uint32_t *length) {
    uint32_t prdt_low = table_low + 0x80u;
    uint32_t prdt_high = table_high;
    if (prdt_low < table_low) {
        ++prdt_high;
    }
    if ((prdt_low & 0xFFFFu) > 0xFFF0u) {
        return -2;
    }
    volatile uint8_t *ptr = window_map(prdt_low, prdt_high, 16u);
    if (!ptr) {
        return -3;
    }
    volatile uint32_t *entry = (volatile uint32_t *)(uintptr_t)ptr;
    *data_low = entry[0];
    *data_high = entry[1];
    *length = (entry[3] & 0x3FFFFFu) + 1u;
    window_unmap();
    return 0;
}

static int copy_to_host(uint32_t low, uint32_t high, const uint8_t *source,
                        uint32_t count) {
    while (count) {
        uint32_t chunk = 0x10000u - (low & 0xFFFFu);
        if (chunk > count) {
            chunk = count;
        }
        volatile uint8_t *dest = window_map(low, high, chunk);
        if (!dest) {
            return -1;
        }
        for (uint32_t i = 0; i < chunk; ++i) {
            dest[i] = source[i];
        }
        window_unmap();
        source += chunk;
        count -= chunk;
        if (low > UINT32_MAX - chunk) {
            ++high;
        }
        low += chunk;
    }
    return 0;
}

static int copy_from_host(uint32_t low, uint32_t high, uint8_t *destination,
                          uint32_t count) {
    if (low & 1u) {
        volatile const uint8_t *source = (volatile const uint8_t *)(uintptr_t)
            (0x30040000u | (low & ~1u));
        for (uint32_t i = 0; i < count; ++i) destination[i] = source[i];
        return 0;
    }
    while (count) {
        uint32_t chunk = 0x10000u - (low & 0xFFFFu);
        if (chunk > count) chunk = count;
        volatile uint8_t *source = window_map(low, high, chunk);
        if (!source) return -1;
        for (uint32_t i = 0; i < chunk; ++i) destination[i] = source[i];
        window_unmap();
        destination += chunk;
        count -= chunk;
        if (low > UINT32_MAX - chunk) ++high;
        low += chunk;
    }
    return 0;
}

static void complete_console_command(int check_condition) {
    REG32(CONSOLE_FIS_SCRATCH) = 0;
    REG32(CONSOLE_FIS_SCRATCH + 4u) = 0;
    REG32(CONSOLE_PORT + 0x34u) = console_slot_mask;
    REG32(0x8000C084u) = 0x80u;
    REG32(CONSOLE_PORT + 0x20u) = check_condition ? 0x451u : 0x50u;
    REG32(CONSOLE_PORT + 0x38u) = ~console_slot_mask;
    REG32(CONSOLE_PORT + 0x10u) = check_condition ? 0x40000008u : 8u;
    REG32(0x80002808u) = REG32(0x80002808u) | 0x80u;
}

static int service_packet(const uint8_t cdb[16], uint32_t data_low,
                          uint32_t data_high, uint32_t length,
                          uint32_t *transferred) {
    *transferred = 0;
    static const uint8_t inquiry[44] = {
        0x03, 0x80, 0x00, 0x32, 0x27, 0, 0, 0,
        'M', 'a', 'r', 'v', 'e', 'l', 'l', ' ',
        'C', 'o', 'n', 's', 'o', 'l', 'e', ' ',
        ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ',
        '1', '.', '0', '1', 0, 0x80, 0, 0, 'M', 'R', 'V', 'L'
    };
    static const uint8_t request_sense[19] = {
        0xF0, 0, 0, 0, 0, 0, 0, 8
    };
    static const uint8_t configuration[32] = {
        0, 0, 0, 0x18, 0, 0, 0, 0,
        0, 0, 3, 4, 0, 8, 0, 0,
        0, 1, 0x0B, 8, 0, 0, 0, 2,
        1, 0, 0, 0, 0, 0, 0, 0
    };
    static const uint8_t mode_sense[32] = {
        0x00, 0x56, 0x70, 0, 0, 0, 0, 0,
        0x2A, 0x4E, 0x3F, 0x37, 0xF1, 0x73, 0x29, 0x23,
        0x1B, 0x90, 0x01, 0, 0x07, 0xD0, 0x1B, 0x90,
        0, 0, 0x1B, 0x90, 0x16, 0x0C, 0, 0x01
    };
    const uint8_t *output = NULL;
    uint32_t output_length = 0;
    console_packet_code = cdb[0];
    console_status = 0;
    switch (cdb[0]) {
    case 0x00: case 0x1B: case 0x1E:
        break;
    case 0x03:
        output = request_sense; output_length = sizeof request_sense; break;
    case 0x12:
        output = inquiry; output_length = sizeof inquiry; break;
    case 0x46:
        output = configuration; output_length = 28u; break;
    case 0x5A:
        if (cdb[2] != 0x2Au && cdb[2] != 0x3Fu) return 1;
        output = mode_sense; output_length = sizeof mode_sense; break;
    case 0x1D: {
        if (length > sizeof management_reply || length < 0x19u) return -11;
        if (copy_from_host(data_low, data_high, management_reply, length)) return -12;
        *transferred = length;
        if (management_reply[0] != 0xE0u) return -13;
        management_reply[0x18u] = 0;
        uint8_t command = management_reply[8];
        console_packet_code |= (uint32_t)command << 8;
        if (command == 0xFDu && management_reply[0x3Cu] == 0xA4u &&
            length >= 0x5Au) {
            uint32_t seconds = ((uint32_t)management_reply[0x56u] << 16) |
                               ((uint32_t)management_reply[0x57u] << 24) |
                               management_reply[0x58u] |
                               ((uint32_t)management_reply[0x59u] << 8);
            REG32(0x04000240u) = seconds;
            *(volatile uint8_t *)(uintptr_t)0x0400023Cu = (seconds != 0u);
        } else if (command == 0xF3u && management_reply[9] == 3u &&
                   management_reply[0x17u] == 1u && length >= 0x50u) {
            uint32_t index = management_reply[0x3Eu] |
                             ((uint32_t)management_reply[0x3Fu] << 8);
            uint32_t detected = 0;
            for (uint32_t port = 0; port < 4u; ++port) {
                uint32_t base = 0x8000A900u + port * 0x80u;
                if ((REG32(base + 0x28u) & 0xFu) == 3u &&
                    REG32(base + 0x24u) == 0x101u) {
                    if (detected == index) {
                        management_reply[0x42u] = 1u;
                        management_reply[0x44u] = 0xFFu;
                        management_reply[0x45u] = 0xFFu;
                        management_reply[0x4Fu] = 3u;
                    }
                    ++detected;
                }
            }
            if (index >= detected) {
                management_reply[0x18u] = 0x37u;
                console_status = 0x37u;
            }
        } else if (command == 0xE1u && management_reply[9] == 0x10u) {


            switch (management_reply[10]) {
            case 1u:
                console_status = basic_ui_session ? 0u : 0xFFu;
                break;
            case 3u:
                basic_ui_session = (management_reply[11] & 3u) != 0u;
                break;
            case 6u: case 7u: case 8u: case 9u:
                break;
            default:
                console_status = 7u;
                break;
            }
            management_reply[0x18u] = (uint8_t)console_status;
        } else {
            management_reply[0x18u] = 7u;
            console_status = 7u;
        }
        management_reply[0] = 0xE1u;
        for (uint32_t i = length; i < sizeof management_reply; ++i) {
            management_reply[i] = 0;
        }
        management_ready = 1;
        break;
    }
    case 0x1C:
        if (cdb[2] != 0xE1u || !management_ready) return 1;
        output = management_reply;
        output_length = sizeof management_reply;
        break;
    default:
        return 1;
    }
    if (output && length) {
        if (output_length > length) output_length = length;
        if (data_low & 1u) {
            volatile uint8_t *dest = (volatile uint8_t *)(uintptr_t)
                (0x30040000u | (data_low & ~1u));
            for (uint32_t i = 0; i < output_length; ++i) dest[i] = output[i];
        } else if (copy_to_host(data_low, data_high, output, output_length)) {
            return -16;
        }
        *transferred = output_length;
    }
    return 0;
}

static int console_read_command(uint32_t fetched[8]) {
    if (!console_slot) {
        volatile const uint32_t *source =
            (volatile const uint32_t *)(uintptr_t)CONSOLE_FETCH;
        for (unsigned i = 0; i < 8u; ++i) fetched[i] = source[i];
        return 0;
    }
    const uint32_t clb = REG32(CONSOLE_PORT);
    const uint32_t low = clb + console_slot * 32u;
    const uint32_t high = REG32(CONSOLE_PORT + 4u) + (low < clb);
    if (!clb || clb == UINT32_MAX || (clb & 0x1Fu)) return -20;
    if (copy_from_host(low, high, (uint8_t *)fetched, 16u)) return -21;
    if ((!fetched[2] && !fetched[3]) || (fetched[2] & 0x3Fu)) return -22;
    return copy_from_host(fetched[2], fetched[3], (uint8_t *)(fetched + 4), 16u) ? -23 : 0;
}


static void console_publish_completion(uint32_t transferred, int failed) {
    const uint32_t clb = REG32(CONSOLE_PORT);
    const uint32_t low = clb + console_slot * 32u;
    const uint32_t high = REG32(CONSOLE_PORT + 4u) + (low < clb);
    if (clb && clb != UINT32_MAX && !(clb & 0x1Fu)) {
        volatile uint32_t *mapped = (volatile uint32_t *)(void *)window_map(low, high, 16u);
        if (mapped) {
            if (mapped[0] == console_header[0] && mapped[2] == console_header[2] &&
                mapped[3] == console_header[3]) mapped[1] = transferred;
            window_unmap();
        }
    }
    const uint32_t fb = REG32(CONSOLE_PORT + 8u);
    if (!(REG32(CONSOLE_PORT + 0x18u) & 0x10u) || !fb ||
        fb == UINT32_MAX || (fb & 0xFFu)) return;
    volatile uint32_t *rfis = (volatile uint32_t *)(void *)window_map(
        fb, REG32(CONSOLE_PORT + 0x0Cu), 0x60u);
    if (!rfis) return;
    rfis[0x40u / 4u] = failed ? 0x04514034u : 0x00504034u;
    for (unsigned i = 1; i < 5u; ++i) rfis[0x40u / 4u + i] = 0u;
    rfis[0x58u / 4u] = failed ? 0x045140A1u : 0x005040A1u;
    rfis[0x5Cu / 4u] = 0u;
    window_unmap();
}

int console_identify_poll(void) {
    const uint32_t ci = REG32(CONSOLE_PORT + 0x38u);


    const uint32_t pending = ci & (REG32(CONSOLE_SHADOW) | ~1u);
    if (!(REG32(CONSOLE_PORT + 0x18u) & 1u)) return 0;
    if (!pending) return 0;
    console_slot = 0;
    while (!(pending & (1u << console_slot))) ++console_slot;
    console_slot_mask = 1u << console_slot;
    console_opcode = 0;
    console_packet_code = 0;
    console_status = 0;
    for (unsigned i = 0; i < 4u; ++i) console_header[i] = 0;
    uint32_t fetched[8];
    uint32_t transferred = 0;
    int result = console_read_command(fetched);
    if (result) goto complete;
    for (unsigned i = 0; i < 4u; ++i) console_header[i] = fetched[i];
    const uint32_t flags = fetched[0];
    const uint32_t fis = fetched[4];
    const uint32_t opcode = (fis >> 16) & 0xFFu;
    console_opcode = opcode;
    if ((flags & 0x1Fu) != 5u || (fis & 0x0000FFFFu) != 0x8027u) {
        result = -24;
        goto complete;
    }


    if (opcode == 0xEFu && !(flags >> 16)) goto complete;
    if (opcode != 0xA1u && opcode != 0xA0u) {
        result = -25;
        goto complete;
    }
    uint32_t data_low = 0, data_high = 0, length = 0;
    if ((flags >> 16) == 1u) {
        result = read_prdt(fetched[2] & ~0x3Fu, fetched[3], &data_low, &data_high, &length);
        if (result) goto complete;
    } else if ((flags >> 16) || opcode == 0xA1u) {
        result = -26;
        goto complete;
    }
    if (opcode == 0xA1u) {
        if (length > sizeof identify_packet) length = sizeof identify_packet;
        if (data_low & 1u) {
            volatile uint8_t *dest = (volatile uint8_t *)(uintptr_t)(0x30040000u | (data_low & ~1u));
            const uint8_t *source = (const uint8_t *)identify_packet;
            for (uint32_t i = 0; i < length; ++i) dest[i] = source[i];
        } else if (copy_to_host(data_low, data_high, (const uint8_t *)identify_packet, length)) {
            result = -5;
            goto complete;
        }
        transferred = length;
    } else {
        uint8_t cdb[16];
        const uint32_t table_low = fetched[2] & ~0x3Fu;
        const uint32_t cdb_low = table_low + 0x40u;
        if (copy_from_host(cdb_low, fetched[3] + (cdb_low < table_low), cdb, sizeof cdb)) {
            result = -6;
            goto complete;
        }
        result = service_packet(cdb, data_low, data_high, length, &transferred);
        if (result > 0) console_status = 1u;
    }
complete:
    if (result < 0) console_status = (uint32_t)result;
    const int failed = result < 0 || console_status == 1u;
    console_publish_completion(transferred, failed);
    complete_console_command(failed);
    return result < 0 ? result : 1;
}
