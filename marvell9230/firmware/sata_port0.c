
#include "sata_port0.h"

#define REG32(address) (*(volatile const uint32_t *)(uintptr_t)(address))

enum {
    BACKEND_BASE = 0x8000A800u,
    PORT0_BASE = 0x8000A900u,
};

struct sata_port0_snapshot sata_port0_probe(void) {
    struct sata_port0_snapshot result;
    result.backend_ports = (REG32(BACKEND_BASE) & 0x1Fu) + 1u;
    result.backend_bitmap = REG32(BACKEND_BASE + 0x0Cu);
    result.sstatus = REG32(PORT0_BASE + 0x28u);
    result.signature = REG32(PORT0_BASE + 0x24u);
    return result;
}

uint32_t sata_port_status(unsigned port) {
    if (port >= 4u) {
        return 0;
    }
    return REG32(PORT0_BASE + port * 0x80u + 0x28u);
}

uint32_t sata_port_signature(unsigned port) {
    if (port >= 4u) {
        return 0;
    }
    return REG32(PORT0_BASE + port * 0x80u + 0x24u);
}

int sata_port0_ata_ready(const struct sata_port0_snapshot *port) {
    return (port->backend_bitmap & 1u) &&
           (port->sstatus & 0xFu) == 3u &&
           port->signature == 0x00000101u;
}

void sata_port0_prepare_identify(void) {
    sata_port_prepare_identify(0);
}

void sata_port_prepare_identify(unsigned port) {
    if (port >= SATA_PHYSICAL_PORTS) return;
    volatile uint8_t *const slot = (volatile uint8_t *)(uintptr_t)sata_port_slot_address(port);
    volatile uint8_t *const table = (volatile uint8_t *)(uintptr_t)0x3006D400u;
    volatile uint8_t *const data = (volatile uint8_t *)(uintptr_t)sata_port_identify_address(port);
    for (unsigned i = 0; i < 0x40u; ++i) {
        slot[i] = 0;
    }
    for (unsigned i = 0; i < 0x90u; ++i) {
        table[i] = 0;
    }
    volatile uint8_t *const extension = (volatile uint8_t *)(uintptr_t)sata_port_extension_address(port);
    for (unsigned i = 0; i < 0x400u; ++i) {
        extension[i] = 0;
    }
    for (unsigned i = 0; i < 512u; ++i) {
        data[i] = 0xA5u;
    }
    *(volatile uint32_t *)(void *)(slot + 0x00u) = 0x00010005u;
    *(volatile uint32_t *)(void *)(slot + 0x08u) = 0x0006D401u;
    slot[0x20u] = 0x27u;
    slot[0x21u] = 0x80u;
    slot[0x22u] = 0xECu;
    table[0x00u] = 0x27u;
    table[0x01u] = 0x80u;
    table[0x02u] = 0xECu;
    *(volatile uint32_t *)(void *)(table + 0x80u) = (uint32_t)(sata_port_identify_address(port) & 0xFFFFFFu) | 1u;
    *(volatile uint32_t *)(void *)(table + 0x8Cu) = 0x000001FFu;
}

void sata_port0_controller_enable(void) {
    uint32_t control = REG32(BACKEND_BASE + 4u);
    *(volatile uint32_t *)(uintptr_t)(BACKEND_BASE + 4u) = control | 0x80000002u;
}

int sata_port0_ensure_command_engine(void) {
    return sata_port_ensure_command_engine(0);
}

int sata_port_ensure_command_engine(unsigned port) {
    if (port >= SATA_PHYSICAL_PORTS) return 0;
    const uintptr_t base = sata_port_base(port);
    const uint32_t clb = (uint32_t)(sata_port_slot_address(port) & 0xFFFFFFu) | 3u;
    const uint32_t fb = (uint32_t)(sata_port_fis_address(port) & 0xFFFFFFu) | 1u;
    const uint32_t extension = (uint32_t)(sata_port_extension_address(port) & 0xFFFFFFu) | 1u;
    const uint32_t command = REG32(base + 0x18u);
    if ((command & 0x11u) == 0x11u &&
        REG32(base + 0x00u) == clb &&
        REG32(base + 0x08u) == fb) {
        return 1;
    }
    *(volatile uint32_t *)(uintptr_t)(base + 0x14u) = 0u;
    *(volatile uint32_t *)(uintptr_t)(base + 0x18u) = command & ~0x11u;
    unsigned remaining = 1000000u;
    while ((REG32(base + 0x18u) & 0xC000u) && --remaining) {
    }
    if (!remaining) {
        return 0;
    }
    volatile uint8_t *fis = (volatile uint8_t *)sata_port_fis_address(port);
    volatile uint8_t *ext = (volatile uint8_t *)sata_port_extension_address(port);
    for (unsigned i = 0; i < 0x100u; ++i) fis[i] = 0;
    for (unsigned i = 0; i < 0x400u; ++i) ext[i] = 0;
    *(volatile uint32_t *)(uintptr_t)(base + 0x04u) = 0u;
    *(volatile uint32_t *)(uintptr_t)(base + 0x0Cu) = 0u;
    *(volatile uint32_t *)(uintptr_t)(base + 0x00u) = clb;
    *(volatile uint32_t *)(uintptr_t)(base + 0x70u) = extension;
    *(volatile uint32_t *)(uintptr_t)(base + 0x08u) = fb;
    *(volatile uint32_t *)(uintptr_t)(base + 0x30u) = 0xFFFFFFFFu;
    *(volatile uint32_t *)(uintptr_t)(base + 0x10u) = 0xFFFFFFFFu;
    *(volatile uint32_t *)(uintptr_t)(base + 0x18u) = 0x10000000u;
    *(volatile uint32_t *)(uintptr_t)(base + 0x18u) = 0x10000010u;
    *(volatile uint32_t *)(uintptr_t)(base + 0x18u) = 0x10000011u;
    return (REG32(base + 0x18u) & 0x11u) == 0x11u;
}

