
#ifndef OPEN9230_SATA_PORT0_H
#define OPEN9230_SATA_PORT0_H

#include <stdint.h>

enum { SATA_PHYSICAL_PORTS = 4u };

static inline uintptr_t sata_port_base(unsigned port) {
    return 0x8000A900u + port * 0x80u;
}


static inline uintptr_t sata_port_slot_address(unsigned port) {
    return port ? 0x30068000u + (port - 1u) * 0x1000u : 0x3006B000u;
}
static inline uintptr_t sata_port_fis_address(unsigned port) {
    return port ? sata_port_slot_address(port) + 0x800u : 0x30067000u;
}
static inline uintptr_t sata_port_extension_address(unsigned port) {
    return port ? sata_port_slot_address(port) + 0xC00u : 0x3006D000u;
}
static inline uintptr_t sata_port_identify_address(unsigned port) {
    return port ? 0x3006E400u + (port - 1u) * 0x200u : 0x3006E080u;
}

int sata_port_ensure_command_engine(unsigned port);
void sata_port_prepare_identify(unsigned port);
int sata_port_issue_identify(unsigned port, int enable_port_irq);
uint32_t sata_port_taskfile_status(unsigned port);

struct sata_port0_snapshot {
    uint32_t backend_ports;
    uint32_t backend_bitmap;
    uint32_t sstatus;
    uint32_t signature;
};

struct sata_port0_snapshot sata_port0_probe(void);
uint32_t sata_port_status(unsigned port);
uint32_t sata_port_signature(unsigned port);
int sata_port0_ata_ready(const struct sata_port0_snapshot *port);
void sata_port0_prepare_identify(void);
void sata_port0_controller_enable(void);
int sata_port0_issue_identify(int enable_port_irq);


int sata_port0_ensure_command_engine(void);
void sata_port0_prepare_read_lba0(void);
void sata_port0_issue_read_lba0(void);
int sata_port0_ack_completion(void);
uint16_t sata_port0_identify_word(unsigned index);
uint16_t sata_port0_read0_word(unsigned index);
uint32_t sata_port0_read0_changed_bytes(void);
uint32_t sata_port0_read0_pre_guard(void);
uint32_t sata_port0_read0_post_guard(void);
uint32_t sata_port0_interrupt_enable(void);
uint32_t sata_port0_command_issue(void);
uint32_t sata_port0_interrupt_status(void);
uint32_t sata_port0_taskfile_status(void);
uint32_t sata_port0_backend_control(void);
uint32_t sata_port0_command_control(void);
uint32_t sata_port0_extended_base(void);

#endif
