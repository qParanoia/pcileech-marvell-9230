
#include <stdint.h>
#ifndef OPEN9230_STATIC_BOARD_TEST
#include "monitor.h"
#endif
#if defined(OPEN9230_EXPERIMENTAL_FRONTEND) || defined(OPEN9230_STATIC_BOARD_TEST)
#include "host_frontend.h"
#include "console_identify.h"
#endif
#include "punit.h"
#include "sata_port0.h"
#ifdef OPEN9230_CH568_DIAGNOSTICS
#include "ch568_diag.h"
#endif

#define MMIO32(address) (*(volatile uint32_t *)(uintptr_t)(address))
#define MMIO8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#ifndef IDENTIFY_TIMEOUT_POLLS
#define IDENTIFY_TIMEOUT_POLLS 10000000u
#endif
#ifndef STATIC_TEST_POLL_BUDGET
#define STATIC_TEST_POLL_BUDGET 200000000u
#endif

enum {
    UART0 = 0xD0072000u,
    CHIP_ID = 0xD0030000u,
    STRAP = 0xD0071054u,
    IRQ_STATUS = 0xD0020200u,
    IRQ_ENABLE = 0xD0020204u,
    IRQ_ENABLE_OTHER = 0xD0020208u,
    BOOT_MARKER = 0x04001000u,
    IRQ_COUNT = 0x04001004u,
    IRQ_LAST = 0x04001008u,
    SCTLR_ENTRY = 0x04001010u,
    PUNIT_PORT_ENABLE = 0xD0020110u,
    PUNIT_RESET = 0xD0020114u,
    PUNIT_CONTROL = 0xD0020300u,
    PUNIT_TIMER = 0xD0020318u,
};

static volatile uint32_t startup_probe;
static volatile uint32_t identify_pending;
static volatile uint32_t identify_completed;
static volatile uint32_t read0_pending;
static volatile uint32_t irqtest_pending;
static volatile uint32_t irq_cpu_pending;
static volatile uint32_t irq_port_is;
static volatile uint32_t irq_ci;
#ifdef OPEN9230_EXPERIMENTAL_FRONTEND
static uint32_t host_frontend_started;
#endif
#ifdef OPEN9230_STATIC_BOARD_TEST
static uint32_t static_test_done;
#ifdef OPEN9230_STATIC_BOOT_TEST
static uint32_t static_service_polls;
static uint32_t static_service_events;
static uint32_t static_io_issued;
static uint32_t static_io_completed;
static uint32_t static_io_errors;
static uint32_t static_other_slots;
static uint32_t static_last_host_is;
static uint32_t static_last_port_is;
static uint32_t static_ack_changes;
static uint32_t static_vport_last_ci[8];
static uint32_t static_vport_last_shadow[8];
static uint32_t static_vport_events;
static uint32_t static_console_dumps;
#endif
#endif

extern void stage_enable_irq(void);
extern void stage_disable_irq(void);

static uint32_t stage_sctlr(void) {
    uint32_t value;
    __asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(value));
    return value;
}

static void uart_drain(void) {
    for (uint32_t limit = 1000000u; limit; --limit) {
        if (MMIO8(UART0 + 0x14u) & 0x40u) {
            return;
        }
    }
}

static void uart_init(void) {
    MMIO8(UART0 + 4) = 0;
    MMIO8(UART0 + 12) = 0x80;
    MMIO8(UART0) = 0xA2;
    MMIO8(UART0 + 4) = 0;
    MMIO8(UART0 + 12) = 3;
    MMIO8(UART0 + 8) = 7;
}

static void uart_putc(uint8_t byte) {
    while ((MMIO8(UART0 + 0x14) & 0x20) == 0) {
    }
    MMIO8(UART0) = byte;
}

static void uart_puts(const char *text) {
    while (*text) {
        uart_putc((uint8_t)*text++);
    }
}

static void uart_hex32(uint32_t value) {
    static const char digits[] = "0123456789ABCDEF";
    for (unsigned shift = 28; ; shift -= 4) {
        uart_putc((uint8_t)digits[(value >> shift) & 15]);
        if (shift == 0) {
            break;
        }
    }
}

__attribute__((noinline, used)) void stage_poll_marker(void) {
    __asm__ volatile("nop");
}

#ifdef OPEN9230_STATIC_BOARD_TEST
static struct host_port_reset static_ports[8];

#ifdef OPEN9230_DMA_PROBE
static void static_prepare_additional_ports(void) {
    const uint32_t implemented = MMIO32(0x8000A80Cu);


    if (sata_port0_command_issue() & 1u) {
        uart_puts("SATA_INIT_SKIPPED=PORT0_BUSY\r\n");
        return;
    }
    for (unsigned port = 1; port < SATA_PHYSICAL_PORTS; ++port) {
        if (!(implemented & (1u << port)) ||
            (sata_port_status(port) & 0xFu) != 3u) continue;
        const int engine = sata_port_ensure_command_engine(port);
        for (uint32_t wait = 0; engine && wait < 100000000u; ++wait) {
            if (sata_port_signature(port) == 0x101u) break;
        }
        int identified = 0;
        if (engine && sata_port_signature(port) == 0x101u) {


            sata_port_prepare_identify(port);
            if (sata_port_issue_identify(port, 0)) {
                uint32_t wait = IDENTIFY_TIMEOUT_POLLS;
                while ((MMIO32(sata_port_base(port) + 0x38u) & 1u) && --wait) {
                }
                identified = wait && !(sata_port_taskfile_status(port) & 1u) &&
                    (MMIO32(sata_port_base(port) + 0x10u) & 3u);
            }
        }
        uart_puts("SATA_INIT PORT=");
        uart_hex32(port);
        uart_puts(" ENGINE=");
        uart_hex32((uint32_t)engine);
        uart_puts(" SSTS=");
        uart_hex32(sata_port_status(port));
        uart_puts(" SIG=");
        uart_hex32(sata_port_signature(port));
        uart_puts(" IDENTIFY=");
        uart_hex32((uint32_t)identified);
        uart_puts("\r\n");
        if (MMIO32(sata_port_base(port) + 0x38u) & 1u) {
            uart_puts("SATA_INIT_STOP=IDENTIFY_PENDING\r\n");
            return;
        }
    }
}
#endif

