#include <string.h>

#include "CH568SFR.h"
#include "mailbox.h"
#include "sata_device.h"
#include "usb_mailbox.h"

#define EP0_SIZE 64
#define LOG_QUEUE_DEPTH 16
#define LOG_MESSAGE_SIZE 160
#define BULK_READ_HEADER_SIZE 32
#define USB_BULK_PACKET_SIZE 512
#define BATCH_REQUEST_HEADER_SIZE 16
#define BATCH_RESPONSE_HEADER_SIZE 32
#define BATCH_RESPONSE_TRAILER_SIZE 24
#define BATCH_READY_SIZE 20
#define BULK_READY_SIZE 12
#define LINEAR_REQUEST_SIZE 24
#define SETMAP_HEADER_SIZE 12
#define SETMAP_MAX_RANGES 8

static const UINT8 device_descriptor[] = {
    0x12, 0x01, 0x00, 0x02, 0xFF, 0x00, 0x00, EP0_SIZE,
    0x48, 0x43, 0x37, 0x56, 0x00, 0x01, 0x01, 0x02,
    0x00, 0x01
};

static const UINT8 config_descriptor[] = {
    0x09, 0x02, 0x20, 0x00, 0x01, 0x01, 0x00, 0x80, 0x32,
    0x09, 0x04, 0x00, 0x00, 0x02, 0xFF, 0x00, 0x00, 0x00,
    0x07, 0x05, 0x81, 0x02, 0x00, 0x02, 0x00,
    0x07, 0x05, 0x01, 0x02, 0x00, 0x02, 0x00
};

static const UINT8 language_descriptor[] = {0x04, 0x03, 0x09, 0x04};
static const UINT8 manufacturer_descriptor[] = {
    0x10, 0x03, 'O', 0, 'p', 0, 'e', 0, 'n', 0, 'A', 0, 'I', 0, ' ', 0
};
static const UINT8 product_descriptor[] = {
    0x26, 0x03,
    'C',0,'H',0,'5',0,'6',0,'8',0,' ',0,'S',0,'A',0,'T',0,'A',0,
    ' ',0,'M',0,'a',0,'i',0,'l',0,'b',0,'o',0,'x',0
};

__attribute__((aligned(4))) static UINT8 ep0_buffer[EP0_SIZE];
__attribute__((aligned(4))) static UINT8 ep1_buffer[1024];
__attribute__((aligned(4))) static UINT8 bulk_read_header[BULK_READ_HEADER_SIZE];
__attribute__((aligned(4))) static UINT8 batch_response_header[BATCH_RESPONSE_HEADER_SIZE];
__attribute__((aligned(4))) static UINT8 batch_response_trailer[BATCH_RESPONSE_TRAILER_SIZE];
__attribute__((aligned(4))) static UINT8 batch_ready_frame[BATCH_READY_SIZE];
__attribute__((aligned(4))) static UINT8 bulk_ready_frame[BULK_READY_SIZE];
static UINT32 crc32_table[256];
static UINT32 batch_request_low[MAILBOX_BATCH_MAX_PAGES];
static UINT32 batch_request_high[MAILBOX_BATCH_MAX_PAGES];


static UINT32 setmap_ranges[SETMAP_MAX_RANGES * 4];
static volatile UINT8 batch_request_crc_enabled;
static volatile UINT8 batch_stream_crc_enabled;


static volatile UINT8 ep1_dma_repointed;

#define setup_packet ((PUSB_SETUP_REQ)ep0_buffer)
#define ep1_out      ((PUINT8)&ep1_buffer[0])
#define ep1_in       ((PUINT8)&ep1_buffer[512])

static UINT16 setup_remaining;
static UINT8 setup_request;
static UINT8 configuration;
static UINT8 interface_alt;
static UINT8 pending_address;
static PUINT8 descriptor_cursor;
static char log_queue[LOG_QUEUE_DEPTH][LOG_MESSAGE_SIZE];
static volatile UINT8 log_head;
static volatile UINT8 log_tail;
static volatile UINT8 log_count;
static volatile UINT8 ep1_tx_busy;
static volatile UINT8 command_queued_event;
static volatile UINT8 command_busy_event;
static volatile UINT8 command_error_event;
static volatile UINT8 read_queued_event;
static volatile UINT8 read_queued_is_4k;
static volatile UINT8 batch_queued_event;
static volatile UINT8 linear_queued_event;
static volatile UINT8 setmap_queued_event;
static volatile UINT8 bulk_read_tx_active;
static volatile UINT8 bulk_read_tx_final_packet;
static volatile UINT8 bulk_read_release_pending;
static volatile UINT8 bulk_read_owns_mailbox_result;
static volatile UINT8 bulk_ready_pending;
static UINT16 bulk_read_tx_offset;
static UINT16 bulk_read_tx_length;
static const UINT8 *bulk_read_payload;
static UINT16 bulk_read_payload_length;
static UINT32 bulk_read_sequence;
static UINT8 bulk_read_status;
static volatile UINT8 batch_tx_active;
static volatile UINT8 batch_chunk_release_pending;
static volatile UINT8 batch_stream_release_pending;
static volatile UINT8 batch_packet_finishes_chunk;
static volatile UINT8 batch_packet_finishes_stream;
static volatile UINT8 batch_ready_pending;
static UINT8 batch_page_count;
static UINT8 batch_finish_status;
static UINT16 batch_header_offset;
static UINT16 batch_trailer_offset;
static const UINT8 *batch_chunk_data;
static UINT16 batch_chunk_length;
static UINT16 batch_chunk_offset;
static UINT32 batch_sequence;
static UINT32 batch_expected_length;
static UINT32 batch_received_length;
static UINT32 batch_crc_state;
static UINT16 batch_last_sata_flags;
static UINT16 batch_last_receive_length;

