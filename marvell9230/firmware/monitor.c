
#include <stdint.h>
#include "monitor.h"

#define REG8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

enum {
    UART0 = 0xD0072000u,
    PAYLOAD_BASE = 0x30070000u,
    PAYLOAD_LIMIT = 0x00010000u,
};

static char line[40];
static uint32_t line_used;
static uint32_t upload_length;
static uint32_t upload_received;
static uint32_t upload_crc;
static uint32_t upload_expected_crc;
static uint32_t loaded_length;
static uint32_t announced;
#ifdef OPEN9230_EXPERIMENTAL_FRONTEND
static uint32_t frontend_requested;
static uint32_t frontend_armed;
#endif

static void tx(uint8_t value) {
    while (!(REG8(UART0 + 0x14u) & 0x20u)) {
    }
    REG8(UART0) = value;
}

static void puts(const char *value) {
    while (*value) {
        tx((uint8_t)*value++);
    }
}

static void hex32(uint32_t value) {
    static const char digits[] = "0123456789ABCDEF";
    for (int shift = 28; shift >= 0; shift -= 4) {
        tx((uint8_t)digits[(value >> shift) & 15u]);
    }
}

static int hex_digit(char ch) {
    if (ch >= '0' && ch <= '9') {
        return ch - '0';
    }
    if (ch >= 'A' && ch <= 'F') {
        return ch - 'A' + 10;
    }
    if (ch >= 'a' && ch <= 'f') {
        return ch - 'a' + 10;
    }
    return -1;
}

static int parse_hex8(const char *text, uint32_t *output) {
    uint32_t value = 0;
    for (unsigned i = 0; i < 8u; ++i) {
        int nibble = hex_digit(text[i]);
        if (nibble < 0) {
            return 0;
        }
        value = (value << 4) | (uint32_t)nibble;
    }
    *output = value;
    return 1;
}

static int read_allowed(uint32_t address) {
    if (address & 3u) {
        return 0;
    }
    return (address >= 0x80002800u && address <= 0x8000307Cu) ||
           (address >= 0x8000C000u && address <= 0x8000C0FCu) ||
           (address >= 0x8000A800u && address <= 0x8000AAFCu) ||
           (address >= 0xD0020000u && address <= 0xD00203FCu) ||
           (address >= 0xD0030000u && address <= 0xD00300FCu) ||
           (address >= 0xD0071000u && address <= 0xD00710FCu) ||
           (address >= 0x30060000u && address <= 0x3007FFFCu);
}

static void print_register(uint32_t address) {
    puts("R ");
    hex32(address);
    tx('=');
    hex32(REG32(address));
    puts("\r\n");
}

static void host_snapshot(void) {
    static const uint32_t addresses[] = {
        0x80002800u, 0x80002804u, 0x80003008u, 0x8000300Cu,
        0x80003010u, 0x80003014u, 0x80002910u, 0x80002914u,
        0x80002918u, 0x80002920u, 0x80002924u, 0x80002928u,
        0x80002930u, 0x80002934u, 0x80002938u, 0x8000293Cu,
        0x80002940u,
    };
    puts("HOST_BEGIN\r\n");
    for (unsigned i = 0; i < sizeof addresses / sizeof addresses[0]; ++i) {
        print_register(addresses[i]);
    }
    puts("HOST_END\r\n");
}

static void uart_drain(void) {
    for (uint32_t limit = 1000000u; limit; --limit) {
        if (REG8(UART0 + 0x14u) & 0x40u) {
            return;
        }
    }
}

static void run_payload(void) {
    if (!loaded_length) {
        puts("ERR NO_PAYLOAD\r\n");
        return;
    }
    puts("EXEC_START\r\n");
    uart_drain();
    uint32_t zero = 0;
    __asm__ volatile("mcr p15, 0, %0, c7, c10, 4\n"
                     "mcr p15, 0, %0, c7, c5, 0\n"
                     : : "r"(zero) : "memory");
    ((void (*)(void))(uintptr_t)PAYLOAD_BASE)();
    puts("EXEC_RETURN\r\n");
}

static void process_line(void) {
    uint32_t address;
    uint32_t crc;
    if (line_used == 1u && line[0] == '?') {
#ifdef OPEN9230_EXPERIMENTAL_FRONTEND
        puts("COMMANDS ? H Rxxxxxxxx Ullllllllcccccccc X F\r\n");
#else
        puts("COMMANDS ? H Rxxxxxxxx Ullllllllcccccccc X\r\n");
#endif
    } else if (line_used == 1u && line[0] == 'H') {
        host_snapshot();
    } else if (line_used == 9u && line[0] == 'R' &&
               parse_hex8(line + 1, &address)) {
        if (read_allowed(address)) {
            print_register(address);
        } else {
            puts("ERR ADDRESS\r\n");
        }
    } else if (line_used == 17u && line[0] == 'U' &&
               parse_hex8(line + 1, &address) &&
               parse_hex8(line + 9, &crc) &&
               address >= 4u && address <= PAYLOAD_LIMIT && !(address & 3u)) {
        upload_length = address;
        upload_received = 0;
        upload_crc = 0xFFFFFFFFu;
        upload_expected_crc = crc;
        loaded_length = 0;
        puts("UPLOAD_READY ");
        hex32(upload_length);
        puts("\r\n");
    } else if (line_used == 1u && line[0] == 'X') {
        run_payload();
#ifdef OPEN9230_EXPERIMENTAL_FRONTEND
    } else if (line_used == 1u && line[0] == 'F') {
        if (frontend_armed) {
            puts("HOST_EXPERIMENT_ALREADY_ARMED\r\n");
        } else {
            frontend_armed = 1;
            frontend_requested = 1;
            puts("HOST_EXPERIMENT_ARMED\r\n");
        }
#endif
    } else {
        puts("ERR COMMAND\r\n");
    }
}

#ifdef OPEN9230_EXPERIMENTAL_FRONTEND
int monitor_frontend_requested(void) {
    if (!frontend_requested) {
        return 0;
    }
    frontend_requested = 0;
    return 1;
}
#endif

static void receive_upload_byte(uint8_t byte) {
    REG8(PAYLOAD_BASE + upload_received) = byte;
    upload_crc ^= byte;
    for (unsigned bit = 0; bit < 8u; ++bit) {
        upload_crc = (upload_crc >> 1) ^
                     ((upload_crc & 1u) ? 0xEDB88320u : 0u);
    }
    if (++upload_received == upload_length) {
        if ((upload_crc ^ 0xFFFFFFFFu) == upload_expected_crc) {
            loaded_length = upload_length;
            puts("UPLOAD_OK\r\n");
        } else {
            puts("UPLOAD_BAD_CRC\r\n");
        }
        upload_length = 0;
        upload_received = 0;
    }
}

void monitor_poll(void) {
    if (!announced) {
        announced = 1;
        puts("OPEN9230 MONITOR READY\r\n");
    }
    if (!(REG8(UART0 + 0x14u) & 1u)) {
        return;
    }
    uint8_t byte = REG8(UART0);
    if (upload_length) {
        receive_upload_byte(byte);
        return;
    }
    if (byte == '\r' || byte == '\n') {
        if (line_used) {
            process_line();
            line_used = 0;
        }
    } else if (line_used < sizeof line) {
        line[line_used++] = (char)byte;
    } else {
        line_used = 0;
        puts("ERR LINE\r\n");
    }
}
