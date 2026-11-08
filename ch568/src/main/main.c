#include <nds32_isr.h>
#include <nds32_intrinsic.h>

#include "CH568SFR.h"
#include "MYdebug.h"
#include "mailbox.h"
#include "sata_device.h"
#include "usb_mailbox.h"

int main(void)
{
    SysClkInit();
    mDelaymS(20);
    Interrupt_init(1 << INT_ID_USB1);

    MailboxInit();
    USB1DeviceInit();
    USB1Log("LOG FW 3.0 boot-probe C8 and SATA 1.5G experimental\r\n");
    SATADeviceInit();

    for (;;) {
        MailboxService();
        USB1MailboxService();
        SATADeviceService();
        MailboxService();
        USB1MailboxService();
    }
}
