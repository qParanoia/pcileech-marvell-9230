
#include "host_frontend.h"
#include "host_command.h"
#include "punit_window.h"
#include "sata_port0.h"
#ifdef OPEN9230_CH568_DIAGNOSTICS
#include "ch568_diag.h"
#endif

#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

enum {
    HOST_PORT_COUNT = 0x80002800u,
    HOST_GHC = 0x80002804u,
    HOST_IS = 0x80002808u,
    HOST_PI = 0x8000280Cu,
    HOST_VERSION = 0x80002810u,
    HOST_PORT_BASE = 0x80002900u,
    HOST_IRQ_STATUS = 0x80003008u,
    HOST_IRQ_ENABLE = 0x8000300Cu,
    HOST_PORT_IRQ_BASE = 0x80003010u,
    MAX_VIRTUAL_PORTS = 8u,
    HOST_ISSUE_SHADOW = 0x8000C060u,
    HOST_PORT0_IS = 0x80002910u,
    HOST_PORT0_TFD = 0x80002920u,
    HOST_PORT0_SACT = 0x80002934u,
    HOST_PORT0_CI = 0x80002938u,
    HOST_INTERRUPT = 0x8000C084u,
    BACKEND_IS = 0x8000A808u,
    BACKEND_PORT0_IS = 0x8000A910u,
    BACKEND_PORT0_CI = 0x8000A938u,
    BACKEND_PORT0_SACT = 0x8000A934u,
    BACKEND_PORT0_SSTS = 0x8000A928u,
    BACKEND_PORT0_SIG = 0x8000A924u,
    BACKEND_PORT0_TFD = 0x8000A920u,
    DMA_BASE = 0x8000C000u,
    DMA_AUTOFETCH = 0x8000C044u,
};

static uint8_t host_seen;
static uint8_t host_pending;
struct basic_port_state {
    uint8_t seen, pending, opcode, canceled;
    uint8_t fetched[32];
    uint32_t slot, slot_mask;
    struct host_port_counters counters;
#ifdef OPEN9230_DMA_PROBE
    struct host_identify_probe probe;
    uint32_t previous_irq;
    uint8_t sctl_asserted;
#endif
};
static struct basic_port_state basic_ports[SATA_PHYSICAL_PORTS];
static uint32_t basic_port;
static uint32_t basic_next_port;
#define basic_seen (basic_ports[basic_port].seen)
#define basic_pending (basic_ports[basic_port].pending)
#define basic_canceled (basic_ports[basic_port].canceled)
#define basic_opcode (basic_ports[basic_port].opcode)
#define basic_last_fetched (basic_ports[basic_port].fetched)
#define basic_slot (basic_ports[basic_port].slot)
#define basic_slot_mask (basic_ports[basic_port].slot_mask)
#define BASIC_HOST_BASE (HOST_PORT_BASE + basic_port * 0x80u)
#define BASIC_HOST_RAM (0x30000000u + basic_port * 0x400u)
#define BASIC_HOST_FIS (0x30003000u + basic_port * 0x40u)
#define BASIC_BACKEND_SLOT (sata_port_slot_address(basic_port))
#define BASIC_BACKEND_FIS (sata_port_fis_address(basic_port))
#define BASIC_PORT_MASK (1u << basic_port)
static void host_fail_basic_slot(void);

#ifdef OPEN9230_DMA_PROBE
#define PUNIT_WINDOW1 0xD0020010u
#define identify_probe (basic_ports[basic_port].probe)
#define basic_previous_irq (basic_ports[basic_port].previous_irq)
#define basic_sctl_asserted (basic_ports[basic_port].sctl_asserted)

const struct host_identify_probe *host_frontend_identify_probe(void) {
    return &identify_probe;
}

