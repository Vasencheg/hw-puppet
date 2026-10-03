include(boards/mpconfigboard_esp32s3_common.cmake)

list(APPEND SDKCONFIG_DEFAULTS
    boards/sdkconfig.spiram_oct
    boards/sdkconfig.flash_qio_80m
    boards/sdkconfig.csi
    ${MICROPY_BOARD_DIR}/sdkconfig.board
)

if(NOT MICROPY_DIR)
    get_filename_component(MICROPY_DIR ${CMAKE_CURRENT_LIST_DIR}/../../../.. ABSOLUTE)
endif()

set(MICROPY_SOURCE_BOARD
    ${MICROPY_BOARD_DIR}/board.c
    ${MICROPY_DIR}/shared/tinyusb/mp_usbd_cdc.c
)

