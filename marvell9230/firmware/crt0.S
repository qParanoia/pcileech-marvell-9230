/* SPDX-License-Identifier: MIT */
/* ARMv5TE reset and exception entry for the independently linked RAM stage. */

    .syntax unified
    .arm
    .section .vectors, "ax", %progbits
    .global _start
_start:
    b reset
    b trap
    b trap
    b trap
    b trap
    b trap
    b irq_entry
    b trap

    .section .text.startup, "ax", %progbits
reset:
    msr cpsr_c, #0xd2
    ldr sp, =0x04003f00
    msr cpsr_c, #0xd3
    ldr sp, =0x04004000
    /* CODE1 owns the low vector table at address zero. Preserve the loader's
     * incoming SCTLR for UART diagnostics, then select low exception vectors. */
    mrc p15, 0, r0, c1, c0, 0
    ldr r1, =0x04001010
    str r0, [r1]
    bic r0, r0, #0x2000
    mcr p15, 0, r0, c1, c0, 0
    mcr p15, 0, r0, c7, c5, 4
    ldr r0, =__bss_start
    ldr r1, =__bss_end
    mov r2, #0
1:
    cmp r0, r1
    strlo r2, [r0], #4
    blo 1b
    bl stage_main
trap:
    b trap

irq_entry:
    stmdb sp!, {r0-r3, r12, lr}
    bl stage_irq
    ldmia sp!, {r0-r3, r12, lr}
    subs pc, lr, #4

    .global stage_enable_irq
stage_enable_irq:
    mrs r0, cpsr
    bic r0, r0, #0x80
    msr cpsr_c, r0
    bx lr

    .global stage_disable_irq
stage_disable_irq:
    mrs r0, cpsr
    orr r0, r0, #0x80
    msr cpsr_c, r0
    bx lr
