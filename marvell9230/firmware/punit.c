
#include <stdint.h>
#include "punit.h"

#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))


void punit_init(void) {
    REG32(0x80003818u) = 0;
    REG32(0xD0020114u) = 0;
    REG32(0xD0020110u) = 0xFu;
    REG32(0xD0020300u) = 0;
    REG32(0xD0020000u) = 0;
    REG32(0xD0020010u) = 0;
    REG32(0xD0020310u) = 0xFFFFFFFFu;
    REG32(0xD0020314u) = 0xFFFFFFFFu;
    REG32(0xD0020300u) = REG32(0xD0020300u) | 3u;
    REG32(0xD0020318u) = 0x01C9C380u;
    REG32(0xD002031Cu) = 0x01C9C380u;
    REG32(0xD0020300u) = REG32(0xD0020300u) | 0xCu;
    REG32(0xD0020114u) = 4u;
    REG32(0xD0071058u) = (REG32(0xD0071058u) & 0xFFFF8000u) | 0x5B6Du;
    REG32(0xD0071028u) = 0xFFFFFFFFu;
    REG32(0xD0071024u) = 0xFFFFFFFFu;
}