static char hex_digit(UINT8 value)
{
    value &= 0x0F;
    return (char)(value < 10 ? ('0' + value) : ('A' + value - 10));
}

static char *append_hex32(char *cursor, UINT32 value)
{
    INT8 shift;

    for (shift = 28; shift >= 0; shift -= 4) {
        *cursor++ = hex_digit((UINT8)(value >> shift));
    }
    return cursor;
}

static void store_le16(UINT8 *destination, UINT16 value)
{
    destination[0] = (UINT8)value;
    destination[1] = (UINT8)(value >> 8);
}

static void store_le32(UINT8 *destination, UINT32 value)
{
    destination[0] = (UINT8)value;
    destination[1] = (UINT8)(value >> 8);
    destination[2] = (UINT8)(value >> 16);
    destination[3] = (UINT8)(value >> 24);
}

static UINT16 load_le16(const UINT8 *source)
{
    return (UINT16)source[0] | ((UINT16)source[1] << 8);
}

static UINT32 load_le32(const UINT8 *source)
{
    return (UINT32)source[0] |
           ((UINT32)source[1] << 8) |
           ((UINT32)source[2] << 16) |
           ((UINT32)source[3] << 24);
}

static void crc32_init_table(void)
{
    UINT16 i;
    UINT8 bit;
    UINT32 value;

    for (i = 0; i < 256; ++i) {
        value = i;
        for (bit = 0; bit < 8; ++bit) {
            value = (value >> 1) ^
                    (0xEDB88320UL & (UINT32)(0 - (value & 1)));
        }
        crc32_table[i] = value;
    }
}

static UINT32 crc32_update(UINT32 crc, const UINT8 *data, UINT16 length)
{
    while (length--) {
        crc = (crc >> 8) ^ crc32_table[(UINT8)(crc ^ *data++)];
    }
    return crc;
}

static UINT32 crc32_ieee(const UINT8 *data, UINT16 length)
{
    UINT32 crc;
    crc = 0xFFFFFFFFUL;
    crc = crc32_update(crc, data, length);
    return ~crc;
}

static void prepare_bulk_header(UINT8 status, UINT32 sequence,
                                UINT32 address_low, UINT32 address_high,
                                UINT16 payload_length, UINT32 payload_crc)
{
    memset(bulk_read_header, 0, sizeof(bulk_read_header));
    bulk_read_header[0] = 'C';
    bulk_read_header[1] = 'H';
    bulk_read_header[2] = '5';
    bulk_read_header[3] = 'K';
    store_le16(bulk_read_header + 4, BULK_READ_HEADER_SIZE);
    bulk_read_header[6] = 3;
    bulk_read_header[7] = status;
    store_le32(bulk_read_header + 8, sequence);
    store_le32(bulk_read_header + 12, address_low);
    store_le32(bulk_read_header + 16, address_high);
    store_le32(bulk_read_header + 20, payload_length);
    store_le32(bulk_read_header + 24, payload_crc);
}

static void start_bulk_response(UINT8 status, UINT32 sequence,
                                UINT32 address_low, UINT32 address_high,
                                const UINT8 *payload, UINT16 payload_length,
                                UINT8 owns_mailbox_result)
{
    UINT32 crc;

    crc = payload_length ? crc32_ieee(payload, payload_length) : 0;
    prepare_bulk_header(status, sequence, address_low, address_high,
                        payload_length, crc);
    bulk_read_payload = payload;
    bulk_read_payload_length = payload_length;
    bulk_read_tx_length = (UINT16)(BULK_READ_HEADER_SIZE + payload_length);
    bulk_read_tx_offset = 0;
    bulk_read_tx_final_packet = 0;
    bulk_read_release_pending = 0;
    bulk_read_owns_mailbox_result = owns_mailbox_result;
    bulk_ready_pending = 0;
    bulk_read_sequence = sequence;
    bulk_read_status = status;
    bulk_read_tx_active = 1;
}

static void usb1_ep1_dma_default(void)
{
    if (ep1_dma_repointed) {
        ep1_dma_repointed = 0;
        R16_UEP1_DMA1 = (UINT16)(UINT32)ep1_buffer;
        R8_UEP1_RX_CTRL1 = (R8_UEP1_RX_CTRL1 & (UINT8)~MASK_UEP_R_RES) |
                            UEP_R_RES_ACK | bUEP_AUTO_TOG;
    }
}

void USB1BatchStart(UINT32 sequence, UINT8 page_count,
                    UINT32 expected_length)
{
    memset(batch_response_header, 0, sizeof(batch_response_header));
    batch_response_header[0] = 'C';
    batch_response_header[1] = 'H';
    batch_response_header[2] = 'B';
    batch_response_header[3] = '1';
    store_le16(batch_response_header + 4, BATCH_RESPONSE_HEADER_SIZE);
    batch_response_header[6] = 1;
    batch_response_header[7] = 0;
    store_le32(batch_response_header + 8, sequence);
    store_le16(batch_response_header + 12, page_count);
    store_le32(batch_response_header + 16, expected_length);
    store_le32(batch_response_header + 20, BATCH_RESPONSE_TRAILER_SIZE);
    store_le32(batch_response_header + 24, 1);

    batch_sequence = sequence;
    batch_page_count = page_count;
    batch_expected_length = expected_length;
    batch_received_length = 0;
    batch_stream_crc_enabled = batch_request_crc_enabled;
    batch_crc_state = 0xFFFFFFFFUL;
    batch_last_sata_flags = 0;
    batch_last_receive_length = 0;
    batch_finish_status = 0xFF;
    batch_header_offset = 0;
    batch_trailer_offset = 0;
    batch_chunk_data = 0;
    batch_chunk_length = 0;
    batch_chunk_offset = 0;
    batch_chunk_release_pending = 0;
    batch_stream_release_pending = 0;
    batch_packet_finishes_chunk = 0;
    batch_packet_finishes_stream = 0;
    batch_ready_pending = 0;
    batch_tx_active = 1;
}