static int basic_poll_selected_reset(void) {
    const uint32_t sctl = REG32(BASIC_HOST_BASE + 0x2Cu);
    const uint32_t irq = REG32(HOST_PORT_IRQ_BASE + basic_port * 8u);
    if ((sctl & 0xFu) == 1u) basic_sctl_asserted = 1u;
    const int latched_release = (irq & 0x1000u) &&
        irq != 0xFFFFFFFFu &&
        !(basic_previous_irq & 0x1000u) &&
        (REG32(HOST_GHC) & 0x80000000u) &&
        !(REG32(HOST_PORT0_CI + basic_port * 0x80u) & 1u);
    const int released = (sctl & 0xFu) == 0u &&
        (basic_sctl_asserted || latched_release);
    basic_previous_irq = irq;
    if (!released) return 0;
    basic_sctl_asserted = 0u;


    const uint32_t signature =
        (REG32(BACKEND_PORT0_SSTS + basic_port * 0x80u) & 0xFu) == 3u ?
        REG32(BACKEND_PORT0_SIG + basic_port * 0x80u) : 0xFFFFFFFFu;
    const uint32_t status = signature == 0x101u ?
        REG32(BACKEND_PORT0_SSTS + basic_port * 0x80u) : 0u;
    const uint32_t taskfile = signature == 0x101u ?
        REG32(BACKEND_PORT0_TFD + basic_port * 0x80u) : 0x7Fu;
    const uint32_t command = REG32(BASIC_HOST_BASE + 0x18u);
    REG32(HOST_PORT0_IS + basic_port * 0x80u) = 0u;
    REG32(BASIC_HOST_BASE + 0x18u) = command;
    REG32(BASIC_HOST_BASE + 0x24u) = signature;
    REG32(BASIC_HOST_BASE + 0x28u) = status;
    REG32(BASIC_HOST_BASE + 0x30u) = 0u;
    REG32(HOST_PORT0_SACT + basic_port * 0x80u) = 0xFFFFFFFFu;
    REG32(HOST_PORT0_CI + basic_port * 0x80u) = 0u;
    REG32(BASIC_HOST_BASE + 0x3Cu) = 0u;
    REG32(BASIC_HOST_BASE + 0x40u) = 0u;
    REG32(HOST_PORT0_TFD + basic_port * 0x80u) = taskfile;
    REG32(HOST_PORT_IRQ_BASE + basic_port * 8u) = 0x1000u;
    return 1;
}

int host_frontend_poll_port_reset(unsigned port) {
    if (port >= SATA_PHYSICAL_PORTS) return 0;
    const uint32_t previous = basic_port;
    basic_port = port;
    const int result = basic_poll_selected_reset();
    if (result) {
        basic_canceled = basic_pending;
        basic_seen = 0;
    }
    basic_port = previous;
    return result;
}

int host_frontend_poll_port0_reset(void) {
    return host_frontend_poll_port_reset(0);
}

static uint32_t probe_load32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
           ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static volatile uint8_t *probe_map(uint32_t low, uint32_t high, uint32_t size) {
    return punit_window_map(PUNIT_WINDOW1, 0x50000000u, low, high, size, 1000u);
}

static void probe_unmap(void) {
    punit_window_unmap(PUNIT_WINDOW1);
}


static int basic_fetch_host_slot(uint8_t fetched[32]) {
    const uint32_t clb = REG32(BASIC_HOST_BASE);
    const uint32_t low = clb + basic_slot * 32u;
    const uint32_t high = REG32(BASIC_HOST_BASE + 4u) + (low < clb);
    if (!clb || clb == UINT32_MAX || (clb & 0x1Fu)) return 0;
    volatile const uint8_t *mapped = probe_map(low, high, 16u);
    if (!mapped) return 0;
    for (unsigned i = 0; i < 16u; ++i) fetched[i] = mapped[i];
    probe_unmap();
    const uint32_t table_low = probe_load32(fetched + 8u);
    const uint32_t table_high = probe_load32(fetched + 12u);
    if ((!table_low && !table_high) || (table_low & 0x3Fu)) return 0;
    mapped = probe_map(table_low, table_high, 16u);
    if (!mapped) return 0;
    for (unsigned i = 0; i < 16u; ++i) fetched[16u + i] = mapped[i];
    probe_unmap();
    return 1;
}

static uint32_t host_logical_sector_bytes(void) {


    volatile const uint16_t *const identify =
        (volatile const uint16_t *)(uintptr_t)sata_port_identify_address(basic_port);
    if ((identify[106] & 0xD000u) != 0x5000u) return 512u;
    const uint32_t words = (uint32_t)identify[117] |
                           ((uint32_t)identify[118] << 16);
    return words >= 256u && words <= 32768u ? words * 2u : 512u;
}

