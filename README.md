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
* **On-Device Hardware Pattern Matcher:** Real-time C-level pattern detection and microsecond-level auto-reply directly on Core 0 (`uart_bridge.wait_for`, `uart_bridge.arm_match`).
* **Completely Framework-Agnostic:** Works with any language, `pytest`, bash scripts, `minicom`/`tio`, CI/CD pipelines, or agentic tool frameworks (MCP).

---

## 2. Device Naming & Identifiers

To avoid confusion across tools, build scripts, USB descriptors, and udev rules, the project uses the following standardized naming conventions:

| Context / Layer | Identifier / Variation | Description |
|:---|:---|:---|
| **Human-Readable Name** | **HW Puppet** / **HWPuppet** | Official project and hardware harness title |
| **Repository & CLI** | `hw-puppet` | Git repository name, folder naming, command prefix |
| **Firmware Board Target** | `HW_PUPPET` | MicroPython CMake board name (`BOARD=HW_PUPPET`), folder `firmware/boards/HW_PUPPET/` |
| **USB Manufacturer** | `HW-Puppet` | USB Device Descriptor manufacturer string (`0x303a:0x4002`) |
| **USB Product Name** | `HW-PUPPET` | USB Device Descriptor product string |
| **USB CDC 0 Interface** | `HW-PUPPET REPL` | Primary control & MicroPython Raw REPL interface string |
| **USB CDC 1 Interface** | `HW-PUPPET UART Bridge` | Secondary high-speed UART console stream interface string |
| **Linux Udev Control Node** | `/dev/hw-puppet-control` | Stable symlink to CDC 0 (symlinked to `/dev/ttyACM0`) |
| **Linux Udev UART Node** | `/dev/hw-puppet-uart` | Stable symlink to CDC 1 (symlinked to `/dev/ttyACM1`) |
| **Python / C Packages** | `hw_puppet`, `hw_puppet.uart_bridge` | Root namespace package (`import hw_puppet`) and bridge submodule |

---

## 3. Supported Hardware & Platform

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

## 4. Pinout & Hardware Connections

### ESP32-S3 Pin Mapping (Default)
The firmware reserves only the hardware UART peripheral lines for the transparent console bridge. All other GPIO pins remain completely free and dynamically configurable via standard MicroPython `machine.Pin`:

| ESP32-S3 Pin | Function | Target / DUT Connection | Description |
|:---|:---|:---|:---|
| **GPIO 43** | UART1 TX | Target RX | Serial command TX to target console (115200..921600 baud) |
| **GPIO 44** | UART1 RX | Target TX | Serial log RX from target console (115200..921600 baud) |
| **GND** | Ground | Target GND | Common reference ground (**mandatory**) |

> [!NOTE]
> All other ESP32-S3 pins (relays, reset lines, recovery/boot mode, power switches, I2C, SPI) are controlled dynamically from host scripts or target modules without firmware recompilation.

> [!WARNING]
> **Target Logic Voltage Compatibility (3.3V vs 1.8V vs 5V):**
> - **Native 3.3V I/O:** ESP32-S3 GPIO pins (including UART TX/RX) operate at **3.3V LVCMOS** logic levels and are **NOT 5V tolerant**.
> - **1.8V Targets (e.g. Jetson raw SoC headers, FPGAs, mobile SoCs):** Connecting 3.3V directly to 1.8V I/O pins will permanently damage the target SoC! Always verify target debug UART voltage and use a bidirectional logic level shifter (e.g. TXS0108 / PCA9306) or 1.8V-buffered debug header.
> - **5V Targets:** Require level shifting (e.g. resistive divider or buffer on RX) to protect ESP32-S3 inputs from overvoltage.
> - **Relay Isolation:** Using onboard dry-contact relays for RESET, RECOVERY, and POWER lines provides galvanic isolation, making relay-based control safe regardless of target voltage levels.

---

## 5. On-Device UART Pattern Matcher & Auto-Reply