UINT8 USB1BatchAcceptSataChunk(const UINT8 *data, UINT16 length)
{
    if (!batch_tx_active || batch_chunk_data || length == 0 ||
        batch_received_length + length > batch_expected_length) {
        return 0;
    }
    if (batch_stream_crc_enabled) {
        batch_crc_state = crc32_update(batch_crc_state, data, length);
    }
    batch_received_length += length;
    batch_chunk_data = data;
    batch_chunk_length = length;
    batch_chunk_offset = 0;
    return 1;
}

void USB1BatchFinish(UINT8 status)
{
    if (!batch_tx_active) {
        return;
    }
    batch_finish_status = status;
    memset(batch_response_trailer, 0, sizeof(batch_response_trailer));
    batch_response_trailer[0] = 'C';
    batch_response_trailer[1] = 'E';
    batch_response_trailer[2] = 'N';
    batch_response_trailer[3] = 'D';
    store_le32(batch_response_trailer + 4, batch_sequence);
    store_le32(batch_response_trailer + 8, batch_received_length);
    store_le32(batch_response_trailer + 12,
               batch_stream_crc_enabled ? ~batch_crc_state : 0);
    store_le32(batch_response_trailer + 16, status);
    store_le32(batch_response_trailer + 20,
               (UINT32)batch_page_count);
    batch_trailer_offset = 0;
}

UINT8 USB1BatchActive(void)
{
    return batch_tx_active;
}

void USB1BatchSetSataDiagnostics(UINT16 flags, UINT16 receive_length)
{


    batch_last_sata_flags |= flags;
    batch_last_receive_length = receive_length;
}

static void publish_controller_address(UINT32 address_low, UINT32 address_high)
{
    char message[20];
    char *cursor;

    cursor = append_hex32(message, address_high);
    *cursor++ = ' ';
    cursor = append_hex32(cursor, address_low);
    *cursor++ = '\r';
    *cursor++ = '\n';
    *cursor = 0;
    USB1Log(message);
}

void USB1Log(const char *text)
{
    UINT8 length;
    UINT8 index;

    length = (UINT8)strlen(text);
    if (length >= LOG_MESSAGE_SIZE) {
        length = LOG_MESSAGE_SIZE - 1;
    }

    if (log_count == LOG_QUEUE_DEPTH) {
        log_head = (UINT8)((log_head + 1) % LOG_QUEUE_DEPTH);
        log_count--;
    }
    index = log_tail;
    memcpy(log_queue[index], text, length);
    log_queue[index][length] = 0;
    log_tail = (UINT8)((log_tail + 1) % LOG_QUEUE_DEPTH);
    log_count++;
}

static void publish_next_log(void)
{
    UINT16 length;

    if (ep1_tx_busy || !log_count || !configuration) {
        return;
    }

    length = (UINT16)strlen(log_queue[log_head]);
    memcpy(ep1_in, log_queue[log_head], length);
    log_head = (UINT8)((log_head + 1) % LOG_QUEUE_DEPTH);
    log_count--;
    ep1_tx_busy = 1;
    R16_UEP1_T_LEN1 = length;
    R8_UEP1_TX_CTRL1 = (R8_UEP1_TX_CTRL1 & (UINT8)~MASK_UEP_T_RES) |
                        UEP_T_RES_ACK | bUEP_AUTO_TOG;
}

static void publish_next_bulk_read_packet(void)
{
    UINT16 remaining;
    UINT16 length;
    UINT16 copied;
    UINT16 header_remaining;
    UINT16 payload_offset;

    if (!bulk_read_tx_active || ep1_tx_busy || !configuration) {
        return;
    }
    remaining = (UINT16)(bulk_read_tx_length - bulk_read_tx_offset);
    length = remaining < USB_BULK_PACKET_SIZE ? remaining : USB_BULK_PACKET_SIZE;
    copied = 0;
    if (bulk_read_tx_offset < BULK_READ_HEADER_SIZE) {
        header_remaining = (UINT16)(BULK_READ_HEADER_SIZE -
                                     bulk_read_tx_offset);
        if (header_remaining > length) {
            header_remaining = length;
        }
        memcpy(ep1_in, bulk_read_header + bulk_read_tx_offset,
               header_remaining);
        copied = header_remaining;
    }
    if (copied < length) {
        payload_offset = (UINT16)(bulk_read_tx_offset + copied -
                                  BULK_READ_HEADER_SIZE);
        if (payload_offset < bulk_read_payload_length) {
            memcpy(ep1_in + copied, bulk_read_payload + payload_offset,
                   (UINT16)(length - copied));
        }
    }
    bulk_read_tx_offset = (UINT16)(bulk_read_tx_offset + length);
    if (bulk_read_tx_offset == bulk_read_tx_length) {
        bulk_read_tx_active = 0;
        bulk_read_tx_final_packet = 1;
    }
    ep1_tx_busy = 1;
    R16_UEP1_T_LEN1 = length;
    R8_UEP1_TX_CTRL1 = (R8_UEP1_TX_CTRL1 & (UINT8)~MASK_UEP_T_RES) |
                        UEP_T_RES_ACK | bUEP_AUTO_TOG;
}

