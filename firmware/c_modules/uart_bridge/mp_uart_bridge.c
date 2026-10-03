#include "py/runtime.h"
#include "py/obj.h"
#include "py/objstr.h"
#include "uart_bridge.h"
#include "pattern_matcher.h"

// ==============================================================================
// 1. Subsystem Wiring & Lifecycle
// ==============================================================================

static bool s_subsystems_wired = false;

static void on_uart_rx_tap(const uint8_t *data, size_t len, void *user_ctx) {
    (void)user_ctx;
    pattern_matcher_process_bytes(data, len);
}

static int on_reply_write(const uint8_t *data, size_t len, void *user_ctx) {
    (void)user_ctx;
    return uart_bridge_write(data, len);
}

static void ensure_subsystems_wired(void) {
    if (s_subsystems_wired) return;
    uart_bridge_init();
    pattern_matcher_init();
    uart_bridge_set_rx_tap(on_uart_rx_tap, NULL);
    pattern_matcher_set_reply_writer(on_reply_write, NULL);
    s_subsystems_wired = true;
}

// ==============================================================================
// 2. Match Object Definition & Lifecycle
// ==============================================================================

typedef struct _mp_obj_uart_match_t {
    mp_obj_base_t base;
    int slot_id;
    mp_obj_t callback;
    mp_obj_t pattern_str;
} mp_obj_uart_match_t;

extern const mp_obj_type_t mp_type_uart_match;

// Static table to keep Match objects rooted in GC while active
static mp_obj_t active_match_roots[PATTERN_MATCHER_MAX_TRIGGERS];

// Callback dispatched from C engine (called via pattern_matcher in Core 0 context)
static void mp_bridge_match_cb(int slot_id, const char *pattern, void *user_data) {
    mp_obj_uart_match_t *self = (mp_obj_uart_match_t *)user_data;
    if (self && self->callback != mp_const_none && self->slot_id >= 0) {
        // Schedule callback execution in MicroPython VM thread without allocations
        mp_sched_schedule(self->callback, self->pattern_str);
    }
}

static void mp_uart_match_print(const mp_print_t *print, mp_obj_t self_in, mp_print_kind_t kind) {
    mp_obj_uart_match_t *self = MP_OBJ_TO_PTR(self_in);
    bool active = (self->slot_id >= 0 && pattern_matcher_trigger_is_active(self->slot_id));
    mp_printf(print, "<Match pattern=%s active=%s slot=%d>",
              mp_obj_str_get_str(self->pattern_str),
              active ? "True" : "False",
              self->slot_id);
}

// match.cancel()
static mp_obj_t mp_uart_match_cancel(mp_obj_t self_in) {
    mp_obj_uart_match_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->slot_id >= 0) {
        pattern_matcher_cancel_trigger(self->slot_id);
        if (self->slot_id < PATTERN_MATCHER_MAX_TRIGGERS) {
            active_match_roots[self->slot_id] = mp_const_none;
        }
        self->slot_id = -1;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_uart_match_cancel_obj, mp_uart_match_cancel);

// match.is_active()
static mp_obj_t mp_uart_match_is_active(mp_obj_t self_in) {
    mp_obj_uart_match_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->slot_id >= 0 && pattern_matcher_trigger_is_active(self->slot_id)) {
        return mp_const_true;
    }
    return mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_uart_match_is_active_obj, mp_uart_match_is_active);

// Context manager protocol: __enter__ returns self
static mp_obj_t mp_uart_match_enter(mp_obj_t self_in) {
    return self_in;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_uart_match_enter_obj, mp_uart_match_enter);

// Context manager protocol: __exit__ calls cancel()
static mp_obj_t mp_uart_match_exit(size_t n_args, const mp_obj_t *args) {
    return mp_uart_match_cancel(args[0]);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_uart_match_exit_obj, 1, 4, mp_uart_match_exit);

static const mp_rom_map_elem_t mp_uart_match_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_cancel), MP_ROM_PTR(&mp_uart_match_cancel_obj) },
    { MP_ROM_QSTR(MP_QSTR_is_active), MP_ROM_PTR(&mp_uart_match_is_active_obj) },
    { MP_ROM_QSTR(MP_QSTR___enter__), MP_ROM_PTR(&mp_uart_match_enter_obj) },
    { MP_ROM_QSTR(MP_QSTR___exit__), MP_ROM_PTR(&mp_uart_match_exit_obj) },
};
static MP_DEFINE_CONST_DICT(mp_uart_match_locals_dict, mp_uart_match_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    mp_type_uart_match,
    MP_QSTR_Match,
    MP_TYPE_FLAG_NONE,
    print, mp_uart_match_print,
    locals_dict, &mp_uart_match_locals_dict
);

// ==============================================================================
// 3. uart_bridge Module Functions
// ==============================================================================

