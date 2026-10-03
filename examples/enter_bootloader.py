"""
Scenario: put target (ESP32/ESP8266 etc.) into ROM Bootloader mode.
Executes directly in HW-PUPPET RAM via Raw REPL.
"""

import time
from machine import Pin

PIN_RESET = 4  # Target EN/RST reset pin
PIN_BOOT = 5   # Target BOOT/IO0 mode selection pin

print("=== [HW-PUPPET] Entering Target ROM Bootloader Mode ===")

boot_pin = Pin(PIN_BOOT, Pin.OUT, value=1)
rst_pin = Pin(PIN_RESET, Pin.OUT, value=1)

# 1. Pull BOOT to ground (LOW)
print(f"-> Setting BOOT (GPIO {PIN_BOOT}) to 0...")
boot_pin.value(0)
time.sleep(0.05)

# 2. Trigger active reset pulse (active LOW)
print(f"-> Triggering RESET pulse (GPIO {PIN_RESET}, 100 ms)...")
rst_pin.value(0)
time.sleep(0.1)
rst_pin.value(1)

# 3. Target is now in ROM Bootloader mode, release BOOT high
time.sleep(0.1)
boot_pin.value(1)

print("-> Done! Target is in Bootloader mode.")
print("   Target can now be flashed via secondary port (/dev/hw-puppet-uart or /dev/ttyACM1).")