static void publish_bulk_ready(void)
{
    if (!bulk_ready_pending || ep1_tx_busy || !configuration) {
        return;
    }
    memcpy(ep1_in, bulk_ready_frame, BULK_READY_SIZE);
    bulk_ready_pending = 0;
    ep1_tx_busy = 1;
    R16_UEP1_T_LEN1 = BULK_READY_SIZE;
    R8_UEP1_TX_CTRL1 = (R8_UEP1_TX_CTRL1 & (UINT8)~MASK_UEP_T_RES) |
                        UEP_T_RES_ACK | bUEP_AUTO_TOG;
}

static void publish_next_batch_packet(void)
{
    const UINT8 *source;
    UINT16 remaining;
    UINT16 length;

    if ((!batch_tx_active && !batch_ready_pending) || ep1_tx_busy ||
        !configuration) {
        return;
    }
    source = 0;
    remaining = 0;
    if (batch_ready_pending) {
        usb1_ep1_dma_default();
        source = batch_ready_frame;
        length = BATCH_READY_SIZE;
        memcpy(ep1_in, source, length);
        batch_ready_pending = 0;
    } else if (batch_header_offset < BATCH_RESPONSE_HEADER_SIZE) {
        usb1_ep1_dma_default();
        source = batch_response_header + batch_header_offset;
        remaining = (UINT16)(BATCH_RESPONSE_HEADER_SIZE -
                             batch_header_offset);
        length = remaining < USB_BULK_PACKET_SIZE ? remaining :
                 USB_BULK_PACKET_SIZE;
        memcpy(ep1_in, source, length);
        batch_header_offset = (UINT16)(batch_header_offset + length);
    } else if (batch_chunk_data &&
               batch_chunk_offset < batch_chunk_length) {


        remaining = (UINT16)(batch_chunk_length - batch_chunk_offset);
        length = remaining < USB_BULK_PACKET_SIZE ? remaining :
                 USB_BULK_PACKET_SIZE;
        R8_UEP1_RX_CTRL1 = (R8_UEP1_RX_CTRL1 & (UINT8)~MASK_UEP_R_RES) |
                            UEP_R_RES_NAK | bUEP_AUTO_TOG;
        R16_UEP1_DMA1 = (UINT16)(UINT32)(batch_chunk_data +
                                          batch_chunk_offset - 512);
        ep1_dma_repointed = 1;
        batch_chunk_offset = (UINT16)(batch_chunk_offset + length);
        if (batch_chunk_offset == batch_chunk_length) {
            batch_packet_finishes_chunk = 1;
        }
    } else if (batch_finish_status != 0xFF &&
               batch_trailer_offset < BATCH_RESPONSE_TRAILER_SIZE) {
        usb1_ep1_dma_default();
        source = batch_response_trailer + batch_trailer_offset;
        remaining = (UINT16)(BATCH_RESPONSE_TRAILER_SIZE -
                             batch_trailer_offset);
        length = remaining < USB_BULK_PACKET_SIZE ? remaining :
                 USB_BULK_PACKET_SIZE;
        memcpy(ep1_in, source, length);
        batch_trailer_offset = (UINT16)(batch_trailer_offset + length);
        if (batch_trailer_offset == BATCH_RESPONSE_TRAILER_SIZE) {
            batch_packet_finishes_stream = 1;
        }
    } else {
        return;
    }
    ep1_tx_busy = 1;
    R16_UEP1_T_LEN1 = length;
    R8_UEP1_TX_CTRL1 = (R8_UEP1_TX_CTRL1 & (UINT8)~MASK_UEP_T_RES) |
                        UEP_T_RES_ACK | bUEP_AUTO_TOG;
}


static UINT8 is_command_vers(const UINT8 *data, UINT16 length)
{
    return length >= 4 && data[0] == 'V' && data[1] == 'E' &&
           data[2] == 'R' && data[3] == 'S';
}

static UINT8 is_command_1337(const UINT8 *data, UINT16 length)
{
    if (length >= 4 && data[0] == '1' && data[1] == '3' &&
        data[2] == '3' && data[3] == '7') {
        return 1;
    }
    if (length >= 2 && data[0] == 0x37 && data[1] == 0x13) {
        return 1;
    }
    if (length >= 4 && data[0] == 0x37 && data[1] == 0x13 &&
        data[2] == 0 && data[3] == 0) {
        return 1;
    }
    return 0;
}

static int hex_value(UINT8 value)
{
    if (value >= '0' && value <= '9') return (int)(value - '0');
    if (value >= 'A' && value <= 'F') return (int)(value - 'A' + 10);
    if (value >= 'a' && value <= 'f') return (int)(value - 'a' + 10);
    return -1;
}

static UINT8 parse_read_request(const UINT8 *data, UINT16 length,
                                UINT32 *address_high, UINT32 *address_low,
                                UINT16 *read_size)
{
    UINT32 high = 0;
    UINT32 low = 0;
    UINT8 i;
    UINT8 base = 0;
    int digit;

    while (length && (data[length - 1] == '\r' || data[length - 1] == '\n')) {
        --length;
    }
    if (length == 21 && memcmp(data, "R4K ", 4) == 0 && data[12] == ' ') {
        base = 4;
        *read_size = MAILBOX_READ4K_SIZE;
    } else if (length == 17 && data[8] == ' ') {
        *read_size = MAILBOX_READ64_SIZE;
    } else {
        return 0;
    }
    for (i = 0; i < 8; ++i) {
        digit = hex_value(data[base + i]);
        if (digit < 0) return 0;
        high = (high << 4) | (UINT32)digit;
        digit = hex_value(data[base + i + 9]);
        if (digit < 0) return 0;
        low = (low << 4) | (UINT32)digit;
    }
    *address_high = high;
    *address_low = low;
    return 1;
}

