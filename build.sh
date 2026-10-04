#!/bin/bash
# ==============================================================================
# Build script for HW-PUPPET MicroPython Firmware
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MICROPYTHON_ROOT="${MICROPYTHON_ROOT:-$SCRIPT_DIR/lib/micropython}"
PORT_DIR="${MICROPYTHON_ROOT}/ports/esp32"
BOARD="${BOARD:-HW_PUPPET}"
BOARD_DIR="$SCRIPT_DIR/firmware/boards/$BOARD"
BUILD_DIR="$SCRIPT_DIR/build"
USER_C_MODULES="$SCRIPT_DIR/firmware/c_modules/micropython.cmake"
PATCH_FILE="$SCRIPT_DIR/firmware/patches/0001-tinyusb-dual-cdc.patch"

# Handle arguments
if [ "$1" = "clean" ]; then
    echo "-> Cleaning build artifacts..."
    rm -rf "$BUILD_DIR"
    if [ -d "$PORT_DIR/build-$BOARD" ]; then
        echo "-> Removing $PORT_DIR/build-$BOARD..."
        rm -rf "$PORT_DIR/build-$BOARD"
    fi
    echo "Clean complete."
    exit 0
elif [ "$1" = "--clean" ] || [ "$1" = "-c" ]; then
    echo "-> Cleaning build artifacts before build..."
    rm -rf "$BUILD_DIR"
    if [ -d "$PORT_DIR/build-$BOARD" ]; then
        rm -rf "$PORT_DIR/build-$BOARD"
    fi
elif [ "$1" = "install" ] || [ "$1" = "install-rules" ] || [ "$1" = "install-udev" ]; then
    UDEV_SRC="$SCRIPT_DIR/udev/99-hw-puppet.rules"
    echo "-> Installing udev rules from $UDEV_SRC to /etc/udev/rules.d/..."
    if [ ! -f "$UDEV_SRC" ]; then
        echo "ERROR: udev rules file not found at $UDEV_SRC"
        exit 1
    fi
    sudo cp "$UDEV_SRC" /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    echo "Udev rules installed successfully."
    echo "Device symlinks:"
    echo "  /dev/hw-puppet-control -> CDC 0 (MicroPython REPL)"
    echo "  /dev/hw-puppet-uart    -> CDC 1 (Target UART console)"
    exit 0
elif [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    echo "Usage: $0 [clean | --clean | -c | install | --help]"
    echo ""
    echo "Commands / Options:"
    echo "  (none)                  Build firmware and copy artifacts to build/"
    echo "  clean                   Remove build/ and internal MicroPython build artifacts, then exit"
    echo "  --clean, -c             Clean before performing the build"
    echo "  install, install-rules  Install udev rules to /etc/udev/rules.d/ and reload"
    echo "  --help, -h              Show this help message"
    exit 0
fi

echo "=================================================="
echo "    HW-PUPPET Firmware Build (ESP32-S3)"
echo "=================================================="
echo "MicroPython root : $MICROPYTHON_ROOT"
echo "Board definition : $BOARD_DIR"
echo "User C modules   : $USER_C_MODULES"
echo "Build directory  : $BUILD_DIR"
echo "=================================================="

# 1. Check MicroPython submodule
if [ ! -f "$MICROPYTHON_ROOT/py/mpconfig.h" ]; then
    echo "-> Initializing MicroPython submodule..."
    cd "$SCRIPT_DIR"
    git submodule update --init lib/micropython
    cd "$MICROPYTHON_ROOT"
    git checkout v1.29.0
    git submodule update --init lib/berkeley-db-1.xx lib/micropython-lib
fi

# 2. Check and apply dual-CDC patch
cd "$MICROPYTHON_ROOT"
if ! grep -q "MICROPY_HW_USB_CDC_NUM" shared/tinyusb/tusb_config.h 2>/dev/null; then
    echo "-> Applying Dual-CDC patch to MicroPython..."
    git apply "$PATCH_FILE"
    echo "   Patch applied successfully."
else
    echo "-> Dual-CDC patch is already applied."
fi

# 3. Check ESP-IDF environment
if ! command -v idf.py &> /dev/null; then
    if [ -n "$IDF_PATH" ] && [ -f "$IDF_PATH/export.sh" ]; then
        echo "-> Activating ESP-IDF from $IDF_PATH/export.sh..."
        . "$IDF_PATH/export.sh"
    elif [ -f "/opt/esp/idf/export.sh" ]; then
        echo "-> Activating ESP-IDF from /opt/esp/idf/export.sh..."
        . "/opt/esp/idf/export.sh"
    fi
fi

if ! command -v idf.py &> /dev/null; then
    echo ""
    echo "ERROR: idf.py not found in PATH."
    echo "Please activate ESP-IDF 5.4+ first (e.g. '. export.sh')."
    exit 1
fi

# 4. Sync board configuration into MicroPython tree
rm -rf "$PORT_DIR/boards/$BOARD"
mkdir -p "$PORT_DIR/boards/$BOARD"
cp -r "$BOARD_DIR/"* "$PORT_DIR/boards/$BOARD/"

# 5. Ensure mpy-cross is built
if [ ! -f "$MICROPYTHON_ROOT/mpy-cross/build/mpy-cross" ]; then
    echo "-> Building mpy-cross..."
    make -C "$MICROPYTHON_ROOT/mpy-cross"
fi

# 6. Build firmware
echo "-> Building MicroPython firmware for $BOARD..."
cd "$PORT_DIR"
make BOARD="$BOARD" USER_C_MODULES="$USER_C_MODULES" all

# 7. Copy output artifacts to root build/ directory
echo "-> Copying build artifacts to $BUILD_DIR..."
mkdir -p "$BUILD_DIR"
cp -f "$PORT_DIR/build-$BOARD/firmware.bin" "$BUILD_DIR/"
cp -f "$PORT_DIR/build-$BOARD/bootloader/bootloader.bin" "$BUILD_DIR/" 2>/dev/null || true
cp -f "$PORT_DIR/build-$BOARD/partition_table/partition-table.bin" "$BUILD_DIR/" 2>/dev/null || true
cp -f "$PORT_DIR/build-$BOARD/micropython.bin" "$BUILD_DIR/" 2>/dev/null || true
cp -f "$PORT_DIR/build-$BOARD/micropython.elf" "$BUILD_DIR/" 2>/dev/null || true

echo ""
echo "=================================================="
echo "Build complete!"
echo "Firmware binary: $BUILD_DIR/firmware.bin"
echo ""
echo "To flash (connect cable to 'UART' port):"
echo "  cd $PORT_DIR && make BOARD=$BOARD deploy"
echo "  or directly with esptool:"
echo "  esptool.py -p /dev/ttyACM0 -b 460800 write_flash 0x0 $BUILD_DIR/firmware.bin"
echo "=================================================="
