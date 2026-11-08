
#include "ch568_diag.h"
#include "host_frontend.h"
#include "punit_window.h"
#include "sata_port0.h"

#define REG32(a) (*(volatile uint32_t *)(uintptr_t)(a))
enum {
    TABLE = 0x3006EA00u,
    POLL_DATA = 0x3006EC00u,


    STAGING = 0x30004000u,
    STAGING_BYTES = 0x10000u,


    WINDOW_REGS = 0xD0020000u,
    WINDOW_CPU = 0x40000000u,
    MAILBOX_MAGIC = 0x314D4843u,
    DIAG_MAGIC = 0x31324453u,
    CMD_PING = 0x1337u,
    CMD_READ64 = 0x1338u,
    CMD_READ4K_FIS = 0x1339u,
    CMD_READ4K_DMA = 0x133Au,
    CMD_READ_BATCH = 0x133Bu,
    CMD_STATUS = 0x1340u,
    CMD_READ_LINEAR = 0x1341u,
    CMD_SET_MAP = 0x1342u,
    BATCH_MAX_PAGES = 16u,
    LINEAR_MAX_PAGES = 128u,
    MAILBOX_LBA_READ4K = 0x7F0u,
    MAILBOX_LBA_BATCH = 0x7E0u,
    MAILBOX_LBA_LINEAR = 0x7D0u,
};
static uint32_t ready;
static uint32_t pending;
static uint32_t age;
static uint32_t cooldown;
static uint32_t ack_chunks;
static uint32_t next_chunk;
static uint32_t reply[16];
static uint32_t requests;
static uint32_t errors;


#define MAP_MAX_RANGES 8u
static uint32_t map_count;
static uint32_t map_low[MAP_MAX_RANGES];
static uint32_t map_high[MAP_MAX_RANGES];
static uint32_t map_end_low[MAP_MAX_RANGES];
static uint32_t map_end_high[MAP_MAX_RANGES];

static uint32_t write_lba;
static uint32_t write_sectors;
static uint32_t write_bytes;


static uint32_t write_direct_low;
static uint32_t write_direct_high;
static uint32_t window_held;

uint32_t ch568_diag_ready(void) { return ready; }

void ch568_diag_init(void) {


    static const char model[] = "CH568 MV9230 USB SATA MAILBOX";
    volatile const uint8_t *id =
        (volatile const uint8_t *)sata_port_identify_address(CH568_SERVICE_PORT);
    ready = 0;
    map_count = 0;
    pending = age = cooldown = ack_chunks = next_chunk = requests = errors = 0;
    write_lba = write_sectors = write_bytes = 0;
    write_direct_low = write_direct_high = 0;
    window_held = 0;
    punit_window_unmap(WINDOW_REGS);
    if ((sata_port_status(CH568_SERVICE_PORT) & 15u) != 3u ||
        sata_port_signature(CH568_SERVICE_PORT) != 0x101u ||
        (REG32(sata_port_base(CH568_SERVICE_PORT) + 0x38u) & 1u)) return;
    for (unsigned i = 0; i < sizeof model - 1u; ++i) {
        if (id[54u + (i ^ 1u)] != (uint8_t)model[i]) return;
    }
    ready = 1;
}


static int stage_window_page(uint32_t low, uint32_t high, uint32_t offset) {
    volatile const uint8_t *mapped =
        punit_window_map(WINDOW_REGS, WINDOW_CPU, low, high, 0x1000u, 1000u);
    if (!mapped) return -1;
    volatile uint8_t *destination = (volatile uint8_t *)(uintptr_t)(STAGING + offset);
    if ((low & 3u) == 0u) {
        for (unsigned i = 0; i < 0x1000u; i += 4u)
            *(volatile uint32_t *)(uintptr_t)(destination + i) =
                *(const volatile uint32_t *)(uintptr_t)(mapped + i);
    } else {
        for (unsigned i = 0; i < 0x1000u; ++i) destination[i] = mapped[i];
    }
    punit_window_unmap(WINDOW_REGS);
    return 0;
}