static uint32_t host_expected_transfer_bytes(void) {
    const uint32_t opcode = basic_opcode;
    const uint32_t sectors = (uint32_t)basic_last_fetched[28] |
                             ((uint32_t)basic_last_fetched[29] << 8);
    switch (opcode) {
    case 0xECu:
        return 512u;
    case 0x25u:
    case 0x35u:
        return sectors * host_logical_sector_bytes();
    case 0xC8u:
    case 0xCAu:
        return (sectors & 0xFFu ? sectors & 0xFFu : 256u) *
               host_logical_sector_bytes();
    case 0x06u:
        return sectors * 512u;
    case 0xB0u:
        return (basic_last_fetched[19] == 0xD0u ||
                basic_last_fetched[19] == 0xD1u) ? 512u : 0u;
    default:
        return 0u;
    }
}

static int host_header_matches(volatile const uint32_t *header) {
    return header[0] == probe_load32(basic_last_fetched) &&
           header[2] == probe_load32(basic_last_fetched + 8u) &&
           header[3] == probe_load32(basic_last_fetched + 12u);
}


static void publish_host_prdbc(uint32_t physical_bytes, int failed) {
    struct host_identify_probe *probe = &identify_probe;
    const uint32_t expected = host_expected_transfer_bytes();
    const uint32_t clb_base = REG32(BASIC_HOST_BASE);
    const uint32_t clb_low = clb_base + basic_slot * 32u;
    const uint32_t clb_high = REG32(BASIC_HOST_BASE + 4u) + (clb_low < clb_base);
    probe->response_prdbc_status = 1u;
    probe->response_prdbc_bytes = 0u;
    probe->response_prdbc_backend = physical_bytes;
    probe->response_prdbc_before = 0u;
    probe->response_prdbc_readback = 0u;
    probe->response_prdbc_clb_low = clb_low;
    probe->response_prdbc_clb_high = clb_high;
    probe->response_prdbc_local = REG32((BASIC_HOST_RAM + 4u));
    probe->response_prdbc_fallback = 0u;
    if (!expected && !physical_bytes) return;
    uint32_t bytes = physical_bytes;
    if (expected && bytes > expected) bytes = expected;
    if (!bytes && !failed) bytes = expected;
    if (!bytes) return;


    if (!clb_low || clb_low == 0xFFFFFFFFu || (clb_low & 0x1Fu)) {
        probe->response_prdbc_status = 2u;
        return;
    }
    volatile uint8_t *mapped = probe_map(clb_low, clb_high, 16u);
    if (!mapped) {
        probe->response_prdbc_status = 3u;
        return;
    }
    volatile uint32_t *header = (volatile uint32_t *)(void *)mapped;
    if (!host_header_matches(header)) {
        probe_unmap();
        const uint32_t aligned_low = clb_low & ~0x3FFu;
        if (basic_slot || aligned_low == clb_low || !aligned_low) {
            probe->response_prdbc_status = 5u;
            return;
        }
        mapped = probe_map(aligned_low, clb_high, 16u);
        if (!mapped) {
            probe->response_prdbc_status = 3u;
            return;
        }
        header = (volatile uint32_t *)(void *)mapped;
        if (!host_header_matches(header)) {
            probe_unmap();
            probe->response_prdbc_status = 5u;
            return;
        }
        probe->response_prdbc_clb_low = aligned_low;
        probe->response_prdbc_fallback = 1u;
    }
    probe->response_prdbc_before = header[1];
    header[1] = bytes;
    probe->response_prdbc_readback = header[1];
    if (!basic_slot) REG32((BASIC_HOST_RAM + 4u)) = bytes;
    probe->response_prdbc_local = REG32((BASIC_HOST_RAM + 4u));
    probe->response_prdbc_bytes = bytes;
    probe->response_prdbc_status = probe->response_prdbc_readback == bytes ? 0u : 4u;
    probe_unmap();
}