int sata_port0_issue_identify(int enable_port_irq) {
    return sata_port_issue_identify(0, enable_port_irq);
}

int sata_port_issue_identify(unsigned port, int enable_port_irq) {
    if (port >= SATA_PHYSICAL_PORTS || !sata_port_ensure_command_engine(port)) return 0;
    const uintptr_t base = sata_port_base(port);
    *(volatile uint32_t *)(uintptr_t)(base + 0x14u) = enable_port_irq ? 0xFDC000DBu : 0u;
    *(volatile uint32_t *)(uintptr_t)(base + 0x10u) = 0xFFFFFFFFu;
    *(volatile uint32_t *)(uintptr_t)(base + 0x38u) = 1u;
    return 1;
}

uint32_t sata_port_taskfile_status(unsigned port) {
    return port < SATA_PHYSICAL_PORTS ? REG32(sata_port_base(port) + 0x20u) : 0x7Fu;
}

void sata_port0_prepare_read_lba0(void) {
    volatile uint8_t *const slot = (volatile uint8_t *)(uintptr_t)0x3006B040u;
    volatile uint8_t *const table = (volatile uint8_t *)(uintptr_t)0x3006F100u;

    volatile uint8_t *const data = (volatile uint8_t *)(uintptr_t)0x3006E0D8u;
    static const uint8_t fis[20] = {
        0x27u, 0x80u, 0x25u, 0, 0, 0, 0, 0x40u,
        0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0,
    };
    for (unsigned i = 0; i < 0x40u; ++i) {
        slot[i] = 0;
    }
    for (unsigned i = 0; i < 0xA0u; ++i) {
        table[i] = 0;
    }
    for (unsigned i = 0; i < 512u; ++i) {
        data[i] = 0xA5u;
    }
    for (unsigned i = 0; i < 8u; ++i) {
        ((volatile uint8_t *)(uintptr_t)0x3006E0D0u)[i] = 0xA5u;
        data[512u + i] = 0x5Au;
    }
    *(volatile uint32_t *)(void *)(slot + 0x00u) = 0x00010005u;
    *(volatile uint32_t *)(void *)(slot + 0x08u) = 0x0006F105u;
    for (unsigned i = 0; i < sizeof fis; ++i) {
        slot[0x20u + i] = fis[i];
        table[i] = fis[i];
    }
    *(volatile uint32_t *)(void *)(table + 0x80u) = 0x0006E0D9u;
    *(volatile uint32_t *)(void *)(table + 0x8Cu) = 0x000001FFu;
}

void sata_port0_issue_read_lba0(void) {
    *(volatile uint32_t *)(uintptr_t)(PORT0_BASE + 0x10u) = 0xFFFFFFFFu;
    *(volatile uint32_t *)(uintptr_t)(BACKEND_BASE + 0x08u) = 1u;
    *(volatile uint32_t *)(uintptr_t)(PORT0_BASE + 0x38u) = 2u;
}

int sata_port0_ack_completion(void) {
    uint32_t status = REG32(PORT0_BASE + 0x10u);
    *(volatile uint32_t *)(uintptr_t)(PORT0_BASE + 0x10u) = status;
    *(volatile uint32_t *)(uintptr_t)(BACKEND_BASE + 0x08u) = 1u;
    return (status & 2u) && !(REG32(PORT0_BASE + 0x38u) & 1u);
}

uint16_t sata_port0_identify_word(unsigned index) {
    if (index >= 256u) {
        return 0;
    }
    volatile const uint16_t *const data = (volatile const uint16_t *)(uintptr_t)0x3006E080u;
    return data[index];
}

uint16_t sata_port0_read0_word(unsigned index) {
    if (index >= 256u) {
        return 0;
    }
    volatile const uint16_t *const data = (volatile const uint16_t *)(uintptr_t)0x3006E0D8u;
    return data[index];
}

uint32_t sata_port0_read0_changed_bytes(void) {
    volatile const uint8_t *const data = (volatile const uint8_t *)(uintptr_t)0x3006E0D8u;
    uint32_t changed = 0;
    for (unsigned i = 0; i < 512u; ++i) {
        if (data[i] != 0xA5u) {
            ++changed;
        }
    }
    return changed;
}

uint32_t sata_port0_read0_pre_guard(void) {
    return REG32(0x3006E0D0u);
}

uint32_t sata_port0_read0_post_guard(void) {
    return REG32(0x3006E2D8u);
}

uint32_t sata_port0_interrupt_enable(void) {
    return REG32(PORT0_BASE + 0x14u);
}

uint32_t sata_port0_command_issue(void) {
    return REG32(PORT0_BASE + 0x38u);
}

uint32_t sata_port0_interrupt_status(void) {
    return REG32(PORT0_BASE + 0x10u);
}

uint32_t sata_port0_taskfile_status(void) {
    return REG32(PORT0_BASE + 0x20u);
}

uint32_t sata_port0_backend_control(void) {
    return REG32(BACKEND_BASE + 4u);
}

uint32_t sata_port0_command_control(void) {
    return REG32(PORT0_BASE + 0x18u);
}

uint32_t sata_port0_extended_base(void) {
    return REG32(PORT0_BASE + 0x70u);
}
