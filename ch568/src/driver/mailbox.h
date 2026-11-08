#ifndef CH568_MAILBOX_H
#define CH568_MAILBOX_H

#include "CH568SFR.h"

#define MAILBOX_COMMAND_1337 0x00001337UL
#define MAILBOX_COMMAND_READ64 0x00001338UL
#define MAILBOX_COMMAND_READ4K_FIS 0x00001339UL
#define MAILBOX_COMMAND_READ4K 0x0000133AUL
#define MAILBOX_COMMAND_READ_BATCH 0x0000133BUL
#define MAILBOX_COMMAND_READ_LINEAR 0x00001341UL
#define MAILBOX_COMMAND_SET_MAP 0x00001342UL
#define MAILBOX_READ64_SIZE 64
#define MAILBOX_READ4K_SIZE 4096
#define MAILBOX_READ_MAX_SIZE MAILBOX_READ4K_SIZE
#define MAILBOX_BATCH_MAX_PAGES 16
#define MAILBOX_LINEAR_MAX_PAGES 128

#define MAILBOX_ERROR_NONE             0
#define MAILBOX_ERROR_TIMEOUT          1
#define MAILBOX_ERROR_SATA_RX_CRC      2
#define MAILBOX_ERROR_SATA_FIS_LENGTH  3
#define MAILBOX_ERROR_SATA_TX          4
#define MAILBOX_ERROR_SATA_PHY         5
#define MAILBOX_ERROR_USB_RESET        6
#define MAILBOX_ERROR_SATA_FIFO_OV     7

void MailboxInit(void);
void MailboxService(void);
UINT32 MailboxQueue1337(void);
UINT32 MailboxQueueRead(UINT32 address_high, UINT32 address_low, UINT16 size);
UINT32 MailboxQueueReadBatch(const UINT32 *address_high,
                             const UINT32 *address_low, UINT8 page_count);
UINT32 MailboxQueueReadLinear(UINT32 address_high, UINT32 address_low,
                              UINT8 page_count);
UINT32 MailboxQueueSetMap(const UINT32 *ranges, UINT8 range_count);
UINT8 MailboxBusy(void);
UINT8 MailboxCommandPending(void);
UINT32 MailboxPendingCommand(void);
UINT32 MailboxPendingSequence(void);
UINT32 MailboxPendingAddressHigh(void);
UINT32 MailboxPendingAddressLow(void);
UINT32 MailboxPendingReadSize(void);
UINT32 MailboxReadOffset(void);
UINT8 MailboxPendingBatchCount(void);
UINT32 MailboxPendingBatchAddressHigh(UINT8 index);
UINT32 MailboxPendingBatchAddressLow(UINT8 index);
UINT32 MailboxPendingMapWord(UINT8 index);
void MailboxControllerAck(UINT32 address_low, UINT32 address_high);
void MailboxControllerProgress(void);
UINT8 MailboxControllerReadChunk(const UINT8 *data);
UINT8 MailboxControllerReadData(const UINT8 *data, UINT16 size);
void MailboxAbort(UINT8 error_code);
UINT8 MailboxTakeControllerAck(UINT32 *sequence, UINT32 *address_low,
                               UINT32 *address_high);
UINT8 MailboxPeekReadResult(const UINT8 **data, UINT16 *size,
                            UINT32 *sequence, UINT32 *address_low,
                            UINT32 *address_high);
void MailboxReleaseReadResult(void);
void MailboxControllerBatchComplete(void);
void MailboxReleaseBatchResult(void);
UINT8 MailboxTakeError(UINT32 *sequence, UINT32 *address_low,
                       UINT32 *address_high, UINT8 *error_code);

#endif