static void publish_host_response_fis(uint32_t taskfile) {
    struct host_identify_probe *probe = &identify_probe;
    const uint32_t fb_low = REG32(BASIC_HOST_BASE + 0x08u);
    const uint32_t fb_high = REG32(BASIC_HOST_BASE + 0x0Cu);
    const uint32_t status = taskfile & 0xFFu;
    const uint32_t error = (taskfile >> 8) & 0xFFu;
    const uint32_t sdb = 0x000040A1u | (status << 16) | (error << 24);
    probe->response_fis_status = 1u;
    probe->response_fis_bus_low = fb_low;
    probe->response_fis_bus_high = fb_high;
    probe->response_fis_sdb = sdb;
    probe->response_fis_readback = 0u;
    REG32((BASIC_HOST_FIS + 0x38u)) = sdb;
    REG32((BASIC_HOST_FIS + 0x3Cu)) = 0u;
    if (!(REG32(BASIC_HOST_BASE + 0x18u) & 0x10u) ||
        !fb_low || fb_low == 0xFFFFFFFFu || (fb_low & 0xFFu)) {
        return;
    }
    volatile uint8_t *const mapped = probe_map(fb_low, fb_high, 0x60u);
    if (!mapped) {
        probe->response_fis_status = 2u;
        return;
    }
    volatile uint32_t *const rfis = (volatile uint32_t *)(void *)mapped;
    if (basic_opcode == 0xECu) {
        if ((REG32((BASIC_BACKEND_FIS + 0x20u)) & 0xFFu) == 0x5Fu) {
            for (unsigned i = 0; i < 5u; ++i) {
                rfis[(0x20u / 4u) + i] = REG32((BASIC_BACKEND_FIS + 0x20u) + 4u * i);
            }
        } else {
            rfis[0x20u / 4u] = 0x0058405Fu;
            for (unsigned i = 1; i < 4u; ++i) rfis[(0x20u / 4u) + i] = 0u;
            rfis[0x30u / 4u] = 512u;
        }
    }
    const uint32_t physical_d2h = REG32((BASIC_BACKEND_FIS + 0x40u));
    if ((physical_d2h & 0xFFu) == 0x34u &&
        ((physical_d2h >> 16) & 0xFFFFu) == (taskfile & 0xFFFFu)) {
        for (unsigned i = 0; i < 5u; ++i) {
            rfis[(0x40u / 4u) + i] = REG32((BASIC_BACKEND_FIS + 0x40u) + 4u * i);
        }
    } else {
        rfis[0x40u / 4u] = 0x00004034u | (status << 16) | (error << 24);
        for (unsigned i = 1; i < 5u; ++i) rfis[(0x40u / 4u) + i] = 0u;
    }
    rfis[0x58u / 4u] = sdb;
    rfis[0x5Cu / 4u] = 0u;
    probe->response_fis_readback = rfis[0x58u / 4u];
    probe->response_fis_status = probe->response_fis_readback == sdb ? 0u : 3u;
    probe_unmap();
}

