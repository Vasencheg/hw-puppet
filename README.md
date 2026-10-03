# 🎭 HW Puppet (HWPuppet)

**The Puppet Master for Embedded Target Boards**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MicroPython: v1.29.0](https://img.shields.io/badge/MicroPython-v1.29.0-blue.svg)](https://micropython.org/)
[![Hardware: ESP32--S3](https://img.shields.io/badge/Hardware-ESP32--S3-red.svg)](https://www.espressif.com/)

**HW Puppet** (`hw-puppet`) is a standalone, open-source Hardware-in-the-Loop (HIL) automation bridge and test harness.

Flash the firmware onto an off-the-shelf **ESP32-S3-DevKitC-1** development board, and it immediately becomes a dedicated **HW Puppet** device that "pulls the strings" on your target embedded boards: controlling hardware lines (RESET, RECOVERY/BOOT, POWER relay, GPIOs) and streaming high-speed UART consoles over a single physical USB Type-C connection.

---

## 1. Architecture

```text
[ Host Machine (PC / CI / Test Runner / AI Agent) ]
                      │
                      │ Single USB-C Cable (Native USB OTG)
                      ▼
             ┌─────────────────┐
             │    HW-PUPPET    │ (ESP32-S3 @ MicroPython v1.29.0 + TinyUSB)
             │                 │
             │  ┌───────────┐  │
             │  │   CDC 0   │  │ Control Channel (/dev/hw-puppet-control or /dev/ttyACM0)
             │  │ (Raw REPL)│  │ -> Zero-flash RAM execution for pin manipulation
             │  └─────┬─────┘  │
             │        │        │
             │  ┌─────┴─────┐  │
             │  │   CDC 1   │  │ UART Console Bridge (/dev/hw-puppet-uart or /dev/ttyACM1)
             │  │(Raw Bridge│  │ -> Transparent hardware UART up to 921600+ baud
             │  └─────┬─────┘  │
             └────────┼────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
  [ Control Lines ]          [ Target Console ]
  (RESET, RECOVERY,          (TX / RX @ 115200..921600)
   POWER RELAY, GPIO)               │
        │                           │
        └─────────────┬─────────────┘
                      ▼
          [ Target Dev Board (DUT) ]
   (NVIDIA Jetson, Raspberry Pi, STM32, NXP, etc.)
```

### Key Technical Pillars
* **Single Physical Connection:** A single USB Type-C cable powers the ESP32-S3 and provides both control and data paths.
* **USB Composite Device (Dual CDC):** Powered by custom TinyUSB descriptors:
  * **CDC 0 (`/dev/hw-puppet-control` / `/dev/ttyACM0`):** MicroPython REPL (115200 baud). Host executes scripts directly in RAM using zero-flash Raw REPL RPC.
  * **CDC 1 (`/dev/hw-puppet-uart` / `/dev/ttyACM1`):** Transparent hardware UART bridge connected to the target console (default 115200 baud, configurable up to 921600+).
* **Standard Hardware Control:** Native `machine.Pin`, `machine.Timer`, `neopixel` (WS2812 status LED), and `Pin.irq` without custom driver lock-in.
* **Completely Framework-Agnostic:** Works with any language, `pytest`, bash scripts, `minicom`/`tio`, CI/CD pipelines, or agentic tool frameworks (MCP).

---

## 2. Supported Hardware & Platform

`hw-puppet` runs on the **Espressif ESP32-S3** microcontroller series featuring native USB OTG peripheral support.

<p align="center">
  <img src="https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/_images/esp32-s3-devkitc-1-v1.1-isometric.png" alt="ESP32-S3-DevKitC-1" width="450"/>
</p>

### Recommended Module & Development Board
* **Module:** [**ESP32-S3-WROOM-1**](https://www.espressif.com/en/products/modules/esp32-s3-wroom-1) / **ESP32-S3-WROOM-1U** (PCB antenna or external IPEX connector).
  * **Memory Configuration:** **N8R8** or **N16R8** (8MB/16MB Quad-SPI Flash + 8MB Octal-SPI PSRAM).
  * **Processor:** Dual-core Xtensa® 32-bit LX7 @ up to 240 MHz.
  * **USB:** Hardware USB 1.1 Full-Speed OTG PHY.
* **Reference Development Board:** [**ESP32-S3-DevKitC-1**](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/index.html) (Espressif Systems) or any pin-compatible dual Type-C clone board.
* **Documentation & Schematics:** [Espressif ESP32-S3-DevKitC-1 User Guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/index.html)

### Understanding the Dual USB Type-C Ports
The recommended dev boards feature two distinct USB Type-C receptacles:
| Port Label on Board | Hardware Interface | Role in `hw-puppet` |
|:---|:---|:---|
| **`USB`** (Native USB OTG) | ESP32-S3 internal USB PHY (`GPIO 19` = D-, `GPIO 20` = D+) | **Primary operational connection.** Hosts the TinyUSB Dual CDC stack: CDC 0 (MicroPython Raw REPL RPC) + CDC 1 (Transparent UART Bridge). Connect your host machine or CI runner here. |
| **`UART`** (USB-to-Serial) | On-board CP2102 / CH343 / CH9102 converter | **Flashing & low-level debug port.** Used for flashing initial bootloader & firmware images via `esptool.py`. |

---

## 3. Pinout & Hardware Connections

### ESP32-S3 Pin Mapping (Default)
| ESP32-S3 Pin | Function | Target / DUT Connection | Description |
|:---|:---|:---|:---|
| **GPIO 43** | UART1 TX | Target RX | Serial command TX to target console |
| **GPIO 44** | UART1 RX | Target TX | Serial log RX from target console |
| **GPIO 1** | Control 1 | RESET pin | Active low/high pulse to reset target |
| **GPIO 2** | Control 2 | RECOVERY / BOOT pin | Held low/high during reset for bootloader |
| **GPIO 3** | Control 3 | POWER Relay / Mosfet | 12V/5V DC barrel jack power cycle |
| **GND** | Ground | Target GND | Common reference ground (**mandatory**) |

---

## 4. Quickstart

### 4.1 Install Udev Rules (Linux)
Install udev rules to get persistent, human-readable symlinks:
```bash
./build.sh install-rules
```
This registers:
* `/dev/hw-puppet-control` -> CDC 0 (MicroPython REPL)
* `/dev/hw-puppet-uart` -> CDC 1 (Target UART console)

### 4.2 Flash Pre-built Firmware
Connect the ESP32-S3 USB port in download mode (hold BOOT, tap RESET, release BOOT):
```bash
esptool.py -p /dev/ttyACM0 -b 460800 write_flash 0x0 build/firmware.bin
```

### 4.3 Monitor Target Console
Open CDC 1 to see target boot logs:
```bash
./tools/monitor_target.py
# Or with any serial terminal:
tio /dev/hw-puppet-uart
```

### 4.4 Execute Control Scripts on the Board
Run Python scripts directly on the ESP32-S3 in RAM (no flash wear):
```bash
./tools/run_script.py examples/jetson_reset.py
./tools/run_script.py examples/jetson_recovery.py
```

---

## 5. Building Firmware from Source

### Prerequisites
* ESP-IDF v5.4+ installed and activated (`. $IDF_PATH/export.sh`)
* CMake & Ninja

### Build
```bash
./build.sh
```
Output artifacts are copied to `build/`:
* `build/firmware.bin` (Combined flash binary)
* `build/bootloader.bin`
* `build/partition-table.bin`

---

## 6. Repository Structure

```text
hw-puppet/
├── build.sh                   # Unified firmware build & udev install script
├── build/                     # Compiled firmware binaries
├── firmware/                  # ESP32-S3 firmware sources
│   ├── boards/HW_PUPPET/      # Board definition, pins, TinyUSB config & board.c
│   ├── c_modules/             # Native MicroPython C modules
│   │   ├── uart_bridge/       # Transparent CDC1 <-> UART1 bridge driver
│   │   └── micropython.cmake  # User C modules registration
│   └── patches/               # Clean git patches for MicroPython (Dual CDC stack)
├── lib/
│   └── micropython/           # MicroPython upstream git submodule (v1.29.0)
├── tools/                     # Standalone host CLI tools
│   ├── run_script.py          # RAM script runner via MicroPython Raw REPL
│   └── monitor_target.py      # Target UART console monitor
├── examples/                  # Target control scripts (reset, recovery, power)
└── udev/                      # Linux udev rules for persistent /dev/ symlinks
```

---

## 7. Ecosystem & Integrations

`hw-puppet` can be used directly via serial/REPL, or paired with host agent gateways (such as FastMCP servers) to enable automated troubleshooting, flashing, and diagnostics on real hardware from AI coding agents.
