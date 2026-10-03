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

static mp_obj_t mp_uart_bridge_write(mp_obj_t data_obj) {
    size_t len;
    const char *data = mp_obj_str_get_data(data_obj, &len);
    int written = uart_bridge_write((const uint8_t *)data, len);
    return mp_obj_new_int(written);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_uart_bridge_write_obj, mp_uart_bridge_write);

static mp_obj_t mp_uart_bridge_arm_match(size_t n_args, const mp_obj_t *args) {
    size_t pat_len;
    const char *pat = mp_obj_str_get_data(args[0], &pat_len);

    size_t rep_len = 0;
    const char *rep = NULL;
    if (n_args >= 2 && args[1] != mp_const_none) {
        rep = mp_obj_str_get_data(args[1], &rep_len);
    }

    if (!uart_bridge_arm_match(pat, pat_len, rep, rep_len)) {
        mp_raise_ValueError(MP_ERROR_TEXT("pattern or reply too long (max 64/32)"));
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_uart_bridge_arm_match_obj, 1, 2, mp_uart_bridge_arm_match);

static mp_obj_t mp_uart_bridge_is_matched(void) {
    return mp_obj_new_bool(uart_bridge_is_matched());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_is_matched_obj, mp_uart_bridge_is_matched);

static mp_obj_t mp_uart_bridge_clear_match(void) {
    uart_bridge_clear_match();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_clear_match_obj, mp_uart_bridge_clear_match);

static mp_obj_t mp_uart_bridge_wait_for(size_t n_args, const mp_obj_t *args) {
    size_t pat_len;
    const char *pat = mp_obj_str_get_data(args[0], &pat_len);

    size_t rep_len = 0;
    const char *rep = NULL;
    if (n_args >= 2 && args[1] != mp_const_none) {
        rep = mp_obj_str_get_data(args[1], &rep_len);
    }

    mp_int_t timeout_ms = 5000;
    if (n_args >= 3) {
        timeout_ms = mp_obj_get_int(args[2]);
    }

    if (!uart_bridge_arm_match(pat, pat_len, rep, rep_len)) {
        mp_raise_ValueError(MP_ERROR_TEXT("pattern or reply too long (max 64/32)"));
    }

    mp_int_t remaining = timeout_ms;
    while (remaining > 0) {
        uint32_t slice = (remaining > 50) ? 50 : remaining;
        if (uart_bridge_wait_for_slice(slice)) {
            return mp_const_true;
        }
        remaining -= slice;
        mp_handle_pending(true);
    }

    return mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_uart_bridge_wait_for_obj, 1, 3, mp_uart_bridge_wait_for);

static const mp_rom_map_elem_t mp_module_uart_bridge_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_uart_bridge) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&mp_uart_bridge_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&mp_uart_bridge_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&mp_uart_bridge_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_baud), MP_ROM_PTR(&mp_uart_bridge_set_baud_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_baud), MP_ROM_PTR(&mp_uart_bridge_get_baud_obj) },
    { MP_ROM_QSTR(MP_QSTR_write), MP_ROM_PTR(&mp_uart_bridge_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_arm_match), MP_ROM_PTR(&mp_uart_bridge_arm_match_obj) },
    { MP_ROM_QSTR(MP_QSTR_matched), MP_ROM_PTR(&mp_uart_bridge_is_matched_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear_match), MP_ROM_PTR(&mp_uart_bridge_clear_match_obj) },
    { MP_ROM_QSTR(MP_QSTR_wait_for), MP_ROM_PTR(&mp_uart_bridge_wait_for_obj) },
};
static MP_DEFINE_CONST_DICT(mp_module_uart_bridge_globals, mp_module_uart_bridge_globals_table);

const mp_obj_module_t mp_module_uart_bridge = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mp_module_uart_bridge_globals,
};

MP_REGISTER_MODULE(MP_QSTR_uart_bridge, mp_module_uart_bridge);