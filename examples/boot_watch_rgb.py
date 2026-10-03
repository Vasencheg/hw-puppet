"""
HW-PUPPET: Simple REPL Boot Watcher
Reboots target via relay, uses uart_bridge.on_match() to monitor boot stream,
and reflects status on onboard WS2812 RGB LED:
- Stays dark (OFF) during normal boot
- Flashes YELLOW (200ms) on warnings
- Flashes RED (250ms) on errors
- Turns GREEN when ready prompt is reached
"""

import time
from machine import Pin
import neopixel
import uart_bridge

# --- Configuration & Palette ---
PIN_RST = 12   # Jetson Reset relay (active LOW: 0=closed, 1=open)
PIN_LED = 48   # Onboard WS2812 RGB LED

COLOR_OFF   = (0, 0, 0)
COLOR_RESET = (0, 0, 10)   # Dim Blue: Reset pulse active
COLOR_WARN  = (12, 7, 0)   # Dim Yellow: Warning quick flash
COLOR_ERR   = (15, 0, 0)   # Dim Red: Error quick flash
COLOR_READY = (0, 15, 0)   # Dim Green: Shell / Login prompt ready

np = neopixel.NeoPixel(Pin(PIN_LED), 1)
relay_rst = Pin(PIN_RST, Pin.OUT, value=1)

def set_led(color):
    np[0] = color
    np.write()

# --- State & Callbacks ---
boot_done = False
alert_until = 0

def on_warning(pattern):
    global alert_until
    print(f">>> [WARNING] Matched '{pattern}' -> Flash YELLOW (200ms)")
    alert_until = time.ticks_add(time.ticks_ms(), 200)
    set_led(COLOR_WARN)

def on_error(pattern):
    global alert_until
    print(f">>> [ERROR] Matched '{pattern}' -> Flash RED (250ms)")
    alert_until = time.ticks_add(time.ticks_ms(), 250)
    set_led(COLOR_ERR)

def on_ready(pattern):
    global boot_done
    print(f"\n==================================================")
    print(f">>> [READY] Prompt matched '{pattern}' -> GREEN! <<<")
    print(f"==================================================")
    set_led(COLOR_READY)
    boot_done = True

# --- 1. Reset Target ---
print("-> Resetting target via relay (0.5s)...")
set_led(COLOR_RESET)
relay_rst.value(0)
time.sleep(0.5)
relay_rst.value(1)

print("-> Target released. Watching for events (LED is dark during silent boot)...")
set_led(COLOR_OFF)

# --- 2. Register Triggers (Case-Insensitive) ---
m_warn   = uart_bridge.on_match("warning",      on_warning, debounce_ms=300, case_sensitive=False)
m_err1   = uart_bridge.on_match("error",        on_error,   debounce_ms=350, case_sensitive=False)
m_err2   = uart_bridge.on_match("panic",        on_error,   debounce_ms=350, case_sensitive=False)
m_ready1 = uart_bridge.on_match("login:",       on_ready,   once=True,       case_sensitive=False)
m_ready2 = uart_bridge.on_match("tegra-ubuntu", on_ready,   once=True,       case_sensitive=False)

# --- 3. Watch Loop ---
deadline = time.ticks_add(time.ticks_ms(), 75000)

while not boot_done:
    now = time.ticks_ms()
    if time.ticks_diff(now, deadline) >= 0:
        print(">>> [TIMEOUT] Boot took longer than 75s!")
        set_led(COLOR_ERR)
        break

    # Turn off LED after temporary alert flash expires
    if alert_until and time.ticks_diff(now, alert_until) >= 0:
        alert_until = 0
        set_led(COLOR_OFF)

    time.sleep_ms(20)

# If successfully booted, hold GREEN
if boot_done:
    set_led(COLOR_READY)

# --- 4. Cleanup ---
m_warn.cancel()
m_err1.cancel()
m_err2.cancel()
m_ready1.cancel()
m_ready2.cancel()

print("-> Watcher completed.")
