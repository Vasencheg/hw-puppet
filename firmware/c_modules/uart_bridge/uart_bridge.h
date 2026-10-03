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

#ifdef __cplusplus
}
#endif

#endif