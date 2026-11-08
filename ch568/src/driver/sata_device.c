#include <string.h>

#include "CH568SFR.h"
#include "mailbox.h"
#include "sata_device.h"
#include "usb_mailbox.h"

#define ATA_IDENTIFY_DEVICE 0xEC
#define ATA_SET_FEATURES    0xEF
#define ATA_READ_DMA        0xC8
#define ATA_READ_DMA_EXT    0x25
#define ATA_WRITE_DMA_EXT   0x35
#define ATA_VENDOR_POLL     0xF0
#define ATA_VENDOR_ACK      0xF1
#define ATA_POLL_FEATURE    0x37
#define ATA_ACK_FEATURE     0xA5

#define ATA_SR_DRDY         0x40
#define ATA_SR_DSC          0x10
#define ATA_SR_DRQ          0x08
#define ATA_SR_ERR          0x01
#define ATA_ER_ABRT         0x04
#define ATA_DC_SRST         0x04

#define MAILBOX_MAGIC       0x314D4843UL
#define MAILBOX_LBA_LOW     0x000007FDUL
#define MAILBOX_LBA_HIGH    0x00000000UL
#define MAILBOX_WRITE_LBA_LOW 0x000007F0UL
#define MAILBOX_BATCH_LBA_LOW 0x000007E0UL
#define MAILBOX_LINEAR_LBA_LOW 0x000007D0UL

#define SATA_CONTROL_RUN      (bSC_DMA_EN | bSC_INT_BUSY | bSC_FORCE_1P5G)


__attribute__((aligned(8))) static UINT32 sata_rx[2080];
__attribute__((aligned(8))) static UINT32 sata_tx[2080];
__attribute__((aligned(8))) static UINT32 sata_payload[128];
static UINT8 signature_sent;
static UINT8 identify_logged;
static UINT8 set_features_logged;
static UINT8 read_dma_legacy_logged;
static UINT8 read_dma_logged;
static UINT8 read_dma_detail_count;
static UINT8 poll_logged;
static UINT8 command_delivered_logged;
static UINT8 read4k_chunk_logged;
static UINT8 tx_error_logged;
static UINT8 rx_error_logged;
static UINT8 fifo_over_logged;
static UINT8 pending_status_logged;
static UINT8 phy_retry_count;
static UINT8 soft_reset_asserted;
static UINT8 response_pmp;
static UINT32 phy_wait_count;
static UINT8 command_seen[32];
static UINT8 bulk_write_active;
static UINT8 batch_write_active;
static UINT8 batch_chunk_waiting;
static UINT8 hold_rx_ready;
static UINT32 batch_expected_size;
static UINT32 batch_received_size;


static volatile UINT8 *batch_rx_current;

#define PHY_WAIT_LIMIT 8000000UL

static char hex_digit(UINT8 value)
{
    value &= 0x0F;
    return (char)(value < 10 ? ('0' + value) : ('A' + value - 10));
}

static char *append_text(char *cursor, const char *text)
{
    while (*text) {
        *cursor++ = *text++;
    }
    return cursor;
}

static char *append_hex8(char *cursor, UINT8 value)
{
    *cursor++ = hex_digit((UINT8)(value >> 4));
    *cursor++ = hex_digit(value);
    return cursor;
}

static char *append_hex16(char *cursor, UINT16 value)
{
    cursor = append_hex8(cursor, (UINT8)(value >> 8));
    return append_hex8(cursor, (UINT8)value);
}

static void log_sata_state(const char *reason)
{
    char message[64];
    char *cursor;

    cursor = append_text(message, "LOG SATA ");
    cursor = append_text(cursor, reason);
    cursor = append_text(cursor, " C=");
    cursor = append_hex8(cursor, R8_SATA_CTRL);
    cursor = append_text(cursor, " M=");
    cursor = append_hex8(cursor, R8_SATA_MOD);
    cursor = append_text(cursor, " S=");
    cursor = append_hex8(cursor, R8_SATA_INT_ST);
    cursor = append_text(cursor, " F=");
    cursor = append_hex16(cursor, R16_SATA_INT_FG);
    cursor = append_text(cursor, " R=");
    cursor = append_hex8(cursor, R8_SATA_RTX_CTRL);
    cursor = append_text(cursor, " P=");
    cursor = append_hex8(cursor, R8_SLP_POWER_CTRL);
    *cursor++ = '\r';
    *cursor++ = '\n';
    *cursor = 0;
    USB1Log(message);
}

static void log_srst(const char *phase, UINT8 control)
{
    char message[64];
    char *cursor;

    cursor = append_text(message, "LOG SATA SRST ");
    cursor = append_text(cursor, phase);
    cursor = append_text(cursor, " CT=");
    cursor = append_hex8(cursor, control);
    cursor = append_text(cursor, " PMP=");
    *cursor++ = hex_digit(response_pmp);
    *cursor++ = '\r';
    *cursor++ = '\n';
    *cursor = 0;
    USB1Log(message);
}

