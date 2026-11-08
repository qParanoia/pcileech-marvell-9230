#ifndef CH568_USB_MAILBOX_H
#define CH568_USB_MAILBOX_H

void USB1DeviceInit(void);
void USB1DevIntDeal(void);
void USB1MailboxService(void);
void USB1Log(const char *text);
void USB1BatchStart(UINT32 sequence, UINT8 page_count,
                    UINT32 expected_length);
UINT8 USB1BatchAcceptSataChunk(const UINT8 *data, UINT16 length);
void USB1BatchFinish(UINT8 status);
UINT8 USB1BatchActive(void);
void USB1BatchSetSataDiagnostics(UINT16 flags, UINT16 receive_length);

#endif
