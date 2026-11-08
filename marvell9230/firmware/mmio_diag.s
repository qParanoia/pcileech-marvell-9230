@ SPDX-License-Identifier: MIT
@ ARM state, linked at address 0 by the stock loader.
@ Read-only MMIO diagnostic for board revision discovery over UART0.

    b start
    b halt
    b halt
    b halt
    b halt
    b halt
    b halt
    b halt

marker_address: .word 0x04001000
marker_value:   .word 0x9230b007
uart0_base:     .word 0xd0072000
chip_address:   .word 0xd0030000
strap_address:  .word 0xd0071054
spi_address:    .word 0xf8064000

banner:      .byte 0x4f,0x50,0x45,0x4e,0x39,0x32,0x33,0x30,0x20,0x44,0x49,0x41,0x47,0x0d,0x0a,0x00
chip_label:  .byte 0x43,0x48,0x49,0x50,0x3d,0x00
strap_label: .byte 0x53,0x54,0x52,0x41,0x50,0x3d,0x00
spi_label:   .byte 0x53,0x50,0x49,0x30,0x3d,0x00
newline:     .byte 0x0d,0x0a,0x00
    .align 2

start:
    ldr r0, marker_address
    ldr r1, marker_value
    str r1, [r0]
    bl uart_init

    adr r2, banner
    bl puts

    adr r2, chip_label
    bl puts
    ldr r0, chip_address
    ldr r1, [r0]
    bl puthex32
    adr r2, newline
    bl puts

    adr r2, strap_label
    bl puts
    ldr r0, strap_address
    ldr r1, [r0]
    bl puthex32
    adr r2, newline
    bl puts

    adr r2, spi_label
    bl puts
    ldr r0, spi_address
    ldr r1, [r0]
    bl puthex32
    adr r2, newline
    bl puts

halt:
    b halt

uart_init:
    ldr r4, uart0_base
    mov r1, #0
    strb r1, [r4, #4]
    mov r1, #0x80
    strb r1, [r4, #0xc]
    mov r1, #0xa2
    strb r1, [r4]
    mov r1, #0
    strb r1, [r4, #4]
    mov r1, #3
    strb r1, [r4, #0xc]
    mov r1, #7
    strb r1, [r4, #8]
    bx lr

puts:
    push {r2, lr}
puts_next:
    ldrb r0, [r2], #1
    cmp r0, #0
    beq puts_done
    bl putc
    b puts_next
puts_done:
    pop {r2, pc}

putc:
    ldrb r3, [r4, #0x14]
    tst r3, #0x20
    beq putc
    strb r0, [r4]
    bx lr

puthex32:
    push {r5, r6, lr}
    mov r5, r1
    mov r6, #8
hex_next:
    mov r0, r5, lsr #28
    cmp r0, #9
    addls r0, r0, #0x30
    addhi r0, r0, #0x37
    bl putc
    mov r5, r5, lsl #4
    subs r6, r6, #1
    bne hex_next
    pop {r5, r6, pc}