static void log_ata_command_once(UINT8 command, UINT8 feature)
{
    char message[40];
    char *cursor;
    UINT8 mask;

    mask = (UINT8)(1U << (command & 7));
    if (command_seen[command >> 3] & mask) {
        return;
    }
    command_seen[command >> 3] |= mask;

    cursor = append_text(message, "LOG SATA ATA C=");
    cursor = append_hex8(cursor, command);
    cursor = append_text(cursor, " F=");
    cursor = append_hex8(cursor, feature);
    cursor = append_text(cursor, " P=");
    *cursor++ = hex_digit(response_pmp);
    *cursor++ = '\r';
    *cursor++ = '\n';
    *cursor = 0;
    USB1Log(message);
}

static void log_read_dma_detail(UINT32 lba_low, UINT32 lba_high,
                                UINT16 sector_count)
{
    char message[56];
    char *cursor;

    if (read_dma_detail_count >= 4) {
        return;
    }
    read_dma_detail_count++;
    cursor = append_text(message, "LOG SATA READ25 L=");
    cursor = append_hex16(cursor, (UINT16)(lba_low >> 8));
    cursor = append_hex8(cursor, (UINT8)lba_low);
    cursor = append_text(cursor, " H=");
    cursor = append_hex16(cursor, (UINT16)(lba_high >> 8));
    cursor = append_hex8(cursor, (UINT8)lba_high);
    cursor = append_text(cursor, " N=");
    cursor = append_hex16(cursor, sector_count);
    *cursor++ = '\r';
    *cursor++ = '\n';
    *cursor = 0;
    USB1Log(message);
}

static void make_mailbox_payload(void)
{
    UINT32 command;

    memset(sata_payload, 0, sizeof(sata_payload));
    if (!MailboxCommandPending()) {
        return;
    }
    command = MailboxPendingCommand();
    sata_payload[0] = MAILBOX_MAGIC;
    sata_payload[1] = command;
    if (command == MAILBOX_COMMAND_READ_BATCH) {
        UINT8 i;

        sata_payload[2] = MailboxPendingBatchCount();
        sata_payload[3] = MailboxPendingSequence();
        for (i = 0; i < MailboxPendingBatchCount(); ++i) {
            sata_payload[4 + (UINT16)i * 2] =
                MailboxPendingBatchAddressLow(i);
            sata_payload[5 + (UINT16)i * 2] =
                MailboxPendingBatchAddressHigh(i);
        }
    } else if (command == MAILBOX_COMMAND_READ_LINEAR) {

        sata_payload[2] = MailboxPendingAddressHigh();
        sata_payload[3] = MailboxPendingAddressLow();
        sata_payload[4] = MailboxPendingBatchCount();
    } else if (command == MAILBOX_COMMAND_SET_MAP) {

        UINT8 i;
        sata_payload[2] = MailboxPendingBatchCount();
        sata_payload[3] = 0;
        for (i = 0; i < MailboxPendingBatchCount() * 4u; ++i) {
            sata_payload[4 + (UINT16)i] = MailboxPendingMapWord(i);
        }
    } else {
        sata_payload[2] = MailboxPendingAddressHigh();
        sata_payload[3] = MailboxPendingAddressLow();
    }
}

static void restart_phy(void)
{
    volatile UINT16 delay;

    R8_SATA_CTRL = SATA_CONTROL_RUN | bSC_RESET_PHY;
    for (delay = 0; delay < 2000; ++delay) {
        ;
    }
    R16_SATA_INT_FG = 0x3FFF;
    R8_SATA_CTRL = SATA_CONTROL_RUN;
    R8_SATA_RTX_CTRL = bSRC_R_READY;
    R16_SATA_DMA0 = (UINT16)(UINT32)sata_rx;
    batch_rx_current = (volatile UINT8 *)sata_rx;
    signature_sent = 0;
    bulk_write_active = 0;
    batch_write_active = 0;
    batch_chunk_waiting = 0;
    hold_rx_ready = 0;
    phy_wait_count = 0;
}

static void batch_rx_restore(void)
{
    batch_rx_current = (volatile UINT8 *)sata_rx;
    R16_SATA_DMA0 = (UINT16)(UINT32)sata_rx;
}

