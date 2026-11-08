@ SPDX-License-Identifier: MIT
@ Independent ARM-state stage at RAM address 0 after the existing SPI loader.
@ No calls or data references into the proprietary RAM segments.

    b reset
    b trap                 @ undefined instruction
    b trap                 @ software interrupt
    b trap                 @ prefetch abort
    b trap                 @ data abort
    b trap                 @ reserved
    b irq_handler
    b trap                 @ FIQ

svc_stack_top: .word 0x04004000
irq_stack_top: .word 0x04003f00
uart0_base:    .word 0xd0072000
chip_address:  .word 0xd0030000
irq_pending:   .word 0xd0020200
boot_marker:   .word 0x04001000
irq_count:     .word 0x04001004
irq_last:      .word 0x04001008
banner:        .byte 0x4f,0x50,0x45,0x4e,0x39,0x32,0x33,0x30,0x20,0x53,0x54,0x41,0x47,0x45,0x30,0x0d,0x0a,0x00
chip_label:    .byte 0x43,0x48,0x49,0x50,0x3d,0x00
newline:       .byte 0x0d,0x0a,0x00
    .align 2

reset:
    msr cpsr_c, #0xd2       @ IRQ mode, IRQ and FIQ masked
    ldr sp, irq_stack_top
    msr cpsr_c, #0xd3       @ supervisor mode, IRQ and FIQ masked
    ldr sp, svc_stack_top

    ldr r4, uart0_base
    mov r0, #0
    str r0, [r4, #4]
    mov r0, #0x80
    str r0, [r4, #0xc]
    mov r0, #0xa2
    str r0, [r4]
    mov r0, #0
    str r0, [r4, #4]
    mov r0, #3
    str r0, [r4, #0xc]
    mov r0, #7
    str r0, [r4, #8]

    ldr r0, boot_marker
    ldr r1, =0x9230c001
    str r1, [r0]
    ldr r0, irq_count
    mov r1, #0
    str r1, [r0]

    adr r2, banner
    bl puts
    adr r2, chip_label
    bl puts
    ldr r0, chip_address
    ldr r1, [r0]
    bl puthex32
    adr r2, newline
    bl puts

idle:
    b idle

irq_handler:
    push {r0-r3, r12, lr}
    ldr r0, irq_pending
    ldr r1, [r0]
    str r1, [r0]          @ global interrupt status is write-one-to-clear
    ldr r0, irq_last
    str r1, [r0]
    ldr r0, irq_count
    ldr r1, [r0]
    add r1, r1, #1
    str r1, [r0]
    pop {r0-r3, r12, lr}
    subs pc, lr, #4

trap:
    b trap

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
