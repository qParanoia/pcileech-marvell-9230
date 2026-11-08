#include "mailbox.h"

static volatile UINT8 command_pending;
static volatile UINT8 ack_unread;
static volatile UINT32 next_sequence;
static volatile UINT32 pending_sequence;
static volatile UINT32 pending_command;
static volatile UINT32 pending_address_low;
static volatile UINT32 pending_address_high;
static volatile UINT32 pending_read_size;
static volatile UINT8 pending_batch_count;
static volatile UINT32 pending_map_words[32];
static volatile UINT32 pending_batch_address_low[MAILBOX_BATCH_MAX_PAGES];
static volatile UINT32 pending_batch_address_high[MAILBOX_BATCH_MAX_PAGES];
static volatile UINT32 ack_sequence;
static volatile UINT32 ack_address_low;
static volatile UINT32 ack_address_high;
static volatile UINT8 read_data[MAILBOX_READ_MAX_SIZE];
static volatile UINT32 read_offset;
static volatile UINT8 read_done;
static volatile UINT16 read_result_size;
static volatile UINT32 read_result_sequence;
static volatile UINT32 read_result_address_low;
static volatile UINT32 read_result_address_high;
static volatile UINT8 error_unread;
static volatile UINT8 batch_result_pending;
static volatile UINT8 error_result_code;
static volatile UINT32 error_sequence;
static volatile UINT32 error_address_low;
static volatile UINT32 error_address_high;
static UINT32 timeout_last_count;
static UINT32 timeout_elapsed_ticks;

#define TIMER_COUNT_MASK 0x03FFFFFFUL
#define MAILBOX_TIMEOUT_TICKS (2UL * FREQ_SYS)

void MailboxInit(void)
{
    command_pending = 0;
    ack_unread = 0;
    next_sequence = 0;
    pending_sequence = 0;
    pending_command = 0;
    pending_address_low = 0;
    pending_address_high = 0;
    pending_read_size = 0;
    pending_batch_count = 0;
    ack_sequence = 0;
    ack_address_low = 0;
    ack_address_high = 0;
    read_offset = 0;
    read_done = 0;
    read_result_size = 0;
    read_result_sequence = 0;
    read_result_address_low = 0;
    read_result_address_high = 0;
    error_unread = 0;
    batch_result_pending = 0;
    error_result_code = MAILBOX_ERROR_NONE;
    error_sequence = 0;
    error_address_low = 0;
    error_address_high = 0;
    timeout_elapsed_ticks = 0;

    R8_TMR0_CTRL_MOD = RB_TMR_ALL_CLEAR;
    R32_TMR0_CNT_END = TIMER_COUNT_MASK;
    R8_TMR0_INT_FLAG = RB_TMR_IF_CYC_END;
    R8_TMR0_CTRL_MOD = RB_TMR_COUNT_EN;
    timeout_last_count = R32_TMR0_COUNT & TIMER_COUNT_MASK;
}

void MailboxService(void)
{
    UINT32 now;
    UINT32 delta;

    now = R32_TMR0_COUNT & TIMER_COUNT_MASK;
    delta = (now - timeout_last_count) & TIMER_COUNT_MASK;
    timeout_last_count = now;
    if (!command_pending) {
        timeout_elapsed_ticks = 0;
        return;
    }
    timeout_elapsed_ticks += delta;
    if (timeout_elapsed_ticks >= MAILBOX_TIMEOUT_TICKS) {
        MailboxAbort(MAILBOX_ERROR_TIMEOUT);
    }
}

UINT32 MailboxQueue1337(void)
{
    if (MailboxBusy()) {
        return 0;
    }
    next_sequence++;
    if (next_sequence == 0) {
        next_sequence = 1;
    }
    pending_sequence = next_sequence;
    pending_command = MAILBOX_COMMAND_1337;
    pending_address_low = 0;
    pending_address_high = 0;
    pending_read_size = 0;
    command_pending = 1;
    ack_unread = 0;
    read_offset = 0;
    read_done = 0;
    read_result_size = 0;
    error_unread = 0;
    error_result_code = MAILBOX_ERROR_NONE;
    timeout_elapsed_ticks = 0;
    return pending_sequence;
}