To eliminate the 10–50 ms USB-roundtrip latency when synchronizing with target boot sequences (e.g. stopping U-Boot autoboot in a 1-second window), `hw-puppet` implements an **on-the-fly streaming KMP matcher** in native C on Core 0.

Bytes from UART1 RX are checked in $O(1)$ time without interrupting transparent streaming to USB CDC 1.

```python
import hw_puppet
from hw_puppet import uart_bridge

# Inspect platform version and build info:
print(f"HW-PUPPET: v{hw_puppet.__version__}")
print(hw_puppet.info())

# 1. Catch bootloader prompt and auto-reply with a space within microseconds:
if uart_bridge.wait_for("Hit any key to stop autoboot", reply=" ", timeout_ms=5000):
    print("Autoboot interrupted successfully on-device!")

# 2. Wait for login prompt with timeout:
if uart_bridge.wait_for("login:", timeout_ms=15000):
    print("Target reached login prompt")

# 3. Direct UART transmission:
uart_bridge.write(b"root\n")
```

---

## 6. Quickstart

### 6.1 Install Udev Rules (Linux)
Install udev rules to get persistent, human-readable symlinks:
```bash
./build.sh install-rules
```
This registers:
* `/dev/hw-puppet-control` -> CDC 0 (MicroPython REPL)
* `/dev/hw-puppet-uart` -> CDC 1 (Target UART console)

### 6.2 Flash Pre-built Firmware
Connect the ESP32-S3 USB port in download mode (hold BOOT, tap RESET, release BOOT):
```bash
esptool.py -p /dev/ttyACM0 -b 460800 write_flash 0x0 build/firmware.bin
```

### 6.3 Monitor Target Console
Open CDC 1 to see target boot logs:
```bash
./tools/monitor_target.py
# Or with any serial terminal:
tio /dev/hw-puppet-uart
```

### 6.4 Execute Control Scripts on the Board
Run Python scripts directly on the ESP32-S3 in RAM (no flash wear):
```bash
./tools/run_script.py examples/jetson_reset.py
./tools/run_script.py examples/jetson_recovery.py
```

---

## 7. Building Firmware from Source

### Prerequisites
* ESP-IDF v5.4+ installed and activated (`. $IDF_PATH/export.sh` or `get_idf`)
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

## 8. Repository Structure

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

## 9. Ecosystem & Integrations

While `hw-puppet` functions completely standalone via raw REPL, Python scripts, or terminal emulators (`tio`, `minicom`), it is engineered as the core hardware execution engine for the [**`ae-hw-bridge`**](https://github.com/Vasencheg/ae-hw-bridge) (Agents Engine Hardware Bridge) ecosystem.

### Pairing with `ae-hw-bridge` (FastMCP Gateway)

[**`ae-hw-bridge`**](https://github.com/Vasencheg/ae-hw-bridge) is the official host agent gateway and FastMCP server for `hw-puppet`:

* **Single-Owner Host Daemon (`ae-hw-bridge-daemon`):** Prevents serial port contention by owning `/dev/hw-puppet-control` and `/dev/hw-puppet-uart`. Multiple CLI clients, test suites, and AI agent sessions connect concurrently over non-blocking Unix domain socket IPC (`/tmp/ae-hw-bridge.sock`).
* **Model Context Protocol (MCP) Interface:** Exposes vetted, high-level automation tools (`send_target_command`, `read_target_console`, `wait_for_console_pattern`, `full_reboot`, `enter_recovery`) directly to AI coding agents (Claude Desktop, Gemini, Cursor, OpenCode, Agents Engine).
* **Dynamic Target Modules (`.ae-hw-bridge/targets/`):** Define DUT-specific behaviors (pin mappings, reset timings, boot patterns, and login credentials) in Python without modifying the base firmware.
* **Onboard WS2812 Visual Telemetry:** Real-time visual feedback on the ESP32-S3 RGB LED indicating current DUT state (flashing, recovery, rebooting, console ready).

```bash
# Install host gateway
pip install ae-hw-bridge

# Launch MCP server for agents
ae-hw-bridge-mcp
```