static void arm_memory_write(uint32_t lba, uint32_t sectors, uint32_t bytes) {
    write_lba = lba;
    write_sectors = sectors;
    write_bytes = bytes;
    write_direct_low = write_direct_high = 0;
}

static void arm_memory_write_direct(uint32_t lba, uint32_t sectors,
                                    uint32_t bytes, uint32_t host_high,
                                    uint32_t host_low) {
    write_lba = lba;
    write_sectors = sectors;
    write_bytes = bytes;
    write_direct_high = host_high;
    write_direct_low = host_low;
    window_held = 0;
}

static void release_window(void) {
    if (window_held) {
        punit_window_unmap(WINDOW_REGS);
        window_held = 0;
    }
    write_direct_low = write_direct_high = 0;
}

static int issue(void) {
    const uintptr_t base = sata_port_base(CH568_SERVICE_PORT);
    if ((REG32(base + 0x38u) | REG32(base + 0x34u)) & 1u) return 0;
    if (!sata_port_ensure_command_engine(CH568_SERVICE_PORT)) return -1;
    volatile uint8_t *slot = (volatile uint8_t *)sata_port_slot_address(CH568_SERVICE_PORT);
    const int ack = ack_chunks != 0u;
    const int write = !ack && write_bytes != 0u;
    const int direct = write && (write_direct_low | write_direct_high) != 0u;
    volatile uint8_t *table = (volatile uint8_t *)(uintptr_t)TABLE;
    for (unsigned i = 0; i < 64u; ++i) slot[i] = 0;
    for (unsigned i = 0; i < 0x90u; ++i) table[i] = 0;
    table[0] = 0x27u;
    table[1] = 0x80u;
    if (ack) {
        table[2] = 0xF1u;
        table[3] = 0xA5u;
        static const uint8_t fields[8] = {4, 5, 6, 8, 9, 10, 12, 13};
        const uint8_t *bytes = (const uint8_t *)reply + next_chunk * 8u;
        for (unsigned i = 0; i < 8u; ++i) table[fields[i]] = bytes[i];
        REG32((uintptr_t)slot) = 5u;
    } else if (write) {


        table[2] = 0x35u;
        table[4] = (uint8_t)write_lba;
        table[5] = (uint8_t)(write_lba >> 8);
        table[6] = (uint8_t)(write_lba >> 16);
        table[12] = (uint8_t)write_sectors;
        table[13] = (uint8_t)(write_sectors >> 8);
        if (direct) {


            REG32(TABLE + 0x80u) = write_direct_low;
            REG32(TABLE + 0x84u) = write_direct_high;
            REG32(TABLE + 0x8Cu) = write_bytes - 1u;
            REG32((uintptr_t)slot) = 0x10045u;
        } else {
            REG32(TABLE + 0x80u) = (STAGING & 0xFFFFFFu) | 1u;
            REG32(TABLE + 0x8Cu) = write_bytes - 1u;
            REG32((uintptr_t)slot) = 0x10045u;
        }
    } else {
        table[2] = 0xF0u;
        table[3] = 0x37u;
        table[12] = 1u;
        REG32(TABLE + 0x80u) = (POLL_DATA & 0xFFFFFFu) | 1u;
        REG32(TABLE + 0x8Cu) = 511u;
        for (unsigned i = 0; i < 512u; i += 4u) REG32(POLL_DATA + i) = 0;
        REG32((uintptr_t)slot) = 0x10005u;
    }
    REG32((uintptr_t)slot + 8u) = ((uint32_t)(uintptr_t)table & 0xFFFFFFu) | 1u;
    for (unsigned i = 0; i < 16u; ++i) slot[0x20u + i] = table[i];
    REG32(base + 0x10u) = 0xFFFFFFFFu;
    REG32(0x8000A808u) = 1u << CH568_SERVICE_PORT;
    pending = ack ? 2u : (write ? 3u : 1u);
    age = 0;
    REG32(base + 0x38u) = 1u;
    return 1;
}