// uart_bridge.on_match(pattern, callback, reply=None, once=False, debounce_ms=100, case_sensitive=True) -> Match
static mp_obj_t mp_uart_bridge_on_match(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_pattern, ARG_callback, ARG_reply, ARG_once, ARG_debounce_ms, ARG_case_sensitive };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_pattern,        MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_callback,       MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_reply,          MP_ARG_OBJ,                   {.u_obj = mp_const_none} },
        { MP_QSTR_once,           MP_ARG_BOOL,                  {.u_bool = false} },
        { MP_QSTR_debounce_ms,    MP_ARG_INT,                   {.u_int = 100} },
        { MP_QSTR_case_sensitive, MP_ARG_BOOL,                  {.u_bool = true} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    ensure_subsystems_wired();

    size_t pat_len;
    const char *pat = mp_obj_str_get_data(args[ARG_pattern].u_obj, &pat_len);

    size_t rep_len = 0;
    const char *rep = NULL;
    if (args[ARG_reply].u_obj != mp_const_none) {
        rep = mp_obj_str_get_data(args[ARG_reply].u_obj, &rep_len);
    }

    // Allocate Match instance on MicroPython heap
    mp_obj_uart_match_t *match_obj = m_new_obj(mp_obj_uart_match_t);
    match_obj->base.type = &mp_type_uart_match;
    match_obj->callback = args[ARG_callback].u_obj;
    match_obj->pattern_str = args[ARG_pattern].u_obj;
    match_obj->slot_id = -1;

    int slot = pattern_matcher_register_trigger(
        pat, pat_len,
        rep, rep_len,
        args[ARG_once].u_bool,
        args[ARG_debounce_ms].u_int,
        args[ARG_case_sensitive].u_bool,
        mp_bridge_match_cb,
        match_obj
    );

    if (slot < 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("all match trigger slots (8) are in use"));
    }

    match_obj->slot_id = slot;
    active_match_roots[slot] = MP_OBJ_FROM_PTR(match_obj);

    return MP_OBJ_FROM_PTR(match_obj);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mp_uart_bridge_on_match_obj, 2, mp_uart_bridge_on_match);

// uart_bridge.clear_matches()
static mp_obj_t mp_uart_bridge_clear_matches(void) {
    pattern_matcher_clear_all_triggers();
    for (int i = 0; i < PATTERN_MATCHER_MAX_TRIGGERS; i++) {
        active_match_roots[i] = mp_const_none;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_clear_matches_obj, mp_uart_bridge_clear_matches);

// Synchronous helper: uart_bridge.wait_for(pattern, reply=None, timeout_ms=5000, case_sensitive=True) -> bool
static mp_obj_t mp_uart_bridge_wait_for(size_t n_args, const mp_obj_t *args) {
    ensure_subsystems_wired();

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

    bool case_sensitive = true;
    if (n_args >= 4) {
        case_sensitive = mp_obj_is_true(args[3]);
    }

    bool matched = pattern_matcher_wait_for(pat, pat_len, rep, rep_len, (uint32_t)timeout_ms, case_sensitive);
    return mp_obj_new_bool(matched);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_uart_bridge_wait_for_obj, 1, 4, mp_uart_bridge_wait_for);

// Direct transmission to target UART
static mp_obj_t mp_uart_bridge_write(mp_obj_t data_obj) {
    ensure_subsystems_wired();
    size_t len;
    const char *data = mp_obj_str_get_data(data_obj, &len);
    int written = uart_bridge_write((const uint8_t *)data, len);
    return mp_obj_new_int(written);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_uart_bridge_write_obj, mp_uart_bridge_write);

// Lifecycle controls
static mp_obj_t mp_uart_bridge_init(void) {
    ensure_subsystems_wired();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_init_obj, mp_uart_bridge_init);

static mp_obj_t mp_uart_bridge_start(void) {
    ensure_subsystems_wired();
    uart_bridge_start();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_start_obj, mp_uart_bridge_start);

static mp_obj_t mp_uart_bridge_stop(void) {
    uart_bridge_stop();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_stop_obj, mp_uart_bridge_stop);

static mp_obj_t mp_uart_bridge_set_baud(mp_obj_t baud_obj) {
    ensure_subsystems_wired();
    mp_int_t baud = mp_obj_get_int(baud_obj);
    bool ok = uart_bridge_set_baud((uint32_t)baud);
    return mp_obj_new_bool(ok);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_uart_bridge_set_baud_obj, mp_uart_bridge_set_baud);

static mp_obj_t mp_uart_bridge_get_baud(void) {
    ensure_subsystems_wired();
    return mp_obj_new_int_from_uint(uart_bridge_get_baud());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_uart_bridge_get_baud_obj, mp_uart_bridge_get_baud);

// --- Module Globals Table ---
static const mp_rom_map_elem_t mp_module_uart_bridge_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),      MP_ROM_QSTR(MP_QSTR_uart_bridge) },
    { MP_ROM_QSTR(MP_QSTR_on_match),      MP_ROM_PTR(&mp_uart_bridge_on_match_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear_matches), MP_ROM_PTR(&mp_uart_bridge_clear_matches_obj) },
    { MP_ROM_QSTR(MP_QSTR_wait_for),      MP_ROM_PTR(&mp_uart_bridge_wait_for_obj) },
    { MP_ROM_QSTR(MP_QSTR_write),         MP_ROM_PTR(&mp_uart_bridge_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_init),          MP_ROM_PTR(&mp_uart_bridge_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_start),         MP_ROM_PTR(&mp_uart_bridge_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_stop),          MP_ROM_PTR(&mp_uart_bridge_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_baud),      MP_ROM_PTR(&mp_uart_bridge_set_baud_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_baud),      MP_ROM_PTR(&mp_uart_bridge_get_baud_obj) },
    { MP_ROM_QSTR(MP_QSTR_Match),         MP_ROM_PTR(&mp_type_uart_match) },
};
static MP_DEFINE_CONST_DICT(mp_module_uart_bridge_globals, mp_module_uart_bridge_globals_table);

const mp_obj_module_t mp_module_uart_bridge = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mp_module_uart_bridge_globals,
};

MP_REGISTER_MODULE(MP_QSTR_uart_bridge, mp_module_uart_bridge);