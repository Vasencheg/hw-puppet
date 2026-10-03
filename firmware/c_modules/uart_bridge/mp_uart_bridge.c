#include "py/runtime.h"
#include "py/obj.h"
#include "uart_bridge.h"

static mp_obj_t mp_uart_bridge_start(void) {
    uart_bridge_start();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_start_obj, mp_uart_bridge_start);

static mp_obj_t mp_uart_bridge_stop(void) {
    uart_bridge_stop();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_stop_obj, mp_uart_bridge_stop);

static mp_obj_t mp_uart_bridge_init(void) {
    uart_bridge_init();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_init_obj, mp_uart_bridge_init);

static mp_obj_t mp_uart_bridge_set_baud(mp_obj_t baud_obj) {
    mp_int_t baud = mp_obj_get_int(baud_obj);
    bool ok = uart_bridge_set_baud((uint32_t)baud);
    return mp_obj_new_bool(ok);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_uart_bridge_set_baud_obj, mp_uart_bridge_set_baud);

static mp_obj_t mp_uart_bridge_get_baud(void) {
    return mp_obj_new_int_from_uint(uart_bridge_get_baud());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_get_baud_obj, mp_uart_bridge_get_baud);

static const mp_rom_map_elem_t mp_module_uart_bridge_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_uart_bridge) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&mp_uart_bridge_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&mp_uart_bridge_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&mp_uart_bridge_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_baud), MP_ROM_PTR(&mp_uart_bridge_set_baud_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_baud), MP_ROM_PTR(&mp_uart_bridge_get_baud_obj) },
};
static MP_DEFINE_CONST_DICT(mp_module_uart_bridge_globals, mp_module_uart_bridge_globals_table);

const mp_obj_module_t mp_module_uart_bridge = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mp_module_uart_bridge_globals,
};

MP_REGISTER_MODULE(MP_QSTR_uart_bridge, mp_module_uart_bridge);