
#ifndef OPEN9230_CH568_DIAG_H
#define OPEN9230_CH568_DIAG_H
#include <stdint.h>
enum { CH568_SERVICE_PORT = 2u };
void ch568_diag_init(void);
int ch568_diag_poll(void);
uint32_t ch568_diag_ready(void);
#endif