static void static_host_ports_init(void) {
    for (uint32_t port = 0; port < 8u; ++port) {
        static_ports[port].command = 0x00140006u;
        static_ports[port].signature = 0xFFFFFFFFu;
        static_ports[port].sstatus = 0;
        static_ports[port].taskfile = 0x7Fu;
    }
    for (unsigned port = 0; port < SATA_PHYSICAL_PORTS; ++port) {
#ifdef OPEN9230_CH568_DIAGNOSTICS
        if (port == CH568_SERVICE_PORT) continue;
#endif
        if ((sata_port_status(port) & 0xFu) == 3u &&
            sata_port_signature(port) == 0x101u) {
            static_ports[port].signature = 0x101u;
            static_ports[port].sstatus = sata_port_status(port);
            static_ports[port].taskfile = sata_port_taskfile_status(port);
        }
    }
    static_ports[7].command = 0x00100006u;
    static_ports[7].signature = 0xEB140101u;
    static_ports[7].sstatus = 0x113u;
    static_ports[7].taskfile = 0x50u;
}

static uint32_t static_host_reset_registers(void) {
    static_host_ports_init();
    const uint32_t count = host_frontend_reset_registers(static_ports, 8);
#ifdef OPEN9230_DMA_PROBE


#ifdef OPEN9230_CH568_DIAGNOSTICS
    MMIO32(0x8000280Cu) = 0x8Fu & ~(1u << CH568_SERVICE_PORT);
#else
    MMIO32(0x8000280Cu) = 0x8Fu;
#endif
#endif
    return count;
}

static void static_host_snapshot(const char *label) {
    uart_puts(label);
    uart_puts(" GHC=");
    uart_hex32(MMIO32(0x80002804u));
    uart_puts(" CLB=");
    uart_hex32(MMIO32(0x80002900u));
    uart_puts(" CMD=");
    uart_hex32(MMIO32(0x80002918u));
    uart_puts(" CI=");
    uart_hex32(MMIO32(0x80002938u));
    uart_puts(" SHADOW=");
    uart_hex32(MMIO32(0x8000C060u));
    uart_puts(" IRQ=");
    uart_hex32(MMIO32(0x80003008u));
    uart_puts(" AF=");
    uart_hex32(MMIO32(0x8000C044u));
    uart_puts("\r\n");
}

#ifdef OPEN9230_STATIC_BOOT_TEST
static void static_completion_snapshot(void) {
    const unsigned port = host_frontend_basic_port();
    const uintptr_t host_offset = port * 0x80u;
    const uintptr_t backend_offset = port * 0x80u;
    const uintptr_t fis = sata_port_fis_address(port);
    const uintptr_t host_fis = 0x30003000u + port * 0x40u;
    uart_puts("HOST_COMPLETION IS=");
    uart_hex32(MMIO32(0x80002808u));
    uart_puts(" P0IS=");
    uart_hex32(MMIO32(0x80002910u + host_offset));
    uart_puts(" P0IE=");
    uart_hex32(MMIO32(0x80002914u + host_offset));
    uart_puts(" P0TFD=");
    uart_hex32(MMIO32(0x80002920u + host_offset));
    uart_puts(" P0CI=");
    uart_hex32(MMIO32(0x80002938u + host_offset));
    uart_puts(" P0SACT=");
    uart_hex32(MMIO32(0x80002934u + host_offset));
    uart_puts(" INTR=");
    uart_hex32(MMIO32(0x8000C084u));
    uart_puts(" DMA_ST=");
    uart_hex32(MMIO32(0x8000C040u));
    uart_puts(" BE_TFD=");
    uart_hex32(MMIO32(0x8000A920u + backend_offset));
    uart_puts(" PORT=");
    uart_hex32(port);
    uart_puts("\r\n");
    uart_puts("HOST_FIS FB=");
    uart_hex32(MMIO32(0x80002908u + host_offset));
    uart_puts(" FB_HI=");
    uart_hex32(MMIO32(0x8000290Cu + host_offset));
    uart_puts(" BE_PIO=");
    uart_hex32(MMIO32(fis + 0x20u));
    uart_puts(" BE_D2H=");
    uart_hex32(MMIO32(fis + 0x40u));
    uart_puts(" BE_SDB=");
    uart_hex32(MMIO32(fis + 0x58u));
    uart_puts(" HOST_20=");
    uart_hex32(MMIO32(host_fis + 0x20u));
    uart_puts(" HOST_24=");
    uart_hex32(MMIO32(host_fis + 0x24u));
    uart_puts(" HOST_38=");
    uart_hex32(MMIO32(host_fis + 0x38u));
    uart_puts(" HOST_40=");
    uart_hex32(MMIO32(host_fis + 0x40u));
    uart_puts(" PORT=");
    uart_hex32(port);
    uart_puts("\r\n");
}

static void static_trace_host_ack(void);

#ifdef OPEN9230_DMA_PROBE
static uint32_t static_port0_last[7];
static uint32_t static_port0_changes;

static void static_service_port_resets(void) {
    for (unsigned port = 0; port < SATA_PHYSICAL_PORTS; ++port) {
#ifdef OPEN9230_CH568_DIAGNOSTICS
        if (port == CH568_SERVICE_PORT) continue;
#endif
        if (!host_frontend_poll_port_reset(port)) continue;
        const uintptr_t base = 0x80002900u + port * 0x80u;
        uart_puts("HOST_PORT");
        uart_putc((uint8_t)('0' + port));
        uart_puts("_RESET_DONE SSTS=");
        uart_hex32(MMIO32(base + 0x28u));
        uart_puts(" SIG=");
        uart_hex32(MMIO32(base + 0x24u));
        uart_puts(" TFD=");
        uart_hex32(MMIO32(base + 0x20u));
        uart_puts("\r\n");
    }
}

