/* SPDX-License-Identifier: MIT */
ENTRY(_start)
SECTIONS
{
    . = 0x00000000;
    .text : {
        KEEP(*(.vectors))
        *(.text.startup)
        *(.text*)
        *(.rodata*)
    }
    . = ALIGN(4);
    __image_end = .;

    .bss 0x04002000 (NOLOAD) : {
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    }

    ASSERT(__image_end <= 0x00015AA4, "open stage exceeds CODE1 RAM segment")
    ASSERT(__bss_end <= 0x04003E00, "open stage BSS overlaps IRQ stack")
}