static void status_reply(void) {
    const struct host_port_counters *p0 = host_frontend_port_counters(0);
    reply[0] = DIAG_MAGIC;
    reply[1] = 24u;
    reply[2] = REG32(0xD0030000u);
    reply[3] = REG32(0x80002804u);
    reply[4] = REG32(0x8000280Cu);
    reply[5] = REG32(0x8000A80Cu);
    reply[6] = CH568_SERVICE_PORT;
    reply[7] = requests;
    for (unsigned p = 0; p < 4u; ++p) reply[8u + p] = sata_port_status(p);
    reply[12] = p0->issued;
    reply[13] = p0->completed;
    reply[14] = p0->errors;
    reply[15] = errors;
}

static int address_allowed(uint32_t low, uint32_t high, uint32_t size) {
    if (!map_count) return 1;
    const uint64_t start = ((uint64_t)high << 32) | low;
    for (unsigned i = 0; i < map_count; ++i) {
        const uint64_t range_start = ((uint64_t)map_high[i] << 32) | map_low[i];
        const uint64_t range_end = ((uint64_t)map_end_high[i] << 32) | map_end_low[i];
        if (start >= range_start && start + size <= range_end && start + size >= start) {
            return 1;
        }
    }
    return 0;
}


static void dispatch(uint32_t command, uint32_t a, uint32_t b) {
    if (command == CMD_PING && !a && !b) {
        ++requests;
        reply[0] = REG32(0xD0030000u);
        reply[1] = 24u;
        ack_chunks = 1;
        next_chunk = 0;
    } else if (command == CMD_STATUS && !a && !b) {
        ++requests;
        status_reply();
        ack_chunks = 8;
        next_chunk = 0;
    } else if (command == CMD_READ64) {
        if (!address_allowed(b, a, 64u)) {
            ++errors;
            return;
        }
        volatile const uint8_t *mapped =
            punit_window_map(WINDOW_REGS, WINDOW_CPU, b, a, 64u, 1000u);
        if (!mapped) {
            ++errors;
            return;
        }
        for (unsigned i = 0; i < 64u; ++i) ((uint8_t *)reply)[i] = mapped[i];
        punit_window_unmap(WINDOW_REGS);
        ++requests;
        ack_chunks = 8;
        next_chunk = 0;
    } else if (command == CMD_READ4K_DMA) {
        if (!address_allowed(b, a, 0x1000u)) {
            ++errors;
            return;
        }
        if (stage_window_page(b, a, 0u)) {
            ++errors;
            return;
        }
        ++requests;
        arm_memory_write(MAILBOX_LBA_READ4K, 8u, 0x1000u);
    } else if (command == CMD_READ_BATCH) {

        if (!a || a > BATCH_MAX_PAGES) {
            ++errors;
            return;
        }
        for (unsigned i = 0; i < a; ++i) {
            const uint32_t low = REG32(POLL_DATA + 16u + i * 8u);
            const uint32_t high = REG32(POLL_DATA + 20u + i * 8u);
            if (!address_allowed(low, high, 0x1000u)) {
                ++errors;
                return;
            }
            if (stage_window_page(low, high, i * 0x1000u)) {
                ++errors;
                return;
            }
        }
        ++requests;
        arm_memory_write(MAILBOX_LBA_BATCH, a * 8u, a * 0x1000u);
    } else if (command == CMD_SET_MAP) {

        if (!a || a > MAP_MAX_RANGES || b) {
            ++errors;
            return;
        }
        for (unsigned i = 0; i < a; ++i) {
            map_low[i] = REG32(POLL_DATA + 16u + i * 16u);
            map_high[i] = REG32(POLL_DATA + 20u + i * 16u);
            map_end_low[i] = REG32(POLL_DATA + 24u + i * 16u);
            map_end_high[i] = REG32(POLL_DATA + 28u + i * 16u);
        }
        map_count = a;
        ++requests;
        reply[0] = 0x4D414350u;
        reply[1] = map_count;
        ack_chunks = 1;
        next_chunk = 0;
    } else if (command == CMD_READ_LINEAR) {


        const uint32_t pages = REG32(POLL_DATA + 16u);
        const uint32_t total = pages << 12u;

        if (!pages || pages > LINEAR_MAX_PAGES ||
            b > 0xFFFFFFFFu - total) {
            ++errors;
            return;
        }
        if (!address_allowed(b, a, total)) {
            ++errors;
            return;
        }
        ++requests;
        arm_memory_write_direct(MAILBOX_LBA_LINEAR, pages * 8u, total, a, b);
    } else {


        ++errors;
    }
}