static UINT8 sata_send(UINT32 first_dword, const void *tail, UINT16 total_length)
{
    UINT32 timeout;

    timeout = 200000;
    while (!(R8_SATA_INT_ST & bSIS_LINK_FREE) && --timeout) {
        ;
    }
    if (!timeout) {
        if (!tx_error_logged) {
            USB1Log("ERR SATA link busy timeout\r\n");
            tx_error_logged = 1;
        }
        return 0;
    }

    R16_SATA_INT_FG = bSIF_TRAN_OK | bSIF_TRAN_INT | bSIF_COLLIDE;
    R32_SATA_DATA1 = first_dword;
    R16_SATA_DMA1 = (UINT16)(UINT32)tail;
    R16_SATA_TX_LEN = total_length;
    R8_SATA_RTX_CTRL |= bSRC_T_READY;

    timeout = 400000;
    while (!(R16_SATA_INT_FG & (bSIF_TRAN_OK | bSIF_TRAN_INT | bSIF_COLLIDE)) && --timeout) {
        ;
    }
    R8_SATA_RTX_CTRL &= (UINT8)~bSRC_T_READY;
    if (!timeout || !(R16_SATA_INT_FG & bSIF_TRAN_OK) ||
        !(R8_SATA_INT_ST & bSIS_TRAN_CRC_OK)) {
        R16_SATA_INT_FG = bSIF_TRAN_OK | bSIF_TRAN_INT | bSIF_COLLIDE;
        if (!tx_error_logged) {
            USB1Log("ERR SATA TX timeout or CRC\r\n");
            tx_error_logged = 1;
        }
        return 0;
    }
    tx_error_logged = 0;
    R16_SATA_INT_FG = bSIF_TRAN_OK;
    return 1;
}

static void ata_string(UINT16 *words, UINT8 first_word, UINT8 word_count, const char *text)
{
    UINT8 i;
    UINT8 a;
    UINT8 b;

    for (i = 0; i < word_count; ++i) {
        a = *text ? (UINT8)*text++ : (UINT8)' ';
        b = *text ? (UINT8)*text++ : (UINT8)' ';
        words[first_word + i] = ((UINT16)a << 8) | b;
    }
}

static void make_identify(void)
{
    UINT16 *w;
    UINT8 *bytes;
    UINT16 i;
    UINT8 sum;

    memset(sata_payload, 0, 512);
    w = (UINT16 *)sata_payload;
    w[0] = 0x0040;
    w[1] = 1;
    w[3] = 1;
    w[6] = 1;
    ata_string(w, 10, 10, "CH568-000000000001");
    ata_string(w, 23, 4, "3.0");
    ata_string(w, 27, 20, "CH568 MV9230 USB SATA MAILBOX");
    w[47] = 0x8001;
    w[49] = 0x0300;
    w[53] = 0x0007;
    w[60] = 0x0800;
    w[61] = 0;
    w[63] = 0x0007;
    w[80] = 0x01F0;
    w[82] = 0;
    w[83] = 0;
    w[84] = 0;
    w[88] = 0x003F;

    bytes = (UINT8 *)sata_payload;
    bytes[510] = 0xA5;
    bytes[511] = 0;
    sum = 0;
    for (i = 0; i < 511; ++i) {
        sum = (UINT8)(sum + bytes[i]);
    }
    bytes[511] = (UINT8)(0 - sum);
}

static UINT8 send_status(UINT8 status, UINT8 error)
{
    UINT32 first;

    memset(sata_tx, 0, 16);
    first = (UINT32)SATA_FIS_REGDEVICE |
            ((UINT32)(0x40 | response_pmp) << 8) |
            ((UINT32)status << 16) |
            ((UINT32)error << 24);
    return sata_send(first, sata_tx, 20);
}

static UINT8 send_dma_activate(void)
{


    static UINT8 activate_scratch[16];
    UINT32 first;

    memset(activate_scratch, 0, sizeof activate_scratch);
    first = (UINT32)SATA_FIS_DMAACT | ((UINT32)response_pmp << 8);
    return sata_send(first, activate_scratch, 4);
}

static UINT8 send_signature(void)
{
    UINT8 *tail;
    UINT32 first;

    memset(sata_tx, 0, 16);
    tail = (UINT8 *)sata_tx;
    tail[0] = 1;
    tail[8] = 1;
    first = (UINT32)SATA_FIS_REGDEVICE |
            ((UINT32)(0x40 | response_pmp) << 8) |
            ((UINT32)(ATA_SR_DRDY | ATA_SR_DSC) << 16);
    return sata_send(first, sata_tx, 20);
}

static UINT8 send_pio_data(const void *payload, UINT16 payload_length)
{
    UINT8 *tail;
    UINT32 first;

    memset(sata_tx, 0, 20);
    tail = (UINT8 *)sata_tx;
    tail[11] = ATA_SR_DRDY | ATA_SR_DSC;
    tail[12] = (UINT8)payload_length;
    tail[13] = (UINT8)(payload_length >> 8);
    first = (UINT32)SATA_FIS_PIOSETUP |
            ((UINT32)(0x60 | response_pmp) << 8) |
            ((UINT32)(ATA_SR_DRDY | ATA_SR_DSC | ATA_SR_DRQ) << 16);
    if (!sata_send(first, sata_tx, 20)) {
        return 0;
    }

    memcpy(sata_tx, payload, payload_length);
    if (!sata_send((UINT32)SATA_FIS_TRANDATA, sata_tx, (UINT16)(payload_length + 4))) {
        return 0;
    }
    return send_status(ATA_SR_DRDY | ATA_SR_DSC, 0);
}

