#include "py/runtime.h"
#include "py/mphal.h"
#include "uart_bridge.h"

void board_init(void) {
}

void board_usb_init(void) {
}

void boardctrl_startup(void);

void HW_PUPPET_board_startup(void) {
    boardctrl_startup();
    uart_bridge_start();
}