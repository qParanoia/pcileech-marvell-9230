
#ifndef OPEN9230_CONSOLE_IDENTIFY_H
#define OPEN9230_CONSOLE_IDENTIFY_H

#include <stdint.h>


int console_identify_poll(void);
void console_identify_reset(void);
const uint16_t *console_identify_words(void);
uint32_t console_last_opcode(void);
uint32_t console_last_packet_code(void);
uint32_t console_last_status(void);
uint32_t console_last_slot(void);

#endif