static UINT8 parse_batch_request(const UINT8 *data, UINT16 length,
                                 UINT8 *page_count)
{
    UINT8 count;
    UINT8 i;
    UINT16 expected;

    if (length < BATCH_REQUEST_HEADER_SIZE ||
        data[0] != 'C' || data[1] != 'H' ||
        data[2] != 'B' || data[3] != 'Q' ||
        data[4] != 1 ||
        load_le16(data + 6) != BATCH_REQUEST_HEADER_SIZE) {
        return 0;
    }
    count = data[5];
    if (count == 0 || count > MAILBOX_BATCH_MAX_PAGES) {
        return 0;
    }
    expected = (UINT16)(BATCH_REQUEST_HEADER_SIZE + (UINT16)count * 8);
    if (length != expected) {
        return 0;
    }

    batch_request_crc_enabled = (UINT8)((data[8] & 1) == 0);
    for (i = 0; i < count; ++i) {
        batch_request_low[i] = load_le32(data + BATCH_REQUEST_HEADER_SIZE +
                                        (UINT16)i * 8);
        batch_request_high[i] = load_le32(data + BATCH_REQUEST_HEADER_SIZE +
                                         (UINT16)i * 8 + 4);
    }
    *page_count = count;
    return 1;
}


static UINT8 parse_linear_request(const UINT8 *data, UINT16 length,
                                  UINT8 *page_count, UINT8 *flags,
                                  UINT32 *address_high, UINT32 *address_low)
{
    UINT8 count;

    if (length != LINEAR_REQUEST_SIZE ||
        data[0] != 'C' || data[1] != 'H' ||
        data[2] != 'L' || data[3] != 'Q' ||
        data[4] != 1 ||
        load_le16(data + 6) != LINEAR_REQUEST_SIZE) {
        return 0;
    }
    count = data[5];
    if (count == 0 || count > MAILBOX_LINEAR_MAX_PAGES) {
        return 0;
    }
    batch_request_crc_enabled = (UINT8)((data[8] & 1) == 0);
    *page_count = count;
    *flags = data[8];
    *address_high = load_le32(data + 12);
    *address_low = load_le32(data + 16);
    return 1;
}


static UINT8 parse_setmap_request(const UINT8 *data, UINT16 length,
                                  UINT8 *range_count)
{
    UINT8 count;
    UINT16 i;
    if (length < SETMAP_HEADER_SIZE ||
        data[0] != 'C' || data[1] != 'H' ||
        data[2] != 'S' || data[3] != 'M' ||
        data[4] != 1 ||
        load_le16(data + 6) != SETMAP_HEADER_SIZE) {
        return 0;
    }
    count = data[5];
    if (count == 0 || count > SETMAP_MAX_RANGES ||
        length != SETMAP_HEADER_SIZE + (UINT16)count * 16) {
        return 0;
    }
    for (i = 0; i < count * 16u; ++i) {
        ((UINT8 *)setmap_ranges)[i] = data[SETMAP_HEADER_SIZE + i];
    }
    *range_count = count;
    return 1;
}

static void ep0_stall(void)
{
    setup_request = 0xFF;
    R8_UEP0_RX_CTRL1 = UEP_DATA1 | UEP_R_RES_STALL;
    R8_UEP0_TX_CTRL1 = UEP_DATA1 | UEP_T_RES_STALL;
}

