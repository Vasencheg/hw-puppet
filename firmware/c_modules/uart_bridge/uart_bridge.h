#ifndef UART_BRIDGE_H
#define UART_BRIDGE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void uart_bridge_init(void);
void uart_bridge_start(void);
void uart_bridge_stop(void);
bool uart_bridge_set_baud(uint32_t baud_rate);
uint32_t uart_bridge_get_baud(void);
int uart_bridge_write(const uint8_t *data, size_t len);

bool uart_bridge_arm_match(const char *pattern, size_t pattern_len, const char *reply, size_t reply_len);
bool uart_bridge_is_matched(void);
void uart_bridge_clear_match(void);
bool uart_bridge_wait_for_slice(uint32_t slice_ms);

#ifdef __cplusplus
}
#endif

#endif