static UINT8 send_dma_sectors(const void *payload, UINT16 sector_count)
{
    UINT32 first;

    if (sector_count == 0 || sector_count > 8) {
        return 0;
    }
    first = (UINT32)SATA_FIS_TRANDATA |
            ((UINT32)response_pmp << 8);
    while (sector_count--) {
        memcpy(sata_tx, payload, 512);
        if (!sata_send(first, sata_tx, 516)) {
            return 0;
        }
    }
    return send_status(ATA_SR_DRDY | ATA_SR_DSC, 0);
}

static void process_h2d(UINT32 first, UINT16 total_length)
{
    UINT8 command;
    UINT8 feature;
    UINT8 control;
    UINT8 *tail;
    UINT32 address_low;
    UINT32 address_high;

    if ((UINT8)first == SATA_FIS_TRANDATA && batch_write_active) {
        UINT16 payload_length;
        UINT32 remaining;

        remaining = batch_expected_size - batch_received_size;
        if (total_length < 4) {
            batch_write_active = 0;
            batch_rx_restore();
            USB1BatchFinish(MAILBOX_ERROR_SATA_FIS_LENGTH);
            MailboxControllerBatchComplete();
            send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
            return;
        }
        payload_length = (UINT16)(total_length - 4);
        if (payload_length == 0 || payload_length > 8196 ||
            (payload_length & 3) != 0 || batch_chunk_waiting) {
            batch_write_active = 0;
            batch_rx_restore();
            USB1BatchFinish(MAILBOX_ERROR_SATA_FIS_LENGTH);
            MailboxControllerBatchComplete();
            send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
            return;
        }
        if ((UINT32)payload_length > remaining) {


            payload_length = (UINT16)remaining;
        }
        if (!USB1BatchAcceptSataChunk((const UINT8 *)batch_rx_current,
                                      payload_length)) {
            batch_write_active = 0;
            batch_rx_restore();
            USB1BatchFinish(MAILBOX_ERROR_SATA_FIS_LENGTH);
            MailboxControllerBatchComplete();
            send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
            return;
        }
        batch_received_size += payload_length;
        MailboxControllerProgress();
        batch_chunk_waiting = 1;
        hold_rx_ready = 1;
        return;
    }

    if ((UINT8)first == SATA_FIS_TRANDATA && bulk_write_active) {
        UINT16 payload_length;
        UINT32 remaining;

        remaining = MailboxPendingReadSize() - MailboxReadOffset();


        if (total_length < 4) {
            bulk_write_active = 0;
            USB1Log("ERR SATA READ4K-DMA invalid Data FIS length\r\n");
            MailboxAbort(MAILBOX_ERROR_SATA_FIS_LENGTH);
            send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
            return;
        }
        payload_length = (UINT16)(total_length - 4);
        if (payload_length == 0 || payload_length > remaining ||
            (payload_length & 7) != 0) {
            bulk_write_active = 0;
            USB1Log("ERR SATA READ4K-DMA invalid Data FIS length\r\n");
            MailboxAbort(MAILBOX_ERROR_SATA_FIS_LENGTH);
            send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
            return;
        }
        MailboxControllerReadData((const UINT8 *)sata_rx, payload_length);
        MailboxControllerProgress();
        if ((UINT32)payload_length == remaining) {
            bulk_write_active = 0;
            USB1Log("LOG SATA READ4K-DMA 4096 bytes received\r\n");
            send_status(ATA_SR_DRDY | ATA_SR_DSC, 0);
            command_delivered_logged = 0;
        } else {
            R8_SATA_RTX_CTRL |= bSRC_R_READY;
            if (!send_dma_activate()) {
                bulk_write_active = 0;
                USB1Log("ERR SATA READ4K-DMA next DMA Activate failed\r\n");
                MailboxAbort(MAILBOX_ERROR_SATA_TX);
            }
        }
        return;
    }

    if ((UINT8)first != SATA_FIS_REGHOST) {
        return;
    }

    response_pmp = (UINT8)(first >> 8) & 0x0F;
    if (!(first & 0x00008000UL)) {


        if (response_pmp != 0 && response_pmp != 0x0F) {
            return;
        }
        control = ((UINT8 *)sata_rx)[11];
        if (control & ATA_DC_SRST) {
            soft_reset_asserted = 1;
            signature_sent = 0;
            bulk_write_active = 0;
            if (batch_write_active) {
                batch_write_active = 0;
                batch_chunk_waiting = 0;
                batch_rx_restore();
                USB1BatchFinish(MAILBOX_ERROR_SATA_PHY);
                MailboxControllerBatchComplete();
            }
            log_srst("assert", control);
        } else if (soft_reset_asserted) {
            soft_reset_asserted = 0;
            identify_logged = 0;
            poll_logged = 0;
            command_delivered_logged = 0;
            log_srst("release", control);
            if (send_signature()) {
                signature_sent = 1;
                USB1Log("LOG SATA SRST signature sent\r\n");
            }
        }
        return;
    }


    if (response_pmp != 0) {
        return;
    }

    command = (UINT8)(first >> 16);
    feature = (UINT8)(first >> 24);
    tail = (UINT8 *)sata_rx;
    log_ata_command_once(command, feature);


    if (command == ATA_SET_FEATURES) {
        if (send_status(ATA_SR_DRDY | ATA_SR_DSC, 0) && !set_features_logged) {
            USB1Log("LOG SATA SET FEATURES EF accepted\r\n");
            set_features_logged = 1;
        }
        return;
    }

    if (command == ATA_IDENTIFY_DEVICE) {
        make_identify();
        send_pio_data(sata_payload, 512);
        if (!identify_logged) {
            USB1Log("LOG SATA IDENTIFY served\r\n");
            identify_logged = 1;
        }
        return;
    }


    if (command == ATA_READ_DMA) {
        UINT16 sector_count;

        sector_count = tail[8] ? tail[8] : 256;
        if (sector_count <= 8) {
            memset(sata_payload, 0, sizeof(sata_payload));
            if (send_dma_sectors(sata_payload, sector_count)) {
                if (!read_dma_legacy_logged) {
                    USB1Log("LOG SATA READ DMA C8 zero data served\r\n");
                    read_dma_legacy_logged = 1;
                }
            } else {
                send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
            }
        } else {
            USB1Log("ERR SATA READ DMA C8 sector count too large\r\n");
            send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
        }
        return;
    }

    if (command == ATA_READ_DMA_EXT) {
        UINT16 sector_count;
        UINT32 lba_low;
        UINT32 lba_high;

        sector_count = (UINT16)tail[8] | ((UINT16)tail[9] << 8);
        lba_low = (UINT32)tail[0] |
                  ((UINT32)tail[1] << 8) |
                  ((UINT32)tail[2] << 16);
        lba_high = (UINT32)tail[4] |
                   ((UINT32)tail[5] << 8) |
                   ((UINT32)tail[6] << 16);
        log_read_dma_detail(lba_low, lba_high, sector_count);
        if (feature == 0 && sector_count == 1 &&
            lba_low == MAILBOX_LBA_LOW && lba_high == MAILBOX_LBA_HIGH) {
            if (!poll_logged) {
                USB1Log("LOG SATA Marvell mailbox READ DMA EXT received\r\n");
                poll_logged = 1;
            }
            make_mailbox_payload();
            if (MailboxCommandPending()) {
                if (!command_delivered_logged) {
                    if (MailboxPendingCommand() == MAILBOX_COMMAND_READ64) {
                        USB1Log("LOG SATA command 1338 sent to Marvell\r\n");
                    } else if (MailboxPendingCommand() == MAILBOX_COMMAND_READ4K) {
                        USB1Log("LOG SATA command 133A sent to Marvell\r\n");
                    } else if (MailboxPendingCommand() ==
                               MAILBOX_COMMAND_READ_BATCH) {
                        USB1Log("LOG SATA command 133B sent to Marvell\r\n");
                    } else {
                        USB1Log("LOG SATA command 1337 sent to Marvell\r\n");
                    }
                    command_delivered_logged = 1;
                }
            }
            if (send_dma_sectors(sata_payload, 1)) {
                if (MailboxCommandPending()) {
                    USB1Log("LOG SATA mailbox DMA response complete\r\n");
                }
            } else if (MailboxCommandPending()) {
                USB1Log("ERR SATA mailbox DMA response failed\r\n");
            }
            return;
        }

        memset(sata_payload, 0, sizeof(sata_payload));
        if (send_dma_sectors(sata_payload, sector_count)) {
            if (!read_dma_logged) {
                USB1Log("LOG SATA READ DMA EXT zero data served\r\n");
                read_dma_logged = 1;
            }
        } else {
            send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
        }
        return;
    }

    if (command == ATA_WRITE_DMA_EXT) {
        UINT16 sector_count;
        UINT32 lba_low;
        UINT32 lba_high;

        sector_count = (UINT16)tail[8] | ((UINT16)tail[9] << 8);
        lba_low = (UINT32)tail[0] |
                  ((UINT32)tail[1] << 8) |
                  ((UINT32)tail[2] << 16);
        lba_high = (UINT32)tail[4] |
                   ((UINT32)tail[5] << 8) |
                   ((UINT32)tail[6] << 16);
        if (feature == 0 && sector_count == 8 &&
            lba_low == MAILBOX_WRITE_LBA_LOW &&
            lba_high == MAILBOX_LBA_HIGH &&
            MailboxPendingCommand() == MAILBOX_COMMAND_READ4K) {
            bulk_write_active = 1;
            USB1Log("LOG SATA READ4K-DMA WRITE35 received\r\n");
            R8_SATA_RTX_CTRL |= bSRC_R_READY;
            if (!send_dma_activate()) {
                bulk_write_active = 0;
                USB1Log("ERR SATA READ4K-DMA DMA Activate failed\r\n");
                MailboxAbort(MAILBOX_ERROR_SATA_TX);
                send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
            }
            return;
        }
        if (feature == 0 && MailboxPendingBatchCount() != 0 &&
            sector_count == (UINT16)MailboxPendingBatchCount() * 8 &&
            lba_high == MAILBOX_LBA_HIGH &&
            ((MailboxPendingCommand() == MAILBOX_COMMAND_READ_BATCH &&
              lba_low == MAILBOX_BATCH_LBA_LOW) ||
             (MailboxPendingCommand() == MAILBOX_COMMAND_READ_LINEAR &&
              lba_low == MAILBOX_LINEAR_LBA_LOW))) {
            batch_expected_size = MailboxPendingReadSize();
            batch_received_size = 0;
            batch_chunk_waiting = 0;
            batch_write_active = 1;
            fifo_over_logged = 0;
            batch_rx_restore();
            USB1BatchStart(MailboxPendingSequence(),
                           MailboxPendingBatchCount(), batch_expected_size);
            if (MailboxPendingCommand() == MAILBOX_COMMAND_READ_LINEAR) {
                USB1Log("LOG SATA READ-LINEAR WRITE35 received\r\n");
            } else {
                USB1Log("LOG SATA READ-BATCH WRITE35 received\r\n");
            }
            R8_SATA_RTX_CTRL |= bSRC_R_READY;
            if (!send_dma_activate()) {
                batch_write_active = 0;
                USB1BatchFinish(MAILBOX_ERROR_SATA_TX);
                MailboxControllerBatchComplete();
                send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
            }
            return;
        }
        send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
        return;
    }

    if (command == ATA_VENDOR_POLL && feature == ATA_POLL_FEATURE) {
        if (!poll_logged) {
            USB1Log("LOG SATA Marvell poll F0/37 received\r\n");
            poll_logged = 1;
        }
        make_mailbox_payload();
        if (MailboxCommandPending()) {
            if (!command_delivered_logged) {
                if (MailboxPendingCommand() == MAILBOX_COMMAND_READ64) {
                    USB1Log("LOG SATA command 1338 sent to Marvell\r\n");
                } else if (MailboxPendingCommand() == MAILBOX_COMMAND_READ4K) {
                    USB1Log("LOG SATA command 133A sent to Marvell\r\n");
                } else if (MailboxPendingCommand() ==
                           MAILBOX_COMMAND_READ_BATCH) {
                    USB1Log("LOG SATA command 133B sent to Marvell\r\n");
                } else {
                    USB1Log("LOG SATA command 1337 sent to Marvell\r\n");
                }
                command_delivered_logged = 1;
            }
        }


        if (send_pio_data(sata_payload, sizeof(sata_payload))) {
            if (MailboxCommandPending()) {
                USB1Log("LOG SATA poll PIO response complete\r\n");
            }
        } else if (MailboxCommandPending()) {
            USB1Log("ERR SATA poll PIO response failed\r\n");
        }
        return;
    }

    if (command == ATA_VENDOR_ACK && feature == ATA_ACK_FEATURE) {
        if (MailboxPendingCommand() == MAILBOX_COMMAND_SET_MAP) {


            USB1Log("LOG SATA set-map ack received\r\n");
            MailboxControllerAck(0x1342, 1);
            send_status(ATA_SR_DRDY | ATA_SR_DSC, 0);
            return;
        }
        if (MailboxPendingCommand() == MAILBOX_COMMAND_READ64 ||
            MailboxPendingCommand() == MAILBOX_COMMAND_READ4K) {
            UINT8 chunk[8];
            UINT8 is_read4k;
            UINT32 read_offset;

            is_read4k = MailboxPendingCommand() == MAILBOX_COMMAND_READ4K;
            chunk[0] = tail[0];
            chunk[1] = tail[1];
            chunk[2] = tail[2];
            chunk[3] = tail[4];
            chunk[4] = tail[5];
            chunk[5] = tail[6];
            chunk[6] = tail[8];
            chunk[7] = tail[9];
            if (MailboxPendingCommand() == MAILBOX_COMMAND_READ64 ||
                !read4k_chunk_logged) {
                USB1Log("LOG SATA memory-data F1/A5 received\r\n");
                if (MailboxPendingCommand() == MAILBOX_COMMAND_READ4K) {
                    read4k_chunk_logged = 1;
                }
            }
            MailboxControllerReadChunk(chunk);
            read_offset = MailboxReadOffset();
            if (is_read4k && (read_offset & 0x01FF) == 0) {
                switch (read_offset) {
                case 0x0200:
                    USB1Log("LOG SATA READ4K 512/4096 bytes received\r\n");
                    break;
                case 0x0400:
                    USB1Log("LOG SATA READ4K 1024/4096 bytes received\r\n");
                    break;
                case 0x0600:
                    USB1Log("LOG SATA READ4K 1536/4096 bytes received\r\n");
                    break;
                case 0x0800:
                    USB1Log("LOG SATA READ4K 2048/4096 bytes received\r\n");
                    break;
                case 0x0A00:
                    USB1Log("LOG SATA READ4K 2560/4096 bytes received\r\n");
                    break;
                case 0x0C00:
                    USB1Log("LOG SATA READ4K 3072/4096 bytes received\r\n");
                    break;
                case 0x0E00:
                    USB1Log("LOG SATA READ4K 3584/4096 bytes received\r\n");
                    break;
                case 0x1000:
                    USB1Log("LOG SATA READ4K 4096/4096 bytes received\r\n");
                    break;
                }
            }
            if (!MailboxCommandPending()) {
                read4k_chunk_logged = 0;
            }
            send_status(ATA_SR_DRDY | ATA_SR_DSC, 0);
            return;
        }
        address_low = (UINT32)tail[0] |
                      ((UINT32)tail[1] << 8) |
                      ((UINT32)tail[2] << 16) |
                      ((UINT32)tail[4] << 24);
        address_high = (UINT32)tail[5] |
                       ((UINT32)tail[6] << 8) |
                       ((UINT32)tail[8] << 16) |
                       ((UINT32)tail[9] << 24);
        USB1Log("LOG SATA Marvell ACK F1/A5 received\r\n");
        MailboxControllerAck(address_low, address_high);
        send_status(ATA_SR_DRDY | ATA_SR_DSC, 0);
        command_delivered_logged = 0;
        return;
    }

    send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
}