static void ep0_setup(void)
{
    UINT16 length;
    UINT8 status;
    UINT8 reply[2];

    if (R16_USB1_RX_LEN != sizeof(USB_SETUP_REQ)) {
        ep0_stall();
        return;
    }

    setup_remaining = ((UINT16)setup_packet->wLengthH << 8) | setup_packet->wLengthL;
    setup_request = setup_packet->bRequest;
    length = 0;
    status = 0;

    if ((setup_packet->bRequestType & USB_REQ_TYP_MASK) != USB_REQ_TYP_STANDARD) {
        status = 0xFF;
    } else {
        switch (setup_request) {
        case USB_GET_DESCRIPTOR:
            switch (setup_packet->wValueH) {
            case 1:
                descriptor_cursor = (PUINT8)device_descriptor;
                length = sizeof(device_descriptor);
                break;
            case 2:
                descriptor_cursor = (PUINT8)config_descriptor;
                length = sizeof(config_descriptor);
                break;
            case 3:
                if (setup_packet->wValueL == 0) {
                    descriptor_cursor = (PUINT8)language_descriptor;
                    length = sizeof(language_descriptor);
                } else if (setup_packet->wValueL == 1) {
                    descriptor_cursor = (PUINT8)manufacturer_descriptor;
                    length = sizeof(manufacturer_descriptor);
                } else if (setup_packet->wValueL == 2) {
                    descriptor_cursor = (PUINT8)product_descriptor;
                    length = sizeof(product_descriptor);
                } else {
                    status = 0xFF;
                }
                break;
            default:
                status = 0xFF;
                break;
            }
            break;
        case USB_SET_ADDRESS:
            pending_address = setup_packet->wValueL;
            break;
        case USB_GET_CONFIGURATION:
            reply[0] = configuration;
            descriptor_cursor = reply;
            length = 1;
            break;
        case USB_SET_CONFIGURATION:
            configuration = setup_packet->wValueL;
            break;
        case USB_GET_INTERFACE:
            reply[0] = interface_alt;
            descriptor_cursor = reply;
            length = 1;
            break;
        case USB_SET_INTERFACE:
            interface_alt = setup_packet->wValueL;
            break;
        case USB_GET_STATUS:
            reply[0] = 0;
            reply[1] = 0;
            descriptor_cursor = reply;
            length = 2;
            break;
        case USB_CLEAR_FEATURE:
            if ((setup_packet->bRequestType & USB_REQ_RECIP_MASK) == USB_REQ_RECIP_ENDP) {
                if (setup_packet->wIndexL == 0x81) {
                    R8_UEP1_TX_CTRL1 = UEP_T_RES_NAK | bUEP_AUTO_TOG;
                    ep1_tx_busy = 0;
                } else if (setup_packet->wIndexL == 0x01) {
                    R8_UEP1_RX_CTRL1 = UEP_R_RES_ACK | bUEP_AUTO_TOG;
                } else {
                    status = 0xFF;
                }
            }
            break;
        default:
            status = 0xFF;
            break;
        }
    }

    if (status == 0xFF) {
        ep0_stall();
        return;
    }

    setup_remaining = setup_remaining < length ? setup_remaining : length;
    if (setup_remaining && (setup_packet->bRequestType & 0x80)) {
        length = setup_remaining < EP0_SIZE ? setup_remaining : EP0_SIZE;
        memcpy(ep0_buffer, descriptor_cursor, length);
        descriptor_cursor += length;
        setup_remaining -= length;
        R16_UEP0_T_LEN1 = length;
        R8_UEP0_TX_CTRL1 = UEP_DATA1 | UEP_T_RES_ACK;
    } else {
        R16_UEP0_T_LEN1 = 0;
        R8_UEP0_TX_CTRL1 = UEP_DATA1 | UEP_T_RES_ACK;
    }
}

static void ep0_in(void)
{
    UINT16 length;

    if (setup_request == USB_GET_DESCRIPTOR && setup_remaining) {
        length = setup_remaining < EP0_SIZE ? setup_remaining : EP0_SIZE;
        memcpy(ep0_buffer, descriptor_cursor, length);
        descriptor_cursor += length;
        setup_remaining -= length;
        R16_UEP0_T_LEN1 = length;
        R8_UEP0_TX_CTRL1 ^= UEP_DATA1;
    } else {
        R16_UEP0_T_LEN1 = 0;
        R8_UEP0_TX_CTRL1 = UEP_DATA0 | UEP_T_RES_NAK;
        R8_UEP0_RX_CTRL1 = UEP_DATA0 | UEP_R_RES_ACK;
        if (setup_request == USB_SET_ADDRESS) {
            R8_USB1_DEV_AD = pending_address;
        }
    }
}

void USB1DeviceInit(void)
{
    configuration = 0;
    interface_alt = 0;
    pending_address = 0;
    log_head = 0;
    log_tail = 0;
    log_count = 0;
    ep1_tx_busy = 0;
    command_queued_event = 0;
    command_busy_event = 0;
    command_error_event = 0;
    read_queued_event = 0;
    read_queued_is_4k = 0;
    batch_queued_event = 0;
    linear_queued_event = 0;
    setmap_queued_event = 0;
    batch_request_crc_enabled = 1;
    ep1_dma_repointed = 0;
    bulk_read_tx_active = 0;
    bulk_read_tx_final_packet = 0;
    bulk_read_release_pending = 0;
    bulk_read_owns_mailbox_result = 0;
    bulk_ready_pending = 0;
    bulk_read_tx_offset = 0;
    bulk_read_tx_length = 0;
    bulk_read_payload = 0;
    bulk_read_payload_length = 0;
    bulk_read_sequence = 0;
    bulk_read_status = 0;
    batch_tx_active = 0;
    batch_chunk_release_pending = 0;
    batch_stream_release_pending = 0;
    batch_packet_finishes_chunk = 0;
    batch_packet_finishes_stream = 0;
    batch_ready_pending = 0;
    batch_page_count = 0;
    batch_finish_status = 0xFF;
    batch_header_offset = 0;
    batch_trailer_offset = 0;
    batch_chunk_data = 0;
    batch_chunk_length = 0;
    batch_chunk_offset = 0;
    batch_sequence = 0;
    batch_expected_length = 0;
    batch_received_length = 0;
    batch_crc_state = 0xFFFFFFFFUL;
    batch_last_sata_flags = 0;
    batch_last_receive_length = 0;
    crc32_init_table();

    R8_USB1_CTRL = bUC_CLR_ALL;
    R8_USB1_CTRL = UCST_HS | bUC_INT_BUSY | bUC_DMA_EN;
    R8_USB1_SUSPEND = 0;
    R8_USB1_DEV_AD = 0;
    R8_USB1_INT_FG = 0xFF;
    R8_USB1_INT_EN = bUIE_FIFO_OV | bUIE_SUSPEND | bUIE_TRANSFER | bUIE_BUS_RST;

    R8_UEP4_1_MOD1 = bUEP1_TX_EN | bUEP1_RX_EN;
    R8_UEP2_3_MOD1 = 0;

    R8_UEP0_TX_CTRL1 = UEP_T_RES_NAK;
    R8_UEP0_RX_CTRL1 = UEP_R_RES_ACK;
    R16_UEP0_MAX_LEN1 = EP0_SIZE;
    R16_UEP0_DMA1 = (UINT32)ep0_buffer;

    R8_UEP1_TX_CTRL1 = UEP_T_RES_NAK | bUEP_AUTO_TOG;
    R8_UEP1_RX_CTRL1 = UEP_R_RES_ACK | bUEP_AUTO_TOG;
    R16_UEP1_MAX_LEN1 = 512;
    R16_UEP1_DMA1 = (UINT32)ep1_buffer;

    R8_USB1_CTRL |= bUC_DEV_PU_EN;
}

