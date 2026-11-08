#include <nds32_isr.h>
#include <nds32_intrinsic.h>

#include "CH568SFR.h"
#include "CH56X_irq.h"
#include "usb_mailbox.h"

__attribute__((interrupt("id=" XSTR(INT_ID_SW)))) void WDOG_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_TMR0)))) void TMR0_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_GPIO)))) void GPIO_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_SPI0)))) void SPI0_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_SATA)))) void SATA_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_TMR1)))) void TMR1_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_TMR2)))) void TMR2_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_UART0)))) void UART0_Handler(void) {}

__attribute__((interrupt("id=" XSTR(INT_ID_USB1)))) void USB1_Handler(void)
{
    USB1DevIntDeal();
}

__attribute__((interrupt("id=" XSTR(INT_ID_SDC)))) void SDC_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_ECDC)))) void ECDC_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_LED)))) void LED_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_SPI1)))) void SPI1_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_UART1)))) void UART1_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_UART2)))) void UART2_Handler(void) {}
__attribute__((interrupt("id=" XSTR(INT_ID_UART3)))) void UART3_Handler(void) {}