static void static_trace_port0_state(void) {
    const uint32_t now[7] = {
        MMIO32(0x80002804u), MMIO32(0x80002918u),
        MMIO32(0x8000292Cu), MMIO32(0x80002928u),
        MMIO32(0x80002924u), MMIO32(0x80002920u),
        MMIO32(0x80002938u),
    };
    uint32_t changed = 0;
    for (uint32_t i = 0; i < 7u; ++i) {
        changed |= now[i] != static_port0_last[i];
        static_port0_last[i] = now[i];
    }
    if (!changed || static_port0_changes++ >= 48u) return;
    uart_puts("HOST_PORT0 GHC=");
    uart_hex32(now[0]);
    uart_puts(" CMD=");
    uart_hex32(now[1]);
    uart_puts(" SCTL=");
    uart_hex32(now[2]);
    uart_puts(" SSTS=");
    uart_hex32(now[3]);
    uart_puts(" SIG=");
    uart_hex32(now[4]);
    uart_puts(" TFD=");
    uart_hex32(now[5]);
    uart_puts(" CI=");
    uart_hex32(now[6]);
    uart_puts(" IS=");
    uart_hex32(MMIO32(0x80002910u));
    uart_puts(" IE=");
    uart_hex32(MMIO32(0x80002914u));
    uart_puts("\r\n");
}
#endif

static void static_trace_other_ports(void) {
    for (uint32_t port = 1; port < 8u; ++port) {
        uint32_t ci = MMIO32(0x80002938u + port * 0x80u);
        uint32_t shadow = MMIO32(0x8000C060u + port * 4u);
        if (ci == static_vport_last_ci[port] &&
            shadow == static_vport_last_shadow[port]) {
            continue;
        }
        static_vport_last_ci[port] = ci;
        static_vport_last_shadow[port] = shadow;
        if (!(ci | shadow) || static_vport_events++ >= 24u) {
            continue;
        }
        const uintptr_t base = 0x80002900u + port * 0x80u;
        uart_puts("HOST_VPORT PORT=");
        uart_hex32(port);
        uart_puts(" CI=");
        uart_hex32(ci);
        uart_puts(" SHADOW=");
        uart_hex32(shadow);
        uart_puts(" CMD=");
        uart_hex32(MMIO32(base + 0x18u));
        uart_puts(" IS=");
        uart_hex32(MMIO32(base + 0x10u));
        uart_puts(" TFD=");
        uart_hex32(MMIO32(base + 0x20u));
        uart_puts(" CLB=");
        uart_hex32(MMIO32(base));
        uart_puts(" FB=");
        uart_hex32(MMIO32(base + 8u));
        uart_puts("\r\n");
        if (port == 7u && static_console_dumps++ < 4u) {
            for (uint32_t offset = 0; offset < 0x100u; offset += 0x20u) {
                uart_puts("HOST_CONSOLE_SRAM=");
                uart_hex32(offset);
                for (uint32_t word = 0; word < 8u; ++word) {
                    uart_putc(' ');
                    uart_hex32(MMIO32(0x30001C00u + offset + word * 4u));
                }
                uart_puts("\r\n");
            }
        }
    }
}

static int static_host_service_once(void) {
    int event = host_frontend_poll_basic();
    if (event == 1) ++static_io_issued;
    else if (event == 2) ++static_io_completed;
    else if (event < 0) ++static_io_errors;
    int console_event = console_identify_poll();
    if (console_event && static_service_events++ < 64u) {
        uart_puts("HOST_CONSOLE OP=");
        uart_hex32(console_last_opcode());
        uart_puts(" CODE=");
        uart_hex32(console_last_packet_code());
        uart_puts(" STATUS=");
        uart_hex32(console_last_status());
        uart_puts(" EVENT=");
        uart_hex32((uint32_t)console_event);
        uart_puts(" CI=");
        uart_hex32(MMIO32(0x80002CB8u));
        uart_puts(" IS=");
        uart_hex32(MMIO32(0x80002C90u));
        uart_puts(" SLOT=");
        uart_hex32(console_last_slot());
        uart_puts("\r\n");
    }
    if (event && static_service_events++ < 64u) {
        uart_puts("HOST_IO OP=");
        uart_hex32(host_frontend_basic_opcode());
        uart_puts(" EVENT=");
        uart_hex32((uint32_t)event);
        uart_puts(" SHADOW=");
        uart_hex32(MMIO32(0x8000C060u + host_frontend_basic_port() * 4u));
        uart_puts(" SLOT=");
        uart_hex32(host_frontend_basic_slot());
        uart_puts(" PORT=");
        uart_hex32(host_frontend_basic_port());
        uart_puts("\r\n");
        if (event == 2 || event < 0) {
#ifdef OPEN9230_DMA_PROBE
            {
                const struct host_identify_probe *probe =
                    host_frontend_identify_probe();
                uart_puts("HOST_RFIS STATUS=");
                uart_hex32(probe->response_fis_status);
                uart_puts(" FB=");
                uart_hex32(probe->response_fis_bus_high);
                uart_hex32(probe->response_fis_bus_low);
                uart_puts(" SDB=");
                uart_hex32(probe->response_fis_sdb);
                uart_puts(" READBACK=");
                uart_hex32(probe->response_fis_readback);
                uart_puts("\r\n");
                uart_puts("HOST_PRDBC STATUS=");
                uart_hex32(probe->response_prdbc_status);
                uart_puts(" CLB=");
                uart_hex32(probe->response_prdbc_clb_high);
                uart_hex32(probe->response_prdbc_clb_low);
                uart_puts(" VALUE=");
                uart_hex32(probe->response_prdbc_bytes);
                uart_puts(" BE=");
                uart_hex32(probe->response_prdbc_backend);
                uart_puts(" BEFORE=");
                uart_hex32(probe->response_prdbc_before);
                uart_puts(" READBACK=");
                uart_hex32(probe->response_prdbc_readback);
                uart_puts(" LOCAL=");
                uart_hex32(probe->response_prdbc_local);
                uart_puts(" FALLBACK=");
                uart_hex32(probe->response_prdbc_fallback);
                uart_puts("\r\n");
            }
            if (event == 2 && host_frontend_basic_opcode() == 0xECu) {
                const struct host_identify_probe *probe =
                    host_frontend_identify_probe();
                uart_puts("HOST_DMA STATUS=");
                uart_hex32(probe->status);
                uart_puts(" CTBA=");
                uart_hex32(probe->ctba_high);
                uart_hex32(probe->ctba_low);
                uart_puts(" DBA=");
                uart_hex32(probe->data_high);
                uart_hex32(probe->data_low);
                uart_puts(" BYTES=");
                uart_hex32(probe->data_bytes);
                uart_puts(" PRDBC_PRE=");
                uart_hex32(probe->prdbc);
                uart_puts(" MATCH=");
                uart_hex32(probe->matched_bytes);
                uart_puts("\r\nHOST_DMA_W0 H=");
                uart_hex32(probe->host_word0);
                uart_puts(" L=");
                uart_hex32(probe->local_word0);
                uart_puts(" MODEL H=");
                uart_hex32(probe->host_model0);
                uart_puts(" L=");
                uart_hex32(probe->local_model0);
                uart_puts(" CAP H=");
                uart_hex32(probe->host_capacity0);
                uart_puts(" L=");
                uart_hex32(probe->local_capacity0);
                uart_puts("\r\n");
            }
#endif
            static_completion_snapshot();
            static_trace_host_ack();
            static_trace_other_ports();
        }
    }
    return event;
}


