#ifndef UART_BRIDGE_H
#define UART_BRIDGE_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*uart_rx_tap_fn_t)(const uint8_t *data, size_t len, void *user_ctx);

/**
 * Initialize UART1 hardware and TinyUSB CDC1 interface.
 */
void     uart_bridge_init(void);

/**
 * Start bidirectional UART <-> CDC1 bridge FreeRTOS task on Core 0.
 */
void     uart_bridge_start(void);

/**
 * Stop bridge task.
 */
void     uart_bridge_stop(void);

/**
 * Configure target hardware UART baud rate.
 */
bool     uart_bridge_set_baud(uint32_t baud_rate);

/**
 * Get current baud rate.
 */
uint32_t uart_bridge_get_baud(void);

/**
 * Write raw data to target hardware UART.
 */
int      uart_bridge_write(const uint8_t *data, size_t len);

/**
 * Register a passive RX tap callback to inspect target UART data as it arrives.
 */
void     uart_bridge_set_rx_tap(uart_rx_tap_fn_t tap_fn, void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // UART_BRIDGE_H