void SATADeviceInit(void)
{
    signature_sent = 0;
    identify_logged = 0;
    set_features_logged = 0;
    read_dma_legacy_logged = 0;
    read_dma_logged = 0;
    read_dma_detail_count = 0;
    poll_logged = 0;
    command_delivered_logged = 0;
    read4k_chunk_logged = 0;
    bulk_write_active = 0;
    batch_write_active = 0;
    batch_chunk_waiting = 0;
    hold_rx_ready = 0;
    batch_expected_size = 0;
    batch_received_size = 0;
    batch_rx_current = (volatile UINT8 *)sata_rx;
    tx_error_logged = 0;
    rx_error_logged = 0;
    fifo_over_logged = 0;
    pending_status_logged = 0;
    phy_retry_count = 0;
    soft_reset_asserted = 0;
    response_pmp = 0;
    phy_wait_count = 0;
    memset(command_seen, 0, sizeof(command_seen));
    memset(sata_rx, 0, sizeof(sata_rx));
    memset(sata_tx, 0, sizeof(sata_tx));

    R8_SATA_CTRL = bSC_CLR_ALL | bSC_FORCE_1P5G |
                   bSC_RESET_PHY | bSC_RESET_LINK;
    R8_SATA_CTRL = SATA_CONTROL_RUN | bSC_RESET_PHY | bSC_RESET_LINK;
    R8_SATA_PM_CTRL = bSPC_DENY;
    R8_SATA_MOD = bSM_RX_EN | bSM_TX_EN;
    R16_SATA_DMA0 = (UINT16)(UINT32)sata_rx;
    R16_SATA_DMA1 = (UINT16)(UINT32)sata_tx;
    R16_SATA_INT_FG = 0x3FFF;
    R8_SATA_RTX_CTRL = bSRC_R_READY;
    R8_SATA_CTRL = SATA_CONTROL_RUN;
    USB1Log("LOG SATA waiting for PHY forced 1.5G\r\n");
}

