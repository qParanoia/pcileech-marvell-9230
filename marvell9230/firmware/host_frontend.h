
#ifndef OPEN9230_HOST_FRONTEND_H
#define OPEN9230_HOST_FRONTEND_H

#include <stdint.h>


uint32_t host_frontend_enable_irqs(void);

struct host_port_reset {
    uint32_t command;
    uint32_t signature;
    uint32_t sstatus;
    uint32_t taskfile;
};


uint32_t host_frontend_reset_registers(const struct host_port_reset ports[8],
                                       uint32_t count);


void host_frontend_init_dma_registers(void);


uint32_t host_frontend_enable_autofetch(uint32_t port);


int host_frontend_poll_identify(void);


int host_frontend_poll_basic(void);
uint32_t host_frontend_basic_opcode(void);
uint32_t host_frontend_basic_slot(void);
uint32_t host_frontend_basic_port(void);
struct host_port_counters {
    uint32_t issued;
    uint32_t completed;
    uint32_t errors;
};
const struct host_port_counters *host_frontend_port_counters(unsigned port);
void host_frontend_basic_reset_state(void);

#ifdef OPEN9230_DMA_PROBE
struct host_identify_probe {
    uint32_t status;
    uint32_t ctba_low;
    uint32_t ctba_high;
    uint32_t data_low;
    uint32_t data_high;
    uint32_t data_bytes;
    uint32_t prdbc;
    uint32_t matched_bytes;
    uint32_t host_word0;
    uint32_t local_word0;
    uint32_t host_model0;
    uint32_t local_model0;
    uint32_t host_capacity0;
    uint32_t local_capacity0;
    uint32_t response_fis_status;
    uint32_t response_fis_bus_low;
    uint32_t response_fis_bus_high;
    uint32_t response_fis_sdb;
    uint32_t response_fis_readback;
    uint32_t response_prdbc_status;
    uint32_t response_prdbc_bytes;
    uint32_t response_prdbc_backend;
    uint32_t response_prdbc_before;
    uint32_t response_prdbc_readback;
    uint32_t response_prdbc_clb_low;
    uint32_t response_prdbc_clb_high;
    uint32_t response_prdbc_local;
    uint32_t response_prdbc_fallback;
};
const struct host_identify_probe *host_frontend_identify_probe(void);
int host_frontend_poll_port0_reset(void);
int host_frontend_poll_port_reset(unsigned port);
#endif

#endif