static void probe_identify_dma(void) {
    struct host_identify_probe *probe = &identify_probe;
    probe->status = 1u;
    probe->ctba_low = probe_load32(basic_last_fetched + 8);
    probe->ctba_high = probe_load32(basic_last_fetched + 12);
    probe->data_low = 0;
    probe->data_high = 0;
    probe->data_bytes = 0;
    probe->prdbc = 0;
    probe->matched_bytes = 0;
    probe->host_word0 = 0;
    probe->local_word0 = 0;
    probe->host_model0 = 0;
    probe->local_model0 = 0;
    probe->host_capacity0 = 0;
    probe->local_capacity0 = 0;
    uint32_t entry_low = probe->ctba_low + 0x80u;
    uint32_t entry_high = probe->ctba_high + (entry_low < probe->ctba_low);
    if ((entry_low & 0xFFFFu) > 0xFFF0u) {
        probe->status = 2u;
        return;
    }
    volatile const uint8_t *entry = probe_map(entry_low, entry_high, 16u);
    if (!entry) {
        probe->status = 3u;
        return;
    }
    probe->data_low = REG32((uintptr_t)entry);
    probe->data_high = REG32((uintptr_t)entry + 4u);
    probe->data_bytes = (REG32((uintptr_t)entry + 12u) & 0x3FFFFFu) + 1u;
    probe_unmap();
    if (probe->data_bytes < 512u) {
        probe->status = 4u;
        return;
    }
    uint32_t clb_base = REG32(BASIC_HOST_BASE);
    uint32_t clb_low = clb_base + basic_slot * 32u;
    uint32_t clb_high = REG32(BASIC_HOST_BASE + 4u) + (clb_low < clb_base);
    if ((clb_low & 0xFFFFu) <= 0xFFF8u) {
        volatile const uint8_t *header = probe_map(clb_low, clb_high, 16u);
        if (header) {
            probe->prdbc = REG32((uintptr_t)header + 4u);
            probe_unmap();
        }
    }
    volatile const uint8_t *local =
        (volatile const uint8_t *)(uintptr_t)sata_port_identify_address(basic_port);
    uint32_t low = probe->data_low;
    uint32_t high = probe->data_high;
    for (uint32_t offset = 0; offset < 512u;) {
        volatile const uint8_t *source = probe_map(low, high, 512u - offset);
        if (!source) {
            probe->status = 5u;
            return;
        }
        uint32_t chunk = 0x10000u - (low & 0xFFFFu);
        if (chunk > 512u - offset) chunk = 512u - offset;
        for (uint32_t i = 0; i < chunk; ++i) {
            uint32_t index = offset + i;
            uint32_t host_byte = source[i];
            uint32_t local_byte = local[index];
            probe->matched_bytes += host_byte == local_byte;
            if (index < 4u) {
                probe->host_word0 |= host_byte << (8u * index);
                probe->local_word0 |= local_byte << (8u * index);
            } else if (index >= 54u && index < 58u) {
                probe->host_model0 |= host_byte << (8u * (index - 54u));
                probe->local_model0 |= local_byte << (8u * (index - 54u));
            } else if (index >= 200u && index < 204u) {
                probe->host_capacity0 |= host_byte << (8u * (index - 200u));
                probe->local_capacity0 |= local_byte << (8u * (index - 200u));
            }
        }
        probe_unmap();
        if (low > UINT32_MAX - chunk) ++high;
        low += chunk;
        offset += chunk;
    }
    probe->status = 0u;
}
#endif

uint32_t host_frontend_enable_irqs(void) {
    uint32_t count = (REG32(HOST_PORT_COUNT) & 0x1Fu) + 1u;
    if (count > MAX_VIRTUAL_PORTS) {
        count = MAX_VIRTUAL_PORTS;
    }
    REG32(HOST_IRQ_STATUS) = 0xFFFFFFFFu;
    REG32(HOST_IRQ_ENABLE) = 2u;
    for (uint32_t port = 0; port < count; ++port) {
        const uintptr_t pair = HOST_PORT_IRQ_BASE + port * 8u;
        REG32(pair) = 0xFFFFFFFFu;
        REG32(pair + 4u) = 0x104Fu;
    }
    return count;
}

uint32_t host_frontend_reset_registers(const struct host_port_reset ports[8],
                                       uint32_t count) {
    if (!ports || !count || count > MAX_VIRTUAL_PORTS) {
        return 0;
    }

    REG32(HOST_PORT_COUNT) = 0x80309F00u | (count - 1u);
    REG32(HOST_GHC) = 0;
    REG32(HOST_IS) = 0;
    REG32(HOST_PI) = (1u << count) - 1u;
    REG32(HOST_VERSION) = 0x00010200u;
    for (uintptr_t offset = 0x14u; offset <= 0x28u; offset += 4u) {
        REG32(HOST_PORT_COUNT + offset) = 0;
    }
    for (uint32_t port = 0; port < count; ++port) {
        const uintptr_t base = HOST_PORT_BASE + port * 0x80u;
        REG32(base + 0x14u) = 0;
        REG32(base + 0x10u) = 0;
        REG32(base + 0x18u) = ports[port].command;
        REG32(base + 0x24u) = ports[port].signature;
        REG32(base + 0x28u) = ports[port].sstatus;
        REG32(base + 0x30u) = 0;
        REG32(base + 0x34u) = 0xFFFFFFFFu;
        REG32(base + 0x38u) = 0;
        REG32(base + 0x3Cu) = 0;
        REG32(base + 0x40u) = 0;
        REG32(base + 0x20u) = ports[port].taskfile;
    }
    host_frontend_enable_irqs();
    REG32(HOST_GHC) = REG32(HOST_GHC) & ~1u;
    return count;
}