static void static_liveness_snapshot(void) {
    uart_puts("HOST_ALIVE POLLS=");
    uart_hex32(static_service_polls);
    uart_puts(" GHC=");
    uart_hex32(MMIO32(0x80002804u));
    uart_puts(" P0CI=");
    uart_hex32(MMIO32(0x80002938u));
    uart_puts(" SHADOW=");
    uart_hex32(MMIO32(0x8000C060u));
    uart_puts(" P7CI=");
    uart_hex32(MMIO32(0x80002CB8u));
    uart_puts(" P7SH=");
    uart_hex32(MMIO32(0x8000C07Cu));
    uart_puts(" P7OP=");
    uart_hex32(console_last_opcode());
    uart_puts(" P7SLOT=");
    uart_hex32(console_last_slot());
    uart_puts(" P7STATUS=");
    uart_hex32(console_last_status());
    uart_puts(" BE_CI=");
    uart_hex32(sata_port0_command_issue());
    uart_puts(" BE_TFD=");
    uart_hex32(sata_port0_taskfile_status());
    uart_puts(" ISSUED=");
    uart_hex32(static_io_issued);
    uart_puts(" DONE=");
    uart_hex32(static_io_completed);
    uart_puts(" ERR=");
    uart_hex32(static_io_errors);
    uart_puts("\r\n");
#ifdef OPEN9230_DMA_PROBE
    for (unsigned port = 0; port < SATA_PHYSICAL_PORTS; ++port) {
        const uintptr_t host = 0x80002900u + port * 0x80u;
        const struct host_port_counters *counters = host_frontend_port_counters(port);
        uart_puts("HOST_SATA PORT=");
        uart_hex32(port);
        uart_puts(" SSTS=");
        uart_hex32(MMIO32(host + 0x28u));
        uart_puts(" SIG=");
        uart_hex32(MMIO32(host + 0x24u));
        uart_puts(" CI=");
        uart_hex32(MMIO32(host + 0x38u));
        uart_puts(" BE_CI=");
        uart_hex32(MMIO32(sata_port_base(port) + 0x38u));
        uart_puts(" BE_TFD=");
        uart_hex32(sata_port_taskfile_status(port));
        uart_puts(" ISSUED=");
        uart_hex32(counters->issued);
        uart_puts(" DONE=");
        uart_hex32(counters->completed);
        uart_puts(" ERR=");
        uart_hex32(counters->errors);
        uart_puts("\r\n");
    }
#endif
}

static void static_trace_host_ack(void) {
    uint32_t host_is = MMIO32(0x80002808u);
    uint32_t port_is = MMIO32(0x80002910u);
    if (host_is != static_last_host_is || port_is != static_last_port_is) {
        static_last_host_is = host_is;
        static_last_port_is = port_is;
        if (static_ack_changes++ < 16u) {
            uart_puts("HOST_IRQ_CHANGE IS=");
            uart_hex32(host_is);
            uart_puts(" P0IS=");
            uart_hex32(port_is);
            uart_puts(" INTR=");
            uart_hex32(MMIO32(0x8000C084u));
            uart_puts("\r\n");
        }
    }
}
#endif