static uint32_t recover_streak;

static void recover_service_port(void) {
    const uintptr_t base = sata_port_base(CH568_SERVICE_PORT);
    ++recover_streak;
    pending = 0;
    ack_chunks = next_chunk = 0;
    write_bytes = 0;
    release_window();
    REG32(base + 0x14u) = 0u;
    REG32(base + 0x18u) = REG32(base + 0x18u) & ~0x1Fu;
    unsigned remaining = 2000000u;
    while ((REG32(base + 0x18u) & 0xC000u) && --remaining) {
    }
    if (recover_streak >= 2u) {
        const uint32_t control = REG32(0x8000A804u);
        REG32(0x8000A804u) = control & ~0x80000002u;
        for (volatile unsigned delay = 0; delay < 20000u; ++delay) {
        }
        REG32(0x8000A804u) = control | 0x80000002u;
        for (volatile unsigned delay = 0; delay < 20000u; ++delay) {
        }
        for (unsigned port = 0; port < SATA_PHYSICAL_PORTS; ++port) {
            (void)sata_port_ensure_command_engine(port);
        }
    }
    (void)sata_port_ensure_command_engine(CH568_SERVICE_PORT);
    REG32(base + 0x10u) = 0xFFFFFFFFu;
    REG32(0x8000A808u) = 1u << CH568_SERVICE_PORT;
    cooldown = 1024u;
}

int ch568_diag_poll(void) {
    const uintptr_t base = sata_port_base(CH568_SERVICE_PORT);
    if (!ready) return 0;
    if (pending) {
        if ((REG32(base + 0x38u) | REG32(base + 0x34u)) & 1u) {
            if (++age < 200000u) return 0;
            ++errors;
            recover_service_port();
            return -2;
        }
        const unsigned completed = pending;
        pending = 0;
        recover_streak = 0;
        if ((REG32(base + 0x20u) & 1u) ||
            !(REG32(base + 0x10u) & 3u) ||
            (REG32(base + 0x10u) & 0x40000000u) ||
            (completed == 1u &&
             REG32(sata_port_slot_address(CH568_SERVICE_PORT) + 4u) != 512u) ||
            (completed == 3u &&
             REG32(sata_port_slot_address(CH568_SERVICE_PORT) + 4u) != write_bytes)) {
            ++errors;
            ack_chunks = next_chunk = 0;
            write_bytes = 0;
            release_window();
            cooldown = 1024u;
            return -2;
        }
        REG32(base + 0x10u) = 0xFFFFFFFFu;
        REG32(0x8000A808u) = 1u << CH568_SERVICE_PORT;
        if (completed == 2u) {
            if (++next_chunk == ack_chunks) ack_chunks = next_chunk = 0;
        } else if (completed == 3u) {
            write_bytes = 0;
            release_window();
        } else if (REG32(POLL_DATA) == MAILBOX_MAGIC) {
            dispatch(REG32(POLL_DATA + 4u), REG32(POLL_DATA + 8u),
                     REG32(POLL_DATA + 12u));
        }
        cooldown = (ack_chunks || write_bytes) ? 0u : 128u;
    }
    if (cooldown) { --cooldown; return 0; }
    return issue();
}
