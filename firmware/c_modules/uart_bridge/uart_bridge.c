#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/idf_additions.h"
#include "uart_bridge.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "tusb.h"
#include "esp_log.h"
#include <string.h>

#define UART_NUM            UART_NUM_1
#define UART_TX_PIN         43
#define UART_RX_PIN         44
#define DEFAULT_UART_BAUD   115200
#define UART_BUF_SIZE       (16 * 1024)
#define CDC_INTERFACE       1

#define MAX_PATTERN_LEN     64
#define MAX_REPLY_LEN       32

static const char *TAG = "uart_bridge";

static TaskHandle_t bridge_task_handle = NULL;
static bool bridge_initialized = false;
static bool bridge_running = false;
static uint32_t current_baud = DEFAULT_UART_BAUD;

static volatile bool match_active = false;
static volatile bool match_found = false;
static char match_pattern[MAX_PATTERN_LEN];
static uint32_t match_pattern_len = 0;
static uint32_t match_curr_idx = 0;
static uint8_t kmp_next[MAX_PATTERN_LEN];
static char match_reply[MAX_REPLY_LEN];
static uint32_t match_reply_len = 0;
static SemaphoreHandle_t match_sem = NULL;

static void uart_bridge_task(void *arg);

static void compute_kmp_table(const char *pat, uint32_t len, uint8_t *next) {
    if (len == 0) return;
    next[0] = 0;
    uint32_t j = 0;
    for (uint32_t i = 1; i < len; i++) {
        while (j > 0 && pat[i] != pat[j]) {
            j = next[j - 1];
        }
        if (pat[i] == pat[j]) {
            j++;
        }
        next[i] = (uint8_t)j;
    }
}

bool uart_bridge_set_baud(uint32_t baud_rate) {
    if (baud_rate < 300 || baud_rate > 5000000) {
        ESP_LOGE(TAG, "Invalid baud rate: %lu", (unsigned long)baud_rate);
        return false;
    }
    current_baud = baud_rate;
    if (bridge_initialized) {
        esp_err_t err = uart_set_baudrate(UART_NUM, baud_rate);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to set baud rate: %d", err);
            return false;
        }
    }
    ESP_LOGI(TAG, "Baud rate updated to %lu", (unsigned long)baud_rate);
    return true;
}

uint32_t uart_bridge_get_baud(void) {
    return current_baud;
}

void tud_cdc_line_coding_cb(uint8_t itf, cdc_line_coding_t const *p_line_coding) {
    if (itf == CDC_INTERFACE && p_line_coding != NULL) {
        uint32_t baud = p_line_coding->bit_rate;
        ESP_LOGI(TAG, "USB CDC1 requested baud: %lu, data_bits: %d, stop: %d, parity: %d",
                 (unsigned long)baud, p_line_coding->data_bits, p_line_coding->stop_bits, p_line_coding->parity);
        
        if (baud >= 300 && baud <= 5000000) {
            uart_bridge_set_baud(baud);
        }

        if (bridge_initialized) {
            uart_word_length_t data_bits = UART_DATA_8_BITS;
            switch (p_line_coding->data_bits) {
                case 5: data_bits = UART_DATA_5_BITS; break;
                case 6: data_bits = UART_DATA_6_BITS; break;
                case 7: data_bits = UART_DATA_7_BITS; break;
                case 8: data_bits = UART_DATA_8_BITS; break;
                default: break;
            }
            uart_set_word_length(UART_NUM, data_bits);

            uart_stop_bits_t stop_bits = UART_STOP_BITS_1;
            if (p_line_coding->stop_bits == 2) {
                stop_bits = UART_STOP_BITS_2;
            }
            uart_set_stop_bits(UART_NUM, stop_bits);

            uart_parity_t parity = UART_PARITY_DISABLE;
            if (p_line_coding->parity == 1) {
                parity = UART_PARITY_ODD;
            } else if (p_line_coding->parity == 2) {
                parity = UART_PARITY_EVEN;
            }
            uart_set_parity(UART_NUM, parity);
        }
    }
}