void host_frontend_init_dma_registers(void) {
    REG32(DMA_BASE + 0x04u) = 2u;
    REG32(DMA_BASE + 0x04u) = 0u;
    REG32(DMA_BASE + 0x50u) = 0x59000008u;
    REG32(DMA_BASE + 0x54u) = 0x20u;
    REG32(DMA_BASE + 0x08u) = 0x00060F50u;
    REG32(DMA_BASE + 0x0Cu) = 0u;
    REG32(DMA_BASE + 0x10u) = 0u;
    REG32(DMA_BASE + 0x10u) = 0x00011009u;
    REG32(DMA_BASE + 0x14u) = 0x00060EF4u;
    REG32(DMA_BASE + 0x18u) = 0u;
    REG32(DMA_BASE + 0x24u) = 0u;
    REG32(DMA_BASE + 0x24u) = 0x00011009u;
    REG32(DMA_BASE + 0x28u) = 0x00060F20u;
    REG32(DMA_BASE + 0x2Cu) = 0u;
    REG32(DMA_BASE + 0x38u) = 0u;
    REG32(DMA_BASE + 0x3Cu) = 0u;
    REG32(DMA_BASE + 0x04u) = 0x2149u;
    REG32(DMA_AUTOFETCH) = 0xDu;
}

uint32_t host_frontend_enable_autofetch(uint32_t port) {
    if (port >= MAX_VIRTUAL_PORTS) {
        return 0;
    }
    uint32_t value = REG32(DMA_AUTOFETCH) | (1u << (port + 4u));
    REG32(DMA_AUTOFETCH) = value;
    return value;
}

int host_frontend_poll_identify(void) {
    if (host_pending) {
        if ((REG32(BACKEND_PORT0_CI) | REG32(BACKEND_PORT0_SACT)) & 1u) {
            return 0;
        }
        host_pending = 0;
        if ((REG32(BACKEND_PORT0_TFD) & 1u) ||
            !(REG32(BACKEND_PORT0_IS) & 2u)) {
            return -3;
        }
        REG32(BACKEND_PORT0_IS) = 0xFFFFFFFFu;
        REG32(BACKEND_IS) = 1u;
        REG32(HOST_PORT0_CI) = 0xFFFFFFFEu;
        REG32(HOST_PORT0_IS) = 8u;
        REG32(HOST_INTERRUPT) = 1u;
        return 2;
    }
    if (!(REG32(HOST_ISSUE_SHADOW) & 1u)) {
        host_seen = 0;
        return 0;
    }
    if (host_seen) {
        return 0;
    }
    host_seen = 1;
    if ((REG32(BACKEND_PORT0_SSTS) & 0xFu) != 3u ||
        REG32(BACKEND_PORT0_SIG) != 0x101u ||
        ((REG32(BACKEND_PORT0_CI) | REG32(BACKEND_PORT0_SACT)) & 1u)) {
        return -1;
    }
    uint8_t fetched[32];
    uint8_t slot[64];
    volatile const uint8_t *const source = (volatile const uint8_t *)(uintptr_t)0x30000000u;
    volatile uint8_t *const destination = (volatile uint8_t *)(uintptr_t)0x3006B000u;
    for (unsigned i = 0; i < sizeof fetched; ++i) {
        fetched[i] = source[i];
    }
    if (host_build_identify_slot(fetched, slot)) {
        return -2;
    }
    for (unsigned i = 0; i < sizeof slot; ++i) {
        destination[i] = slot[i];
    }
    if (!sata_port0_ensure_command_engine()) {
        host_fail_basic_slot();
        return -4;
    }
    REG32(BACKEND_PORT0_IS) = 0xFFFFFFFFu;
    REG32(BACKEND_IS) = 1u;
    host_pending = 1;
    REG32(BACKEND_PORT0_CI) = 1u;
    return 1;
}

uint32_t host_frontend_basic_opcode(void) {
    return basic_opcode;
}

uint32_t host_frontend_basic_slot(void) {
    return basic_slot;
}

uint32_t host_frontend_basic_port(void) {
    return basic_port;
}

const struct host_port_counters *host_frontend_port_counters(unsigned port) {
    return port < SATA_PHYSICAL_PORTS ? &basic_ports[port].counters : 0;
}