void SATADeviceService(void)
{
    UINT16 flags;
    UINT16 receive_length;
    UINT32 first;

    if (bulk_write_active &&
        MailboxPendingCommand() != MAILBOX_COMMAND_READ4K) {
        bulk_write_active = 0;
    }
    if (batch_write_active &&
        MailboxPendingCommand() != MAILBOX_COMMAND_READ_BATCH &&
        MailboxPendingCommand() != MAILBOX_COMMAND_READ_LINEAR) {
        batch_write_active = 0;
        batch_chunk_waiting = 0;
        hold_rx_ready = 0;
        batch_rx_restore();
        USB1BatchFinish(MAILBOX_ERROR_TIMEOUT);
    }

    if (MailboxCommandPending()) {
        if (!pending_status_logged) {
            log_sata_state("CMD");
            pending_status_logged = 1;
        }
    } else {
        pending_status_logged = 0;
    }

    flags = R16_SATA_INT_FG;

    if (flags & bSIF_PHYERR) {
        log_sata_state("PHYERR");
        R16_SATA_INT_FG = bSIF_PHYERR;
        if (batch_write_active) {
            batch_write_active = 0;
            batch_chunk_waiting = 0;
            batch_rx_restore();
            USB1BatchFinish(MAILBOX_ERROR_SATA_PHY);
            MailboxControllerBatchComplete();
        } else {
            MailboxAbort(MAILBOX_ERROR_SATA_PHY);
        }
        phy_retry_count++;
        restart_phy();
        USB1Log("LOG SATA retry forced 1.5G\r\n");
        return;
    }

    if (!(R8_SATA_INT_ST & bSIS_PHYRDY)) {
        if (batch_write_active) {
            batch_write_active = 0;
            batch_chunk_waiting = 0;
            batch_rx_restore();
            USB1BatchFinish(MAILBOX_ERROR_SATA_PHY);
            MailboxControllerBatchComplete();
        } else {
            MailboxAbort(MAILBOX_ERROR_SATA_PHY);
        }
        signature_sent = 0;
        soft_reset_asserted = 0;
        bulk_write_active = 0;
        response_pmp = 0;
        R8_SATA_RTX_CTRL |= bSRC_R_READY;
        if (flags & bSIF_PHYRDY) {
            R16_SATA_INT_FG = bSIF_PHYRDY;
        }
        if (++phy_wait_count >= PHY_WAIT_LIMIT) {
            phy_retry_count++;
            restart_phy();
            USB1Log("LOG SATA retry forced 1.5G\r\n");
        }
        return;
    }

    if (!signature_sent && !soft_reset_asserted) {
        phy_wait_count = 0;
        response_pmp = 0;
        R16_SATA_INT_FG = bSIF_PHYRDY;
        if (send_signature()) {
            signature_sent = 1;
            phy_retry_count = 0;
            USB1Log("LOG SATA PHY ready and signature sent\r\n");
        }
    }

    flags = R16_SATA_INT_FG;
    if (flags & bSIF_RECV_OK) {
        first = R32_SATA_DATA0;
        receive_length = R16_SATA_RX_LEN;
        if (batch_write_active) {
            USB1BatchSetSataDiagnostics(flags, receive_length);
        }
        R8_SATA_RTX_CTRL &= (UINT8)~bSRC_R_READY;
        if (R8_SATA_INT_ST & bSIS_RECV_CRC_OK) {
            R16_SATA_INT_FG = bSIF_RECV_OK;
            hold_rx_ready = 0;
            process_h2d(first, receive_length);
            if (!hold_rx_ready) {
                R8_SATA_RTX_CTRL |= bSRC_R_READY;
            }
        } else {
            R16_SATA_INT_FG = bSIF_RECV_OK;
            R8_SATA_RTX_CTRL |= bSRC_R_READY;
            if (batch_write_active) {
                USB1BatchSetSataDiagnostics(flags, receive_length);
                batch_write_active = 0;
                batch_chunk_waiting = 0;
                batch_rx_restore();
                USB1BatchFinish(MAILBOX_ERROR_SATA_RX_CRC);
                MailboxControllerBatchComplete();
            } else {
                MailboxAbort(MAILBOX_ERROR_SATA_RX_CRC);
            }
            if (!rx_error_logged) {
                USB1Log("ERR SATA RX CRC\r\n");
                rx_error_logged = 1;
            }
        }
    }

    if (flags & (bSIF_FIFO_OV | bSIF_COLLIDE | bSIF_TRAN_INT)) {
        if ((flags & bSIF_FIFO_OV) && batch_write_active) {
            USB1BatchSetSataDiagnostics(flags, R16_SATA_RX_LEN);
            if (!fifo_over_logged) {
                USB1Log("LOG SATA FIFO_OV deferred until RECV_OK\r\n");
                fifo_over_logged = 1;
            }


        }
        if ((flags & bSIF_FIFO_OV) && bulk_write_active) {
            bulk_write_active = 0;
            MailboxAbort(MAILBOX_ERROR_SATA_RX_CRC);
        }
        R16_SATA_INT_FG = flags & (bSIF_FIFO_OV | bSIF_COLLIDE | bSIF_TRAN_INT);
    }
}

