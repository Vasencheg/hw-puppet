"""
Scenario: Hardware reset NVIDIA Jetson into normal boot mode.
Hardware wiring:
- GPIO 11: Jetson FORCE RECOVERY (held open / unenergized)
- GPIO 12: Jetson RESET (active LOW relay)

Sequence:
1. Ensure Force Recovery relay is OFF (open / unenergized).
2. Pulse Reset relay (connects SYS_RST to GND for 500ms, then release).
3. Jetson boots into standard Linux (L4T) mode.
"""

import time
from machine import Pin

PIN_REC = 11    # Force Recovery relay pin
PIN_RST = 12    # System Reset relay pin

# Active LOW relay logic: 0 = energized (closed), 1 = off (open)
RELAY_ON = 0
RELAY_OFF = 1

print("=== [HW-PUPPET] NVIDIA Jetson Hardware Reset ===")

# 1. Ensure Recovery is open (released)
relay_rec = Pin(PIN_REC, Pin.OUT, value=RELAY_OFF)
relay_rst = Pin(PIN_RST, Pin.OUT, value=RELAY_OFF)
time.sleep(0.1)

# 2. Trigger Reset pulse
print("-> Triggering RESET pulse (GPIO 12 -> GND, 500ms)...")
relay_rst.value(RELAY_ON)
time.sleep(0.5)
relay_rst.value(RELAY_OFF)

print("-> RESET released.")
print("\n=== Reset complete: Jetson is booting normally ===")
