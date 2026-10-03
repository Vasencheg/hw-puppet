# User C Modules for MicroPython ESP32 (HW-PUPPET)

add_library(usermod_hw_puppet INTERFACE)

target_sources(usermod_hw_puppet INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/uart_bridge/uart_bridge.c
    ${CMAKE_CURRENT_LIST_DIR}/uart_bridge/mp_uart_bridge.c
)

target_include_directories(usermod_hw_puppet INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/uart_bridge
)

target_link_libraries(usermod INTERFACE usermod_hw_puppet)
