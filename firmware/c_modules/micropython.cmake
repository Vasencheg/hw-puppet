# User C Modules for MicroPython ESP32 (HW-PUPPET)

add_library(usermod_hw_puppet INTERFACE)

# Extract Git version information at configuration time
execute_process(
    COMMAND git describe --tags --always --dirty
    WORKING_DIRECTORY ${CMAKE_CURRENT_LIST_DIR}
    OUTPUT_VARIABLE HW_PUPPET_GIT_TAG
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
)
execute_process(
    COMMAND git rev-parse --short HEAD
    WORKING_DIRECTORY ${CMAKE_CURRENT_LIST_DIR}
    OUTPUT_VARIABLE HW_PUPPET_GIT_REV
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
)
if(NOT HW_PUPPET_GIT_TAG)
    set(HW_PUPPET_GIT_TAG "0.1.0-dev")
endif()
if(NOT HW_PUPPET_GIT_REV)
    set(HW_PUPPET_GIT_REV "unknown")
endif()

target_sources(usermod_hw_puppet INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/hw_puppet/hw_puppet.c
    ${CMAKE_CURRENT_LIST_DIR}/hw_puppet/mp_hw_puppet.c
    ${CMAKE_CURRENT_LIST_DIR}/uart_bridge/uart_bridge.c
    ${CMAKE_CURRENT_LIST_DIR}/pattern_matcher/pattern_matcher.c
    ${CMAKE_CURRENT_LIST_DIR}/uart_bridge/mp_uart_bridge.c
)

target_include_directories(usermod_hw_puppet INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/hw_puppet
    ${CMAKE_CURRENT_LIST_DIR}/uart_bridge
    ${CMAKE_CURRENT_LIST_DIR}/pattern_matcher
)

target_compile_definitions(usermod_hw_puppet INTERFACE
    HW_PUPPET_VERSION_RAW=${HW_PUPPET_GIT_TAG}
    HW_PUPPET_GIT_HASH_RAW=${HW_PUPPET_GIT_REV}
)

target_link_libraries(usermod INTERFACE usermod_hw_puppet)
