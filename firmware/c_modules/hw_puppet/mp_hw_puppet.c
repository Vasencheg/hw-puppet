#include "py/runtime.h"
#include "py/obj.h"
#include "py/objstr.h"
#include "hw_puppet.h"

// Forward declaration of native submodules
extern const mp_obj_module_t mp_module_uart_bridge;

// --- Version & Metadata String Objects ---
static const mp_obj_str_t mp_hw_puppet_version_obj = {
    .base = { &mp_type_str },
    .hash = 0,
    .len = sizeof(HW_PUPPET_VERSION_STR) - 1,
    .data = (const byte *)HW_PUPPET_VERSION_STR,
};

static const mp_obj_str_t mp_hw_puppet_git_hash_obj = {
    .base = { &mp_type_str },
    .hash = 0,
    .len = sizeof(HW_PUPPET_GIT_HASH_STR) - 1,
    .data = (const byte *)HW_PUPPET_GIT_HASH_STR,
};

static const mp_obj_str_t mp_hw_puppet_build_date_obj = {
    .base = { &mp_type_str },
    .hash = 0,
    .len = sizeof(HW_PUPPET_BUILD_DATE_STR) - 1,
    .data = (const byte *)HW_PUPPET_BUILD_DATE_STR,
};

static const mp_obj_str_t mp_hw_puppet_platform_obj = {
    .base = { &mp_type_str },
    .hash = 0,
    .len = sizeof(HW_PUPPET_PLATFORM_STR) - 1,
    .data = (const byte *)HW_PUPPET_PLATFORM_STR,
};

// hw_puppet.info() -> dict
static mp_obj_t mp_hw_puppet_info(void) {
    mp_obj_t dict = mp_obj_new_dict(4);
    mp_obj_dict_store(dict, MP_ROM_QSTR(MP_QSTR_version), (mp_obj_t)&mp_hw_puppet_version_obj);
    mp_obj_dict_store(dict, MP_ROM_QSTR(MP_QSTR_git_hash), (mp_obj_t)&mp_hw_puppet_git_hash_obj);
    mp_obj_dict_store(dict, MP_ROM_QSTR(MP_QSTR_build_date), (mp_obj_t)&mp_hw_puppet_build_date_obj);
    mp_obj_dict_store(dict, MP_ROM_QSTR(MP_QSTR_platform), (mp_obj_t)&mp_hw_puppet_platform_obj);
    return dict;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_hw_puppet_info_obj, mp_hw_puppet_info);

// --- Module Globals Table ---
static const mp_rom_map_elem_t mp_module_hw_puppet_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),      MP_ROM_QSTR(MP_QSTR_hw_puppet) },
    { MP_ROM_QSTR(MP_QSTR___version__),   MP_ROM_PTR(&mp_hw_puppet_version_obj) },
    { MP_ROM_QSTR(MP_QSTR_VERSION),       MP_ROM_PTR(&mp_hw_puppet_version_obj) },
    { MP_ROM_QSTR(MP_QSTR_version),       MP_ROM_PTR(&mp_hw_puppet_version_obj) },
    { MP_ROM_QSTR(MP_QSTR_info),          MP_ROM_PTR(&mp_hw_puppet_info_obj) },
    // Builtin Submodules: allows 'from hw_puppet import uart_bridge' and 'import hw_puppet.uart_bridge'
    { MP_ROM_QSTR(MP_QSTR_uart_bridge),   MP_ROM_PTR(&mp_module_uart_bridge) },
};
static MP_DEFINE_CONST_DICT(mp_module_hw_puppet_globals, mp_module_hw_puppet_globals_table);

const mp_obj_module_t mp_module_hw_puppet = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mp_module_hw_puppet_globals,
};

MP_REGISTER_MODULE(MP_QSTR_hw_puppet, mp_module_hw_puppet);