static void static_host_test(void) {
    uart_puts("STATIC_HOST_BEGIN\r\nHOST_PRE_GHC=");
    uart_hex32(MMIO32(0x80002804u));
    uart_puts("\r\nHOST_PRE_CLB_LO=");
    uart_hex32(MMIO32(0x80002900u));
    uart_puts("\r\nHOST_PRE_CLB_HI=");
    uart_hex32(MMIO32(0x80002904u));
    uart_puts("\r\nHOST_PRE_CMD=");
    uart_hex32(MMIO32(0x80002918u));
    uart_puts("\r\nHOST_PRE_CI=");
    uart_hex32(MMIO32(0x80002938u));
    uart_puts("\r\nHOST_PRE_SHADOW=");
    uart_hex32(MMIO32(0x8000C060u));
    uart_puts("\r\nHOST_PRE_AUTOFETCH=");
    uart_hex32(MMIO32(0x8000C044u));
    uart_puts("\r\nHOST_PRE_RAM0=");
    uart_hex32(MMIO32(0x30000000u));
    uart_puts("\r\nHOST_PRE_FIS0=");
    uart_hex32(MMIO32(0x30000010u));
    uart_puts("\r\n");
#ifdef OPEN9230_DMA_PROBE
    static_prepare_additional_ports();
#ifdef OPEN9230_CH568_DIAGNOSTICS
    ch568_diag_init();
    uart_puts("CH568_DIAGNOSTICS_READY=");
    uart_hex32(ch568_diag_ready());
    uart_puts("\r\n");
#endif
#endif
    static_host_ports_init();
    if (!(MMIO32(0x80002804u) & 0x80000000u) &&
        !MMIO32(0x80002900u) && !MMIO32(0x80002904u)) {
        uart_puts("HOST_RESET_PORTS=");
        uart_hex32(static_host_reset_registers());
        uart_puts("\r\n");
    } else {
        uart_puts("HOST_RESET_SKIPPED=BUSY\r\n");
        uart_puts("HOST_IRQ_PORTS=");
        uart_hex32(host_frontend_enable_irqs());
        uart_puts("\r\n");
    }
    host_frontend_init_dma_registers();
    if (static_ports[0].signature == 0x101u) {
        uart_puts("HOST_AUTOFETCH_INIT=");
        uart_hex32(host_frontend_enable_autofetch(0));
        uart_puts("\r\n");
    }
#ifdef OPEN9230_STATIC_BOOT_TEST
    uart_puts("HOST_CONSOLE_AUTOFETCH=");
    uart_hex32(host_frontend_enable_autofetch(7));
    uart_puts("\r\n");
#endif
#ifdef OPEN9230_DMA_PROBE
    uart_puts("HOST_IMPLEMENTED_PI=");
    uart_hex32(MMIO32(0x8000280Cu));
    uart_puts(" SATA_PORTS=00000004\r\n");
#endif
    static_host_snapshot("HOST_POST_INIT");
    int last_event = 0;
    uint32_t issued = 0;
    uint32_t completed = 0;
    uint32_t active = 0;
    uint32_t last_ghc = MMIO32(0x80002804u);
    uint32_t last_clb = MMIO32(0x80002900u);
    uint32_t last_cmd = MMIO32(0x80002918u);
    uint32_t last_ci = MMIO32(0x80002938u);
    uint32_t last_shadow = MMIO32(0x8000C060u);
    uint32_t change_count = 0;
    uint32_t reset_count = 0;
    uint32_t progress_mark = STATIC_TEST_POLL_BUDGET / 4u;
    for (uint32_t poll = 0; poll < STATIC_TEST_POLL_BUDGET; ++poll) {
        if (!(poll & 0xFFFu)) {
#ifdef OPEN9230_STATIC_BOOT_TEST
            static_trace_host_ack();
            static_trace_other_ports();
#endif
            uint32_t ghc = MMIO32(0x80002804u);
            uint32_t clb = MMIO32(0x80002900u);
            uint32_t cmd = MMIO32(0x80002918u);
            uint32_t ci = MMIO32(0x80002938u);
            uint32_t shadow = MMIO32(0x8000C060u);
            if (ghc != last_ghc || clb != last_clb || cmd != last_cmd ||
                ci != last_ci || shadow != last_shadow) {
                if (change_count++ < 24u) {
                    static_host_snapshot("HOST_CHANGE");
                }
                last_ghc = ghc;
                last_clb = clb;
                last_cmd = cmd;
                last_ci = ci;
                last_shadow = shadow;
            }
            if ((ghc & 1u) && reset_count < 4u) {
                ++reset_count;
                uart_puts("HOST_GHC_RESET_EVENT=");
                uart_hex32(ghc);
                uart_puts("\r\n");
                static_host_reset_registers();
#ifdef OPEN9230_STATIC_BOOT_TEST
                host_frontend_basic_reset_state();
                console_identify_reset();
#endif
                static_host_snapshot("HOST_POST_GHC_RESET");
            }
            if (progress_mark && poll >= progress_mark &&
                progress_mark < STATIC_TEST_POLL_BUDGET) {
                static_host_snapshot("HOST_PROGRESS");
                progress_mark += STATIC_TEST_POLL_BUDGET / 4u;
            }
        }
#ifdef OPEN9230_DMA_PROBE
        if (!active && (MMIO32(0x80002804u) & 0x80000000u)) {
#else
        if (!active && !(poll & 0xFFFu) &&
            (sata_port_status(0) & 0xFu) == 3u &&
            sata_port_signature(0) == 0x101u &&
            (MMIO32(0x80002804u) & 0x80000000u) &&
            (MMIO32(0x80002918u) & 1u) &&
            ((MMIO32(0x80002900u) & ~0x3FFu) ||
             MMIO32(0x80002904u))) {
#endif
            active = 1;
            uart_puts("HOST_PREREQUISITES_READY\r\n");
        }
        if (active) {
#ifdef OPEN9230_DMA_PROBE
            static_service_port_resets();
#endif
#ifdef OPEN9230_STATIC_BOOT_TEST
            int event = static_host_service_once();
#else
            int event = host_frontend_poll_identify();
#endif
            if (event) {
                last_event = event;
                issued |= (uint32_t)(event == 1);
                completed |= (uint32_t)(event == 2);
#ifndef OPEN9230_STATIC_BOOT_TEST
                uart_puts("HOST_IDENTIFY_EVENT=");
                uart_hex32((uint32_t)event);
                uart_puts("\r\n");
#endif
            }
        }
#ifdef OPEN9230_STATIC_BOOT_TEST
        else if (MMIO32(0x80002804u) & 0x80000000u) {
            (void)console_identify_poll();
        }
#endif
        stage_poll_marker();
    }
    uart_puts("HOST_CHANGES=");
    uart_hex32(change_count);
    uart_puts(" HOST_RESETS=");
    uart_hex32(reset_count);
    uart_puts("\r\nHOST_RESULT=");
    if (completed) {
        uart_puts("COMPLETE");
    } else if (last_event < 0) {
        uart_puts("ERROR_");
        uart_hex32((uint32_t)last_event);
    } else if (issued) {
        uart_puts("PENDING");
    } else if (!active) {
        uart_puts("NOT_READY");
    } else {
        uart_puts("NO_ISSUE");
    }
    uart_puts("\r\nHOST_GHC=");
    uart_hex32(MMIO32(0x80002804u));
    uart_puts("\r\nHOST_CLB_LO=");
    uart_hex32(MMIO32(0x80002900u));
    uart_puts("\r\nHOST_CLB_HI=");
    uart_hex32(MMIO32(0x80002904u));
    uart_puts("\r\nHOST_P0_CMD=");
    uart_hex32(MMIO32(0x80002918u));
    uart_puts("\r\nHOST_P0_CI=");
    uart_hex32(MMIO32(0x80002938u));
    uart_puts("\r\nHOST_SHADOW=");
    uart_hex32(MMIO32(0x8000C060u));
    uart_puts("\r\nHOST_AUTOFETCH_CTL=");
    uart_hex32(MMIO32(0x8000C044u));
    uart_puts("\r\nHOST_FETCH0=");
    uart_hex32(MMIO32(0x30000000u));
    uart_puts("\r\nHOST_FIS0=");
    uart_hex32(MMIO32(0x30000010u));
    uart_puts("\r\nHOST_BE_CI=");
    uart_hex32(MMIO32(0x8000A938u));
    uart_puts("\r\nHOST_BE_SACT=");
    uart_hex32(MMIO32(0x8000A934u));
    uart_puts("\r\nHOST_BE_IS=");
    uart_hex32(MMIO32(0x8000A910u));
    uart_puts("\r\nSTATIC_TEST_END\r\n");
#ifdef OPEN9230_STATIC_BOOT_TEST
    uart_puts("HOST_SERVICE_CONTINUES\r\n");
#endif
}
#endif

__attribute__((noreturn, noinline, used)) void stage_idle(void) {
    uint32_t polls = 0;
    for (;;) {
        if (irq_cpu_pending) {
            if (MMIO32(IRQ_COUNT)) {
                irq_cpu_pending = 0;
                stage_disable_irq();
                uart_puts("P0_IRQTEST_IRQ PENDING=");
                uart_hex32(MMIO32(IRQ_LAST));
                uart_puts(" PORTIS=");
                uart_hex32(irq_port_is);
                uart_puts(" CI=");
                uart_hex32(irq_ci);
                uart_puts(" ACK=");
                uart_hex32((uint32_t)sata_port0_ack_completion());
                uart_puts("\r\nP0_IRQTEST_W0=");
                uart_hex32(sata_port0_identify_word(0));
                uart_puts("\r\n");
            } else if (++polls == IDENTIFY_TIMEOUT_POLLS) {
                irq_cpu_pending = 0;
                stage_disable_irq();
                MMIO32(IRQ_ENABLE) = 0;
                uart_puts("P0_IRQTEST_TIMEOUT CI=");
                uart_hex32(sata_port0_command_issue());
                uart_puts(" IS=");
                uart_hex32(sata_port0_interrupt_status());
                uart_puts(" IRQST=");
                uart_hex32(MMIO32(IRQ_STATUS));
                uart_puts("\r\n");
            } else if (polls == 1000000u) {
                uart_puts("P0_IRQTEST_WAIT CI=");
                uart_hex32(sata_port0_command_issue());
                uart_puts(" IS=");
                uart_hex32(sata_port0_interrupt_status());
                uart_puts(" IRQST=");
                uart_hex32(MMIO32(IRQ_STATUS));
                uart_puts("\r\n");
            }
            stage_poll_marker();
            continue;
        }
        if (irqtest_pending) {
            if (!(sata_port0_command_issue() & 1u)) {
                irqtest_pending = 0;
                polls = 0;
                uint32_t port_status = sata_port0_interrupt_status();
                uint32_t global_status = MMIO32(IRQ_STATUS);
                uart_puts("P0_IRQTEST_MASKED_DONE IS=");
                uart_hex32(port_status);
                uart_puts(" IE=");
                uart_hex32(sata_port0_interrupt_enable());
                uart_puts(" IRQST=");
                uart_hex32(global_status);
                uart_puts(" VEC_IN=");
                uart_hex32(MMIO32(SCTLR_ENTRY));
                uart_puts(" SCTLR=");
                uart_hex32(stage_sctlr());
                uart_puts(" W0=");
                uart_hex32(sata_port0_identify_word(0));
                uart_puts("\r\n");
                if (global_status & 1u) {
                    uart_puts("P0_IRQTEST_CPU_START\r\n");
                    uart_drain();
                    irq_cpu_pending = 1;
                    stage_enable_irq();
                } else {
                    MMIO32(IRQ_ENABLE) = 0;
                    uart_puts("P0_IRQTEST_NO_GLOBAL_PENDING\r\n");
                }
            } else if (++polls == IDENTIFY_TIMEOUT_POLLS) {
                irqtest_pending = 0;
                MMIO32(IRQ_ENABLE) = 0;
                uart_puts("P0_IRQTEST_MASKED_TIMEOUT CI=");
                uart_hex32(sata_port0_command_issue());
                uart_puts(" IS=");
                uart_hex32(sata_port0_interrupt_status());
                uart_puts(" IRQST=");
                uart_hex32(MMIO32(IRQ_STATUS));
                uart_puts("\r\n");
            }
            stage_poll_marker();
            continue;
        }
        uint32_t slot_mask = identify_pending ? 1u : (read0_pending ? 2u : 0u);
        if (slot_mask && !(sata_port0_command_issue() & slot_mask)) {
            polls = 0;
            if (identify_pending) {
                identify_pending = 0;
                uart_puts("P0_IDENTIFY_POLL_DONE IS=");
            } else {
                read0_pending = 0;
                uart_puts("P0_READ0_POLL_DONE IS=");
            }
            uart_hex32(sata_port0_interrupt_status());
            uart_puts(" TFD=");
            uint32_t taskfile = sata_port0_taskfile_status();
            uart_hex32(taskfile);
            uart_puts(" IRQST=");
            uart_hex32(MMIO32(IRQ_STATUS));
            if (slot_mask == 1u) {
                uart_puts("\r\nP0_W0=");
                uint32_t word0 = sata_port0_identify_word(0);
                uart_hex32(word0);
                uart_puts("\r\nP0_MAJOR=");
                uart_hex32(sata_port0_identify_word(80));
                uart_puts("\r\nP0_ROTATION=");
                uart_hex32(sata_port0_identify_word(217));
                uart_puts("\r\nP0_DSM=");
                uart_hex32(sata_port0_identify_word(169));
                uart_puts("\r\n");
#ifdef OPEN9230_BASIC_BOOT


                uart_puts("P0_BACKEND_READY\r\n");
#else
                if (word0 != 0xA5A5u && !(taskfile & 1u)) {
                    sata_port0_prepare_read_lba0();
                    read0_pending = 1;
                    uart_puts("P0_READ0_START\r\n");
                    sata_port0_issue_read_lba0();
                    uart_puts("P0_READ0_ISSUED CI=");
                    uart_hex32(sata_port0_command_issue());
                    uart_puts("\r\n");
                } else {
                    uart_puts("P0_READ0_SKIPPED\r\n");
                }
#endif
            } else {
                uart_puts("\r\nP0_READ0_W0=");
                uart_hex32(sata_port0_read0_word(0));
                uart_puts("\r\nP0_READ0_LAST=");
                uart_hex32(sata_port0_read0_word(255));
                uart_puts("\r\nP0_READ0_CHANGED=");
                uart_hex32(sata_port0_read0_changed_bytes());
                uart_puts("\r\nP0_READ0_PRE=");
                uart_hex32(sata_port0_read0_pre_guard());
                uart_puts("\r\nP0_READ0_POST=");
                uart_hex32(sata_port0_read0_post_guard());
                uart_puts("\r\n");
                if (sata_port0_read0_changed_bytes() &&
                    sata_port0_read0_pre_guard() == 0xA5A5A5A5u &&
                    sata_port0_read0_post_guard() == 0x5A5A5A5Au &&
                    !(taskfile & 1u)) {
                    sata_port0_prepare_identify();
                    irqtest_pending = 1;
                    polls = 0;
                    MMIO32(IRQ_STATUS) = 0xFFFFFFFFu;
                    MMIO32(IRQ_ENABLE) = 1u;
                    uart_puts("P0_IRQTEST_MASKED_START\r\n");
                    if (!sata_port0_issue_identify(1)) {
                        irqtest_pending = 0;
                        MMIO32(IRQ_ENABLE) = 0;
                        uart_puts("P0_IRQTEST_SETUP_FAIL\r\n");
                    } else {
                        uart_puts("P0_IRQTEST_ISSUED CI=");
                        uart_hex32(sata_port0_command_issue());
                        uart_puts(" IS=");
                        uart_hex32(sata_port0_interrupt_status());
                        uart_puts(" IRQST=");
                        uart_hex32(MMIO32(IRQ_STATUS));
                        uart_puts("\r\n");
                    }
                } else {
                    uart_puts("P0_IRQTEST_SKIPPED\r\n");
                }
            }
        } else if (slot_mask && ++polls == IDENTIFY_TIMEOUT_POLLS) {
            identify_pending = 0;
            read0_pending = 0;
            uart_puts(slot_mask == 1u ? "P0_IDENTIFY_TIMEOUT CI=" : "P0_READ0_TIMEOUT CI=");
            uart_hex32(sata_port0_command_issue());
            uart_puts(" IS=");
            uart_hex32(sata_port0_interrupt_status());
            uart_puts(" TFD=");
            uart_hex32(sata_port0_taskfile_status());
            uart_puts(" CMD=");
            uart_hex32(sata_port0_command_control());
            uart_puts(" X70=");
            uart_hex32(sata_port0_extended_base());
            uart_puts(" CLB=");
            uart_hex32(MMIO32(0x8000A900u));
            uart_puts(" FB=");
            uart_hex32(MMIO32(0x8000A908u));
            uart_puts(" BECTL=");
            uart_hex32(sata_port0_backend_control());
            uart_puts(" IRQST=");
            uart_hex32(MMIO32(IRQ_STATUS));
            uart_puts("\r\n");
        } else if (slot_mask && polls == 1000000u) {
            uart_puts(slot_mask == 1u ? "P0_IDENTIFY_WAIT CI=" : "P0_READ0_WAIT CI=");
            uart_hex32(sata_port0_command_issue());
            uart_puts(" IS=");
            uart_hex32(sata_port0_interrupt_status());
            uart_puts(" IRQST=");
            uart_hex32(MMIO32(IRQ_STATUS));
            uart_puts("\r\n");
        }
        if (!slot_mask) {
#ifdef OPEN9230_STATIC_BOARD_TEST
            if (!static_test_done) {
                static_test_done = 1;
                static_host_test();
            }
#ifdef OPEN9230_STATIC_BOOT_TEST
            else {
                ++static_service_polls;
#ifdef OPEN9230_CH568_DIAGNOSTICS
                (void)ch568_diag_poll();
#endif
                if (!(static_service_polls & 0x3FFFFFu)) {
                    static_liveness_snapshot();
                }
                if (MMIO8(UART0 + 0x14u) & 1u) {
                    if (MMIO8(UART0) == '?') static_liveness_snapshot();
                }
#ifdef OPEN9230_DMA_PROBE
                static_service_port_resets();
                if (!(static_service_polls & 0x3FFu)) {
                    static_trace_port0_state();
                }
#endif
                if (!(static_service_polls & 0xFFFu)) {
                    static_trace_host_ack();
                    static_trace_other_ports();
                    uint32_t ghc = MMIO32(0x80002804u);
                    uint32_t shadow = MMIO32(0x8000C060u);
                    if (ghc & 1u) {
                        uart_puts("HOST_LATE_RESET=");
                        uart_hex32(ghc);
                        uart_puts("\r\n");
                        static_host_reset_registers();
                        host_frontend_basic_reset_state();
                        console_identify_reset();
                        static_host_snapshot("HOST_LATE_RESET_DONE");
                    }
                    if ((shadow & ~1u) && shadow != static_other_slots) {
                        static_other_slots = shadow;
                        uart_puts("HOST_OTHER_SLOTS=");
                        uart_hex32(shadow);
                        uart_puts("\r\n");
                    }
                }
                if (MMIO32(0x80002804u) & 0x80000000u) {
                    static_host_service_once();
                }
            }
#endif
#else
            monitor_poll();
#ifdef OPEN9230_EXPERIMENTAL_FRONTEND
            if (!host_frontend_started && monitor_frontend_requested()) {
                host_frontend_started = 1;
                uart_puts("HOST_FRONTEND_PORTS=");
                uart_hex32(host_frontend_enable_irqs());
                uart_puts("\r\n");
                host_frontend_init_dma_registers();
                if ((sata_port_status(0) & 0xFu) == 3u &&
                    sata_port_signature(0) == 0x101u) {
                    uart_puts("HOST_AUTOFETCH=");
                    uart_hex32(host_frontend_enable_autofetch(0));
                    uart_puts("\r\n");
                }
            }
            if (host_frontend_started) {
                int host_event = host_frontend_poll_identify();
                if (host_event) {
                    uart_puts("HOST_IDENTIFY_EVENT=");
                    uart_hex32((uint32_t)host_event);
                    uart_puts("\r\n");
                }
            }
#endif
#endif
        }
        stage_poll_marker();
    }
}

__attribute__((noreturn)) void stage_main(void) {
    uart_init();
    MMIO32(BOOT_MARKER) = 0x9230C002u;
    MMIO32(IRQ_COUNT) = 0;
    MMIO32(IRQ_LAST) = 0;
#ifdef OPEN9230_STATIC_BOARD_TEST
#ifdef OPEN9230_STATIC_BOOT_TEST
#ifdef OPEN9230_DMA_PROBE
#ifdef OPEN9230_CH568_DIAGNOSTICS
    uart_puts("OPEN9230 BASIC BOOT V22 CH568=DIAGNOSTICS\r\n");
#else
    uart_puts("OPEN9230 BASIC BOOT V20\r\n");
#endif
#ifdef OPEN9230_NO_OPTION_ROM
    uart_puts("OPTION_ROM=DISABLED\r\n");
#else
    uart_puts("OPTION_ROM=PRESERVED\r\n");
#endif
    uart_puts("CHIP=");
#else
#ifdef OPEN9230_BASIC_BOOT
    uart_puts("OPEN9230 BASIC BOOT V8\r\nCHIP=");
#else
    uart_puts("OPEN9230 STATIC BOOT V7\r\nCHIP=");
#endif
#endif
#else
    uart_puts("OPEN9230 STATIC V2\r\nCHIP=");
#endif
#else
    uart_puts("OPEN9230 C-STAGE V6\r\nCHIP=");
#endif
    uart_hex32(MMIO32(CHIP_ID));
    uart_puts("\r\nSTRAP=");
    uart_hex32(MMIO32(STRAP));
    uart_puts("\r\nBSS=");
    uart_hex32(startup_probe);
    startup_probe = 0xC0DE0001u;
    struct sata_port0_snapshot port = sata_port0_probe();
    uart_puts("\r\nPORTS=");
    uart_hex32(port.backend_ports);
    uart_puts("\r\nPORTMAP=");
    uart_hex32(port.backend_bitmap);
    uart_puts("\r\nP0_SSTS=");
    uart_hex32(port.sstatus);
    uart_puts("\r\nP0_SIG=");
    uart_hex32(port.signature);
    for (unsigned index = 1; index < 4u; ++index) {
        uart_puts("\r\nP");
        uart_putc((uint8_t)('0' + index));
        uart_puts("_SSTS=");
        uart_hex32(sata_port_status(index));
        uart_puts("\r\nP");
        uart_putc((uint8_t)('0' + index));
        uart_puts("_SIG=");
        uart_hex32(sata_port_signature(index));
    }
    uart_puts("\r\nPUNIT_110=");
    uart_hex32(MMIO32(PUNIT_PORT_ENABLE));
    uart_puts("\r\nPUNIT_114=");
    uart_hex32(MMIO32(PUNIT_RESET));
    uart_puts("\r\nPUNIT_300=");
    uart_hex32(MMIO32(PUNIT_CONTROL));
    uart_puts("\r\nPUNIT_318=");
    uart_hex32(MMIO32(PUNIT_TIMER));
    MMIO32(IRQ_ENABLE) = 0;
    MMIO32(IRQ_ENABLE_OTHER) = 0;
    MMIO32(IRQ_STATUS) = 0xFFFFFFFFu;
    punit_init();
    uart_puts("\r\nPUNIT_POST_110=");
    uart_hex32(MMIO32(PUNIT_PORT_ENABLE));
    uart_puts("\r\nPUNIT_POST_114=");
    uart_hex32(MMIO32(PUNIT_RESET));
    uart_puts("\r\nPUNIT_POST_300=");
    uart_hex32(MMIO32(PUNIT_CONTROL));
    uart_puts("\r\nPUNIT_POST_318=");
    uart_hex32(MMIO32(PUNIT_TIMER));
    uart_puts("\r\nBECTL_BEFORE=");
    uart_hex32(sata_port0_backend_control());
    sata_port0_controller_enable();
    uart_puts("\r\nBECTL_AFTER=");
    uart_hex32(sata_port0_backend_control());
    port = sata_port0_probe();
    if ((port.sstatus & 0xFu) == 3u && !sata_port0_ata_ready(&port)) {


        uart_puts("\r\nP0_SIGNATURE_ENGINE=");
        uart_hex32((uint32_t)sata_port0_ensure_command_engine());
        for (uint32_t wait = 0; wait < 100000000u; ++wait) {
            port = sata_port0_probe();
            if (sata_port0_ata_ready(&port)) {
                break;
            }
        }
    } else {
        port = sata_port0_probe();
    }
    uart_puts("\r\nP0_POST_SSTS=");
    uart_hex32(port.sstatus);
    uart_puts("\r\nP0_POST_SIG=");
    uart_hex32(port.signature);
    uint32_t descriptor_ready = 0;
    if (sata_port0_ata_ready(&port)) {
        sata_port0_prepare_identify();
        descriptor_ready = 1;
    }
    uart_puts("\r\nP0_DESC=");
    uart_hex32(descriptor_ready);
    uart_puts("\r\n");
    if (descriptor_ready) {
        MMIO32(IRQ_STATUS) = 0xFFFFFFFFu;
        MMIO32(IRQ_ENABLE) = 0u;
        identify_pending = 1;
        uart_puts("P0_IDENTIFY_START\r\n");
        if (!sata_port0_issue_identify(0)) {
            identify_pending = 0;
            uart_puts("P0_IDENTIFY_SETUP_FAIL CMD=");
            uart_hex32(sata_port0_command_control());
            uart_puts("\r\n");
        } else {
            uart_puts("P0_IDENTIFY_ISSUED CI=");
            uart_hex32(sata_port0_command_issue());
            uart_puts(" CMD=");
            uart_hex32(sata_port0_command_control());
            uart_puts("\r\n");
        }
    }
    stage_idle();
}

void stage_irq(void) {
    MMIO32(IRQ_ENABLE) = 0;
    uint32_t pending = MMIO32(IRQ_STATUS);
    irq_port_is = sata_port0_interrupt_status();
    irq_ci = sata_port0_command_issue();
    identify_completed = (uint32_t)((pending & 1u) != 0);
    MMIO32(IRQ_STATUS) = pending;
    MMIO32(IRQ_LAST) = pending;
    MMIO32(IRQ_COUNT) = MMIO32(IRQ_COUNT) + 1;
}