void SATADeviceBatchChunkConsumed(void)
{
    volatile UINT8 *next_buffer;

    if (!batch_write_active || !batch_chunk_waiting) {
        return;
    }
    batch_chunk_waiting = 0;
    hold_rx_ready = 0;
    if (batch_received_size == batch_expected_size) {
        batch_write_active = 0;
        batch_rx_restore();


        R8_SATA_RTX_CTRL |= bSRC_R_READY;
        if (!send_status(ATA_SR_DRDY | ATA_SR_DSC, 0)) {
            USB1BatchFinish(MAILBOX_ERROR_SATA_TX);
        } else {
            USB1BatchFinish(MAILBOX_ERROR_NONE);
        }
        MailboxControllerBatchComplete();
        command_delivered_logged = 0;
        return;
    }


    next_buffer = (batch_rx_current == (volatile UINT8 *)sata_rx)
                    ? (volatile UINT8 *)sata_tx : (volatile UINT8 *)sata_rx;
    batch_rx_current = next_buffer;
    R16_SATA_DMA0 = (UINT16)(UINT32)next_buffer;
    R8_SATA_RTX_CTRL |= bSRC_R_READY;
    if (!send_dma_activate()) {
        batch_write_active = 0;
        batch_rx_restore();
        USB1BatchFinish(MAILBOX_ERROR_SATA_TX);
        MailboxControllerBatchComplete();
        send_status(ATA_SR_DRDY | ATA_SR_ERR, ATA_ER_ABRT);
    }
}