void USB1MailboxService(void)
{
    UINT32 sequence;
    UINT32 address_low;
    UINT32 address_high;
    const UINT8 *read_data;
    UINT16 read_size;
    UINT8 error_code;
    char message[LOG_MESSAGE_SIZE];
    char *cursor;
    UINT8 i;

    if (batch_chunk_release_pending) {
        batch_chunk_release_pending = 0;
        batch_chunk_data = 0;
        batch_chunk_length = 0;
        batch_chunk_offset = 0;
        SATADeviceBatchChunkConsumed();
    }
    if (batch_stream_release_pending) {
        UINT8 completed_status;

        batch_stream_release_pending = 0;
        completed_status = batch_finish_status;
        batch_tx_active = 0;
        batch_chunk_data = 0;
        batch_chunk_length = 0;
        MailboxReleaseBatchResult();
        memset(batch_ready_frame, 0, sizeof(batch_ready_frame));
        batch_ready_frame[0] = 'C';
        batch_ready_frame[1] = 'H';
        batch_ready_frame[2] = 'B';
        batch_ready_frame[3] = 'R';
        store_le32(batch_ready_frame + 4, batch_sequence);
        store_le32(batch_ready_frame + 8, completed_status);
        store_le32(batch_ready_frame + 12, batch_last_sata_flags);
        store_le32(batch_ready_frame + 16, batch_last_receive_length);
        batch_finish_status = 0xFF;
        batch_ready_pending = 1;
    }

    if (bulk_read_release_pending) {
        bulk_read_release_pending = 0;
        if (bulk_read_owns_mailbox_result) {
            MailboxReleaseReadResult();
        }
        bulk_read_owns_mailbox_result = 0;
        bulk_read_payload = 0;
        bulk_read_payload_length = 0;
        memset(bulk_ready_frame, 0, sizeof(bulk_ready_frame));
        bulk_ready_frame[0] = 'C';
        bulk_ready_frame[1] = 'H';
        bulk_ready_frame[2] = '5';
        bulk_ready_frame[3] = 'R';
        store_le32(bulk_ready_frame + 4, bulk_read_sequence);
        store_le32(bulk_ready_frame + 8, bulk_read_status);
        bulk_ready_pending = 1;
    }

    if (command_queued_event) {
        command_queued_event = 0;
        USB1Log("LOG USB command 1337 queued\r\n");
    }
    if (command_busy_event) {
        command_busy_event = 0;
        USB1Log("ERR USB command already pending\r\n");
    }
    if (command_error_event) {
        command_error_event = 0;
        USB1Log("ERR USB expected 1337 or HIGH32 LOW32\r\n");
    }
    if (read_queued_event) {
        read_queued_event = 0;
        if (read_queued_is_4k) {
            USB1Log("LOG USB 4-KiB memory read queued\r\n");
        } else {
            USB1Log("LOG USB 64-byte memory read queued\r\n");
        }
    }
    if (batch_queued_event) {
        batch_queued_event = 0;
        USB1Log("LOG USB 0x133B batch queued\r\n");
    }
    if (setmap_queued_event) {
        setmap_queued_event = 0;
        USB1Log("LOG USB 0x1342 set-map queued\r\n");
    }
    if (linear_queued_event) {
        linear_queued_event = 0;
    setmap_queued_event = 0;
        USB1Log("LOG USB 0x1341 linear queued\r\n");
    }
    if (MailboxTakeControllerAck(&sequence, &address_low, &address_high)) {
        (void)sequence;
        publish_controller_address(address_low, address_high);
    }
    if (!batch_tx_active && !bulk_read_tx_active &&
        !bulk_read_tx_final_packet &&
        MailboxPeekReadResult(&read_data, &read_size, &sequence,
                              &address_low, &address_high)) {
        if (read_size == MAILBOX_READ4K_SIZE) {
            start_bulk_response(MAILBOX_ERROR_NONE, sequence,
                                address_low, address_high, read_data,
                                read_size, 1);
        } else {
            cursor = message;
            memcpy(cursor, "DATA ", 5);
            cursor += 5;
            for (i = 0; i < read_size; ++i) {
                *cursor++ = hex_digit((UINT8)(read_data[i] >> 4));
                *cursor++ = hex_digit(read_data[i]);
            }
            *cursor++ = '\r';
            *cursor++ = '\n';
            *cursor = 0;
            USB1Log(message);
            MailboxReleaseReadResult();
        }
    }
    if (!batch_tx_active && !bulk_read_tx_active &&
        !bulk_read_tx_final_packet &&
        MailboxTakeError(&sequence, &address_low, &address_high,
                         &error_code)) {
        start_bulk_response(error_code, sequence, address_low, address_high,
                            0, 0, 0);
    }
    if (batch_tx_active || batch_ready_pending) {
        publish_next_batch_packet();
    } else if (bulk_read_tx_active) {
        publish_next_bulk_read_packet();
    } else if (bulk_ready_pending) {
        publish_bulk_ready();
    } else {
        publish_next_log();
    }
}