UINT32 MailboxQueueRead(UINT32 address_high, UINT32 address_low, UINT16 size)
{
    if ((size != MAILBOX_READ64_SIZE && size != MAILBOX_READ4K_SIZE) ||
        MailboxBusy()) {
        return 0;
    }
    next_sequence++;
    if (next_sequence == 0) {
        next_sequence = 1;
    }
    pending_sequence = next_sequence;
    pending_command = size == MAILBOX_READ64_SIZE ?
                      MAILBOX_COMMAND_READ64 : MAILBOX_COMMAND_READ4K;
    pending_read_size = size;
    pending_batch_count = 0;
    pending_address_high = address_high;
    pending_address_low = address_low;
    command_pending = 1;
    ack_unread = 0;
    read_offset = 0;
    read_done = 0;
    read_result_size = 0;
    error_unread = 0;
    error_result_code = MAILBOX_ERROR_NONE;
    timeout_elapsed_ticks = 0;
    return pending_sequence;
}

UINT32 MailboxQueueReadBatch(const UINT32 *address_high,
                             const UINT32 *address_low, UINT8 page_count)
{
    UINT8 i;

    if (page_count == 0 || page_count > MAILBOX_BATCH_MAX_PAGES ||
        MailboxBusy()) {
        return 0;
    }
    next_sequence++;
    if (next_sequence == 0) {
        next_sequence = 1;
    }
    pending_sequence = next_sequence;
    pending_command = MAILBOX_COMMAND_READ_BATCH;
    pending_batch_count = page_count;
    pending_read_size = (UINT32)page_count * MAILBOX_READ4K_SIZE;
    for (i = 0; i < page_count; ++i) {
        pending_batch_address_high[i] = address_high[i];
        pending_batch_address_low[i] = address_low[i];
    }
    pending_address_high = address_high[0];
    pending_address_low = address_low[0];
    command_pending = 1;
    ack_unread = 0;
    read_offset = 0;
    read_done = 0;
    read_result_size = 0;
    error_unread = 0;
    error_result_code = MAILBOX_ERROR_NONE;
    batch_result_pending = 0;
    timeout_elapsed_ticks = 0;
    return pending_sequence;
}

UINT32 MailboxQueueReadLinear(UINT32 address_high, UINT32 address_low,
                              UINT8 page_count)
{
    if (page_count == 0 || page_count > MAILBOX_LINEAR_MAX_PAGES ||
        MailboxBusy()) {
        return 0;
    }
    next_sequence++;
    if (next_sequence == 0) {
        next_sequence = 1;
    }
    pending_sequence = next_sequence;
    pending_command = MAILBOX_COMMAND_READ_LINEAR;
    pending_batch_count = page_count;
    pending_read_size = (UINT32)page_count * MAILBOX_READ4K_SIZE;
    pending_address_high = address_high;
    pending_address_low = address_low;
    command_pending = 1;
    ack_unread = 0;
    read_offset = 0;
    read_done = 0;
    read_result_size = 0;
    error_unread = 0;
    error_result_code = MAILBOX_ERROR_NONE;
    batch_result_pending = 0;
    timeout_elapsed_ticks = 0;
    return pending_sequence;
}

UINT32 MailboxQueueSetMap(const UINT32 *ranges, UINT8 range_count)
{
    UINT8 i;
    if (range_count == 0 || range_count > 8 || MailboxBusy()) {
        return 0;
    }
    next_sequence++;
    if (next_sequence == 0) {
        next_sequence = 1;
    }
    pending_sequence = next_sequence;
    pending_command = MAILBOX_COMMAND_SET_MAP;
    pending_batch_count = range_count;
    for (i = 0; i < range_count * 4u; ++i) {
        pending_map_words[i] = ranges[i];
    }
    command_pending = 1;
    ack_unread = 0;
    read_offset = 0;
    read_done = 0;
    read_result_size = 0;
    error_unread = 0;
    error_result_code = MAILBOX_ERROR_NONE;
    batch_result_pending = 0;
    timeout_elapsed_ticks = 0;
    return pending_sequence;
}

UINT8 MailboxBusy(void)
{
    return command_pending || ack_unread || read_done || error_unread ||
           batch_result_pending;
}

UINT8 MailboxCommandPending(void)
{
    return command_pending;
}

UINT32 MailboxPendingSequence(void)
{
    return pending_sequence;
}

UINT32 MailboxPendingCommand(void)
{
    return pending_command;
}

UINT32 MailboxPendingAddressHigh(void)
{
    return pending_address_high;
}

UINT32 MailboxPendingAddressLow(void)
{
    return pending_address_low;
}

UINT32 MailboxPendingReadSize(void)
{
    return pending_read_size;
}

UINT32 MailboxReadOffset(void)
{
    return read_offset;
}

