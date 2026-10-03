"""
HW-PUPPET REPL Script:
1. Reboots the target board (Jetson) via hardware RESET relay (GPIO 12).
2. Sets WS2812 RGB LED (GPIO 48) status:
   - BLUE: Hardware Reset pulse active
   - ORANGE: Target booting (normal stream)
   - YELLOW: Warning detected in console stream ("warn", "warning")
   - RED: Error detected in console stream ("error", "failed", "panic", "fault")
   - GREEN: Prompt / Ready reached ("login:", "tegra-ubuntu", "$", "#")
3. Live-streams console output to REPL stdout.
4. Restores UART bridge on completion.

Run on board via:
    python3 tools/run_script.py examples/boot_watch_rgb.py
"""

import sys
import time
from machine import Pin, UART
import neopixel
import uart_bridge

# --- Pin Configuration ---
PIN_REC = 11   # Target RECOVERY relay (active LOW: 0=closed, 1=open)
PIN_RST = 12   # Target RESET relay (active LOW: 0=closed, 1=open)
PIN_LED = 48   # Onboard WS2812 RGB LED
UART_TX = 43
UART_RX = 44
BAUDRATE = 115200

# --- RGB Color Palette (R, G, B) ---
COLOR_OFF    = (0, 0, 0)
COLOR_RESET  = (0, 0, 50)   # Blue: Reset pulse
COLOR_BOOT   = (25, 10, 0)  # Dim Orange: Boot in progress
COLOR_WARN   = (50, 35, 0)  # Yellow: Warning detected
COLOR_ERR    = (60, 0, 0)   # Red: Error / Panic detected
COLOR_READY  = (0, 60, 0)   # Green: Prompt ready / logged in

# Target ready prompt patterns
PROMPT_PATTERNS = ["login:", "tegra-ubuntu", "$ ", "# "]
# Error patterns
ERROR_PATTERNS = ["error", "panic", "failed", "fail", "fault", "fatal"]
# Warning patterns
WARN_PATTERNS = ["warning", "warn"]

print("==================================================")
print("  HW-PUPPET: Reboot & Visual Boot Stream Monitor  ")
print("==================================================")

# 1. Initialize hardware lines & RGB LED
np = neopixel.NeoPixel(Pin(PIN_LED), 1)
relay_rec = Pin(PIN_REC, Pin.OUT, value=1)  # Ensure Recovery is unasserted
relay_rst = Pin(PIN_RST, Pin.OUT, value=1)  # Released

def set_led(color):
    np[0] = color
    np.write()

# 2. Stop background bridge task so MicroPython controls UART1
uart_bridge.stop()
time.sleep(0.05)

u = UART(1, baudrate=BAUDRATE, tx=UART_TX, rx=UART_RX, rxbuf=4096)

try:
    # 3. Trigger hardware reset pulse
    print("-> Triggering RESET pulse (GPIO 12 -> 0, 500 ms)...")
    set_led(COLOR_RESET)
    relay_rst.value(0)
    time.sleep(0.5)
    relay_rst.value(1)
    print("-> RESET released. Jetson is booting...")
    set_led(COLOR_BOOT)

    # 4. Monitor UART stream in real-time
    start_time = time.time()
    TIMEOUT_SEC = 60
    current_color = COLOR_BOOT
    temp_color_deadline = 0

    buf = b""
    boot_complete = False

    while (time.time() - start_time) < TIMEOUT_SEC:
        # Check if temporary warning/error color duration expired
        now = time.ticks_ms()
        if temp_color_deadline and time.ticks_diff(now, temp_color_deadline) >= 0:
            set_led(COLOR_BOOT)
            temp_color_deadline = 0

        # Read available bytes from UART
        if u.any():
            chunk = u.read(u.any())
            if chunk:
                # Forward to stdout so host sees the logs
                try:
                    sys.stdout.write(chunk.decode("utf-8", "replace"))
                except Exception:
                    pass

                buf += chunk
                while b"\n" in buf:
                    line_raw, buf = buf.split(b"\n", 1)
                    line_str = line_raw.decode("utf-8", "replace").lower()

                    # 1. Check Prompt / Ready condition
                    if any(p in line_str for p in PROMPT_PATTERNS):
                        set_led(COLOR_READY)
                        print("\n\n>>> [HW-PUPPET] PROMPT DETECTED! Boot completed successfully. <<<")
                        boot_complete = True
                        break

                    # 2. Check Errors -> RED
                    if any(e in line_str for e in ERROR_PATTERNS):
                        set_led(COLOR_ERR)
                        temp_color_deadline = time.ticks_add(time.ticks_ms(), 800)  # Hold red for 800ms

                    # 3. Check Warnings -> YELLOW (if not currently red)
                    elif any(w in line_str for w in WARN_PATTERNS):
                        if not temp_color_deadline:  # Don't overwrite red
                            set_led(COLOR_WARN)
                            temp_color_deadline = time.ticks_add(time.ticks_ms(), 500)  # Hold yellow for 500ms

            if boot_complete:
                break
        else:
            time.sleep_ms(10)

    if not boot_complete:
        set_led(COLOR_ERR)
        print("\n\n>>> [HW-PUPPET] TIMEOUT: Did not reach shell prompt within timeout! <<<")

finally:
    # 5. Clean up UART and restore background CDC1 bridge
    u.deinit()
    uart_bridge.start()
    print("-> Hardware bridge restored. LED status held.")
