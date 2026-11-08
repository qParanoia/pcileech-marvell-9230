
#ifndef OPEN9230_HOST_COMMAND_H
#define OPEN9230_HOST_COMMAND_H

#include <stdint.h>


int host_build_identify_slot(const uint8_t fetched[32], uint8_t backend_slot[64]);


int host_build_basic_slot(const uint8_t fetched[32], uint8_t backend_slot[64]);

#endif