void uart_bridge_init(void) {
    if (bridge_initialized) return;

    uart_config_t uart_cfg = {
        .baud_rate = current_baud,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .rx_flow_ctrl_thresh = 0,
    };
    // 1. Install driver FIRST to enable peripheral clocks and initialize queues
    uart_driver_install(UART_NUM, UART_BUF_SIZE, 0, 0, NULL, 0);
    // 2. Configure UART baud and frame settings on the active peripheral
    uart_param_config(UART_NUM, &uart_cfg);
    // 3. Connect pins via GPIO matrix
    uart_set_pin(UART_NUM, UART_TX_PIN, UART_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    // 4. Ensure RX line has pull-up to prevent floating break/null conditions
    gpio_set_pull_mode(UART_RX_PIN, GPIO_PULLUP_ONLY);

    bridge_initialized = true;
    if (!match_sem) {
        match_sem = xSemaphoreCreateBinary();
    }
    ESP_LOGI(TAG, "UART1 initialized @ %lu baud, TX=%d RX=%d", (unsigned long)current_baud, UART_TX_PIN, UART_RX_PIN);
}

void uart_bridge_start(void) {
    if (!bridge_initialized) {
        uart_bridge_init();
    }
    if (bridge_running) return;
    bridge_running = true;
    xTaskCreatePinnedToCore(uart_bridge_task, "uart_bridge", 4096, NULL, 5, &bridge_task_handle, 0);
    ESP_LOGI(TAG, "Bridge started on Core 0 (priority 5)");
}

void uart_bridge_stop(void) {
    bridge_running = false;
    if (bridge_task_handle) {
        vTaskDelete(bridge_task_handle);
        bridge_task_handle = NULL;
    }
    ESP_LOGI(TAG, "Bridge stopped");
}

int uart_bridge_write(const uint8_t *data, size_t len) {
    if (!bridge_initialized) {
        uart_bridge_init();
    }
    if (data == NULL || len == 0) return 0;
    return uart_write_bytes(UART_NUM, (const char *)data, len);
}

bool uart_bridge_arm_match(const char *pattern, size_t pattern_len, const char *reply, size_t reply_len) {
    if (!bridge_initialized) {
        uart_bridge_init();
    }
    if (pattern == NULL || pattern_len == 0 || pattern_len > MAX_PATTERN_LEN) {
        return false;
    }
    if (reply != NULL && reply_len > MAX_REPLY_LEN) {
        return false;
    }

    match_active = false;
    match_found = false;
    if (match_sem) {
        xSemaphoreTake(match_sem, 0);
    }

    memcpy(match_pattern, pattern, pattern_len);
    match_pattern_len = pattern_len;
    match_curr_idx = 0;
    compute_kmp_table(match_pattern, match_pattern_len, kmp_next);

    if (reply != NULL && reply_len > 0) {
        memcpy(match_reply, reply, reply_len);
        match_reply_len = reply_len;
    } else {
        match_reply_len = 0;
    }

    match_active = true;
    return true;
}

bool uart_bridge_is_matched(void) {
    return match_found;
}

void uart_bridge_clear_match(void) {
    match_active = false;
    match_found = false;
    match_pattern_len = 0;
    match_curr_idx = 0;
    match_reply_len = 0;
    if (match_sem) {
        xSemaphoreTake(match_sem, 0);
    }
}

bool uart_bridge_wait_for_slice(uint32_t slice_ms) {
    if (match_found) return true;
    if (!match_sem) return false;
    return (xSemaphoreTake(match_sem, pdMS_TO_TICKS(slice_ms)) == pdTRUE);
}

void uart_bridge_task(void *arg) {
    uint8_t buf[512];

    while (bridge_running) {
        if (!tusb_inited() || !tud_mounted()) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        // 1. Stream from UART1 (target RX) -> USB CDC1 (host terminal)
        uint32_t cdc_write_avail = tud_cdc_n_write_available(CDC_INTERFACE);
        if (cdc_write_avail > 0) {
            uint32_t to_read = (sizeof(buf) < cdc_write_avail) ? sizeof(buf) : cdc_write_avail;
            int rx_len = uart_read_bytes(UART_NUM, buf, to_read, pdMS_TO_TICKS(5));
            if (rx_len > 0) {
                // Forward immediately to host USB CDC1
                tud_cdc_n_write(CDC_INTERFACE, buf, rx_len);
                tud_cdc_n_write_flush(CDC_INTERFACE);

                // Hardware/C-level pattern matching on incoming target stream
                if (match_active && match_pattern_len > 0) {
                    for (int i = 0; i < rx_len; i++) {
                        char c = (char)buf[i];
                        while (match_curr_idx > 0 && c != match_pattern[match_curr_idx]) {
                            match_curr_idx = kmp_next[match_curr_idx - 1];
                        }
                        if (c == match_pattern[match_curr_idx]) {
                            match_curr_idx++;
                            if (match_curr_idx == match_pattern_len) {
                                match_found = true;
                                match_active = false;
                                if (match_reply_len > 0) {
                                    uart_write_bytes(UART_NUM, match_reply, match_reply_len);
                                }
                                if (match_sem) {
                                    xSemaphoreGive(match_sem);
                                }
                                break;
                            }
                        }
                    }
                }
            }
        }

        // 2. Stream from USB CDC1 (host terminal) -> UART1 (target TX)
        uint32_t cdc_read_avail = tud_cdc_n_available(CDC_INTERFACE);
        if (cdc_read_avail > 0) {
            uint32_t to_read = (sizeof(buf) < cdc_read_avail) ? sizeof(buf) : cdc_read_avail;
            uint32_t cdc_len = tud_cdc_n_read(CDC_INTERFACE, buf, to_read);
            if (cdc_len > 0) {
                uart_write_bytes(UART_NUM, (const char *)buf, cdc_len);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(2));
    }

    vTaskDelete(NULL);
}