void host_frontend_basic_reset_state(void) {
    for (basic_port = 0; basic_port < SATA_PHYSICAL_PORTS; ++basic_port) {
        const int inflight = basic_pending &&
            ((REG32(BACKEND_PORT0_CI + basic_port * 0x80u) |
              REG32(BACKEND_PORT0_SACT + basic_port * 0x80u)) & 1u);
        basic_seen = 0;
        basic_pending = (uint8_t)inflight;
        basic_canceled = (uint8_t)inflight;
        if (!inflight) {
            basic_opcode = 0;
            basic_slot = 0;
            basic_slot_mask = 1u;
        }
#ifdef OPEN9230_DMA_PROBE
        identify_probe.status = 0xFFFFFFFFu;
        basic_previous_irq = REG32(HOST_PORT_IRQ_BASE + basic_port * 8u);
        basic_sctl_asserted = 0;
#endif
    }
    basic_port = 0;
    basic_next_port = 0;
}

static void host_fail_basic_slot(void) {


    REG32((BASIC_HOST_FIS + 0x20u)) = 0x04514034u;
    for (unsigned i = 1; i < 4u; ++i) {
        REG32((BASIC_HOST_FIS + 0x20u) + i * 4u) = 0u;
    }
    REG32(HOST_INTERRUPT) = BASIC_PORT_MASK;
    REG32(HOST_PORT0_TFD + basic_port * 0x80u) = 0x451u;
    REG32(HOST_PORT0_CI + basic_port * 0x80u) = ~basic_slot_mask;
    REG32(HOST_PORT0_IS + basic_port * 0x80u) = 0x40000000u;
    REG32(HOST_IS) = REG32(HOST_IS) | BASIC_PORT_MASK;


    basic_seen = 0;
}

