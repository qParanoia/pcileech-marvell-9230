/* SPDX-License-Identifier: MIT */
ENTRY(payload_entry)
SECTIONS
{
    . = 0x30070000;
    .text : {
        KEEP(*(.text.entry))
        *(.text*)
        *(.rodata*)
    }
    . = ALIGN(4);
    __payload_end = .;
    .data : { *(.data*) }
    .bss (NOLOAD) : { *(.bss*) *(COMMON) }
    ASSERT(__payload_end <= 0x30080000, "payload exceeds upload RAM")
    ASSERT(SIZEOF(.data) == 0, "payload requires initialized data")
    ASSERT(SIZEOF(.bss) == 0, "payload requires BSS initialization")
}