UINT8 MailboxPendingBatchCount(void)
{
    return pending_batch_count;
}

UINT32 MailboxPendingBatchAddressHigh(UINT8 index)
{
    return index < pending_batch_count ? pending_batch_address_high[index] : 0;
}

UINT32 MailboxPendingMapWord(UINT8 index)
{
    return index < 32u ? pending_map_words[index] : 0;
}

UINT32 MailboxPendingBatchAddressLow(UINT8 index)
{
    return index < pending_batch_count ? pending_batch_address_low[index] : 0;
}

void MailboxControllerAck(UINT32 address_low, UINT32 address_high)
{
    if (command_pending) {
        ack_sequence = pending_sequence;
        ack_address_low = address_low;
        ack_address_high = address_high;
        command_pending = 0;
        pending_command = 0;
        ack_unread = 1;
    }
}

void MailboxControllerProgress(void)
{
    if (command_pending) {
        timeout_elapsed_ticks = 0;
    }
}

UINT8 MailboxControllerReadChunk(const UINT8 *data)
{
    UINT8 i;

    if (!command_pending ||
        (pending_command != MAILBOX_COMMAND_READ64 &&
         pending_command != MAILBOX_COMMAND_READ4K) ||
        read_offset >= pending_read_size) {
        return 0;
    }
    for (i = 0; i < 8; ++i) {
        read_data[read_offset++] = data[i];
    }
    if (read_offset == pending_read_size) {
        read_result_size = pending_read_size;
        read_result_sequence = pending_sequence;
        read_result_address_low = pending_address_low;
        read_result_address_high = pending_address_high;
        command_pending = 0;
        pending_command = 0;
        pending_read_size = 0;
        read_done = 1;
        return 1;
    }
    return 0;
}

UINT8 MailboxControllerReadData(const UINT8 *data, UINT16 size)
{
    UINT8 done;

    if ((size & 7) != 0) {
        return 0;
    }
    done = 0;
    while (size != 0 && command_pending) {
        done = MailboxControllerReadChunk(data);
        data += 8;
        size -= 8;
    }
    return done;
}

void MailboxAbort(UINT8 error_code)
{
    if (!command_pending) {
        return;
    }
    error_sequence = pending_sequence;
    error_address_low = pending_address_low;
    error_address_high = pending_address_high;
    error_result_code = error_code;
    error_unread = 1;
    command_pending = 0;
    pending_command = 0;
    pending_read_size = 0;
    pending_batch_count = 0;
    read_offset = 0;
    read_done = 0;
    read_result_size = 0;
    timeout_elapsed_ticks = 0;
}

UINT8 MailboxTakeControllerAck(UINT32 *sequence, UINT32 *address_low,
                               UINT32 *address_high)
{
    if (!ack_unread) {
        return 0;
    }
    *sequence = ack_sequence;
    *address_low = ack_address_low;
    *address_high = ack_address_high;
    ack_unread = 0;
    return 1;
}

UINT8 MailboxPeekReadResult(const UINT8 **data, UINT16 *size,
                            UINT32 *sequence, UINT32 *address_low,
                            UINT32 *address_high)
{
    if (!read_done) {
        return 0;
    }
    *data = (const UINT8 *)read_data;
    *size = read_result_size;
    *sequence = read_result_sequence;
    *address_low = read_result_address_low;
    *address_high = read_result_address_high;
    return 1;
}

void MailboxReleaseReadResult(void)
{
    read_done = 0;
    read_result_size = 0;
}

void MailboxControllerBatchComplete(void)
{
    if (!command_pending ||
        (pending_command != MAILBOX_COMMAND_READ_BATCH &&
         pending_command != MAILBOX_COMMAND_READ_LINEAR)) {
        return;
    }
    command_pending = 0;
    pending_command = 0;
    pending_read_size = 0;
    read_offset = 0;
    batch_result_pending = 1;
    timeout_elapsed_ticks = 0;
}

void MailboxReleaseBatchResult(void)
{
    batch_result_pending = 0;
    pending_batch_count = 0;
}

UINT8 MailboxTakeError(UINT32 *sequence, UINT32 *address_low,
                       UINT32 *address_high, UINT8 *error_code)
{
    if (!error_unread) {
        return 0;
    }
    *sequence = error_sequence;
    *address_low = error_address_low;
    *address_high = error_address_high;
    *error_code = error_result_code;
    error_unread = 0;
    error_result_code = MAILBOX_ERROR_NONE;
    return 1;
}