static int basic_poll_selected(void) {
    if (basic_pending) {
        if ((REG32(BACKEND_PORT0_CI + basic_port * 0x80u) | REG32(BACKEND_PORT0_SACT + basic_port * 0x80u)) & 1u) {
            return 0;
        }
        basic_pending = 0;
        if (basic_canceled) {
            basic_canceled = 0;
            basic_seen = 0;
            REG32(BACKEND_PORT0_IS + basic_port * 0x80u) = 0xFFFFFFFFu;
            REG32(BACKEND_IS) = BASIC_PORT_MASK;
            return 0;
        }
        const uint32_t backend_tfd = REG32(BACKEND_PORT0_TFD + basic_port * 0x80u) & 0xFFFFu;
        const uint32_t backend_is = REG32(BACKEND_PORT0_IS + basic_port * 0x80u);
        const int failed = (backend_tfd & 1u) || (backend_is & 0x40000000u) ||
                           !(backend_is & 3u);
#ifdef OPEN9230_DMA_PROBE
        if (basic_opcode == 0xECu && !failed) probe_identify_dma();
        publish_host_prdbc(REG32((BASIC_BACKEND_SLOT + 4u)), failed);
#endif
        const uint32_t host_port_is = failed ? 0x40000000u : 8u;
        const uint32_t response_tfd = failed && !(backend_tfd & 1u) ?
            0x451u : backend_tfd;
        if (failed) {


            const uint32_t fis0 = REG32((BASIC_BACKEND_FIS + 0x40u));
            if ((fis0 & 0xFFu) == 0x34u &&
                ((fis0 >> 16) & 0xFFu) == (response_tfd & 0xFFu)) {
                for (unsigned i = 0; i < 4u; ++i) {
                    REG32((BASIC_HOST_FIS + 0x20u) + i * 4u) = REG32((BASIC_BACKEND_FIS + 0x40u) + i * 4u);
                }
            } else {
                REG32((BASIC_HOST_FIS + 0x20u)) = 0x00004034u |
                    ((response_tfd & 0xFFu) << 16) |
                    ((response_tfd & 0xFF00u) << 16);
                for (unsigned i = 1; i < 4u; ++i) {
                    REG32((BASIC_HOST_FIS + 0x20u) + i * 4u) = 0u;
                }
            }
        }
#ifdef OPEN9230_DMA_PROBE
        publish_host_response_fis(response_tfd);
#endif
        REG32(BACKEND_PORT0_IS + basic_port * 0x80u) = 0xFFFFFFFFu;
        REG32(BACKEND_IS) = BASIC_PORT_MASK;
        REG32(HOST_PORT0_SACT + basic_port * 0x80u) = basic_slot_mask;
        REG32(HOST_INTERRUPT) = BASIC_PORT_MASK;
        REG32(HOST_PORT0_TFD + basic_port * 0x80u) = response_tfd;
        REG32(HOST_PORT0_CI + basic_port * 0x80u) = ~basic_slot_mask;
        REG32(HOST_PORT0_IS + basic_port * 0x80u) = host_port_is;
        REG32(HOST_IS) = REG32(HOST_IS) | BASIC_PORT_MASK;
        basic_seen = 0;
        return failed ? -3 : 2;
    }
#ifdef OPEN9230_DMA_PROBE
    if (!(REG32(BASIC_HOST_BASE + 0x18u) & 1u)) return 0;
#endif
    const uint32_t pending = REG32(HOST_PORT0_CI + basic_port * 0x80u) &
        (basic_port ? UINT32_MAX : REG32(HOST_ISSUE_SHADOW));
    if (!pending) {
        basic_seen = 0;
        return 0;
    }
    uint8_t fetched[32];
    uint8_t slot[64];
    basic_slot = 0;
    while (!(pending & (1u << basic_slot))) ++basic_slot;
    basic_slot_mask = 1u << basic_slot;
    volatile const uint8_t *const source = (volatile const uint8_t *)(uintptr_t)BASIC_HOST_RAM;
    volatile uint8_t *const destination = (volatile uint8_t *)(uintptr_t)BASIC_BACKEND_SLOT;
    if (!basic_slot && !basic_port) {
        for (unsigned i = 0; i < sizeof fetched; ++i) fetched[i] = source[i];
    } else {
#ifdef OPEN9230_DMA_PROBE
        if (!basic_fetch_host_slot(fetched)) {
            basic_opcode = 0;
            host_fail_basic_slot();
            return -5;
        }
#else
        host_fail_basic_slot();
        return -5;
#endif
    }
    if (basic_seen) {
        unsigned changed = 0;
        for (unsigned i = 0; i < sizeof fetched; ++i) {
            if (i < 4u || i >= 8u) {
                changed |= (unsigned)(fetched[i] != basic_last_fetched[i]);
            }
        }
        if (!changed) {
            return 0;
        }
    }
    basic_opcode = fetched[18];
    if ((REG32(BACKEND_PORT0_CI + basic_port * 0x80u) | REG32(BACKEND_PORT0_SACT + basic_port * 0x80u)) & 1u) {
        return 0;
    }
    basic_seen = 1;
    for (unsigned i = 0; i < sizeof fetched; ++i) {
        basic_last_fetched[i] = fetched[i];
    }
    if ((REG32(BACKEND_PORT0_SSTS + basic_port * 0x80u) & 0xFu) != 3u ||
        REG32(BACKEND_PORT0_SIG + basic_port * 0x80u) != 0x101u) {
        host_fail_basic_slot();
        return -1;
    }
    if (host_build_basic_slot(fetched, slot)) {
        host_fail_basic_slot();
        return -2;
    }
    for (unsigned i = 0; i < sizeof slot; ++i) {
        destination[i] = slot[i];
    }
    if (!sata_port_ensure_command_engine(basic_port)) {
        host_fail_basic_slot();
        return -4;
    }
    REG32(BACKEND_PORT0_IS + basic_port * 0x80u) = 0xFFFFFFFFu;
    REG32(BACKEND_IS) = BASIC_PORT_MASK;
    basic_pending = 1;
    REG32(BACKEND_PORT0_CI + basic_port * 0x80u) = 1u;
    return 1;
}

int host_frontend_poll_basic(void) {
#ifdef OPEN9230_DMA_PROBE
    const uint32_t count = SATA_PHYSICAL_PORTS;
#else
    const uint32_t count = 1u;
#endif
    const uint32_t previous = basic_port;
    for (unsigned tried = 0; tried < count; ++tried) {
        basic_port = basic_next_port;
        basic_next_port = (basic_next_port + 1u) % count;
#ifdef OPEN9230_CH568_DIAGNOSTICS
        if (basic_port == CH568_SERVICE_PORT) continue;
#endif
        const int event = basic_poll_selected();
        if (event) {
            struct host_port_counters *counters = &basic_ports[basic_port].counters;
            if (event == 1) ++counters->issued;
            if (event == 2 || event == -3) ++counters->completed;
            if (event < 0) ++counters->errors;
            return event;
        }
    }
    basic_port = previous;
    return 0;
}