void USB1DevIntDeal(void)
{
    UINT8 event;
    UINT16 length;
    UINT32 address_high;
    UINT32 address_low;
    UINT16 read_size;
    UINT8 page_count;
    UINT8 linear_flags;

    if (R8_USB1_INT_FG & UIF_TRANSFER) {
        if (!(R8_USB1_INT_ST & bUIS_IS_NAK)) {
            event = R8_USB1_INT_ST & (MASK_UIS_TOKEN | MASK_UIS_ENDP);
            if (event == (UIS_TOKEN_OUT | 1) && (R8_USB1_INT_ST & bUIS_TOG_OK)) {
                length = R16_USB1_RX_LEN;
                if (is_command_vers(ep1_out, length)) {
                    USB1Log("FW CH568-MAILBOX 31G2\r\n");
                } else if (is_command_1337(ep1_out, length)) {
                    if (MailboxBusy()) {
                        command_busy_event = 1;
                    } else {
                        if (MailboxQueue1337()) {
                            command_queued_event = 1;
                        } else {
                            command_busy_event = 1;
                        }
                    }
                } else {
                    if (parse_setmap_request(ep1_out, length, &page_count)) {
                        if (MailboxBusy()) {
                            command_busy_event = 1;
                        } else if (MailboxQueueSetMap(setmap_ranges,
                                                      page_count)) {
                            setmap_queued_event = 1;
                        } else {
                            command_busy_event = 1;
                        }
                    } else                     if (parse_linear_request(ep1_out, length, &page_count,
                                             &linear_flags,
                                             &address_high,
                                             &address_low)) {
                        if (MailboxBusy()) {
                            command_busy_event = 1;
                        } else if (MailboxQueueReadLinear(address_high,
                                                          address_low,
                                                          page_count)) {
                            linear_queued_event = 1;
                        } else {
                            command_busy_event = 1;
                        }
                    } else if (parse_batch_request(ep1_out, length, &page_count)) {
                        if (MailboxBusy()) {
                            command_busy_event = 1;
                        } else if (MailboxQueueReadBatch(batch_request_high,
                                                        batch_request_low,
                                                        page_count)) {
                            batch_queued_event = 1;
                        } else {
                            command_busy_event = 1;
                        }
                    } else if (parse_read_request(ep1_out, length,
                                                  &address_high,
                                                  &address_low, &read_size)) {
                        if (MailboxBusy()) {
                            command_busy_event = 1;
                        } else {
                            if (MailboxQueueRead(address_high, address_low,
                                                 read_size)) {
                                read_queued_event = 1;
                                read_queued_is_4k =
                                    read_size == MAILBOX_READ4K_SIZE;
                            } else {
                                command_busy_event = 1;
                            }
                        }
                    } else {
                        command_error_event = 1;
                    }
                }
            } else if (event == (UIS_TOKEN_IN | 1)) {
                R8_UEP1_TX_CTRL1 = (R8_UEP1_TX_CTRL1 & (UINT8)~MASK_UEP_T_RES) |
                                    UEP_T_RES_NAK | bUEP_AUTO_TOG;
                ep1_tx_busy = 0;
                if (bulk_read_tx_final_packet) {
                    bulk_read_tx_final_packet = 0;
                    bulk_read_release_pending = 1;
                }
                if (batch_packet_finishes_chunk) {
                    batch_packet_finishes_chunk = 0;
                    batch_chunk_release_pending = 1;
                }
                if (batch_packet_finishes_stream) {
                    batch_packet_finishes_stream = 0;
                    batch_stream_release_pending = 1;
                }
            } else if (event == UIS_TOKEN_SETUP) {
                ep0_setup();
            } else if (event == UIS_TOKEN_IN) {
                ep0_in();
            } else if (event == UIS_TOKEN_OUT) {
                R8_UEP0_RX_CTRL1 = UEP_DATA0 | UEP_R_RES_ACK;
            }
        }
        R8_USB1_INT_FG = UIF_TRANSFER;
    } else if (R8_USB1_INT_FG & UIF_BUS_RST) {
        usb1_ep1_dma_default();
        R8_UEP0_TX_CTRL1 = UEP_T_RES_NAK;
        R8_UEP0_RX_CTRL1 = UEP_R_RES_ACK;
        R8_UEP1_TX_CTRL1 = UEP_T_RES_NAK | bUEP_AUTO_TOG;
        R8_UEP1_RX_CTRL1 = UEP_R_RES_ACK | bUEP_AUTO_TOG;
        R8_USB1_DEV_AD = 0;
        pending_address = 0;
        configuration = 0;
        ep1_tx_busy = 0;
        bulk_read_tx_active = 0;
        bulk_read_tx_final_packet = 0;
        bulk_read_release_pending = 0;
        bulk_read_owns_mailbox_result = 0;
        bulk_ready_pending = 0;
        bulk_read_payload = 0;
        bulk_read_payload_length = 0;
        batch_tx_active = 0;
        batch_chunk_release_pending = 0;
        batch_stream_release_pending = 0;
        batch_packet_finishes_chunk = 0;
        batch_packet_finishes_stream = 0;
        batch_ready_pending = 0;
        batch_chunk_data = 0;
        batch_chunk_length = 0;
        batch_finish_status = 0xFF;
        MailboxAbort(MAILBOX_ERROR_USB_RESET);
        MailboxReleaseReadResult();
        MailboxReleaseBatchResult();
        R8_USB1_INT_FG = UIF_BUS_RST;
    } else if (R8_USB1_INT_FG & UIF_SUSPEND) {
        R8_USB1_INT_FG = UIF_SUSPEND;
    } else if (R8_USB1_INT_FG & UIF_FIFO_OV) {
        R8_USB1_INT_FG = UIF_FIFO_OV;
    }
}
