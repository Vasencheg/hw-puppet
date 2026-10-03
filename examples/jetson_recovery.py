"""
Scenario: Put NVIDIA Jetson into Force Recovery (RCM) mode.
Hardware wiring:
- GPIO 11: Jetson FORCE RECOVERY (active LOW relay)
- GPIO 12: Jetson RESET (active LOW relay)

Sequence:
1. Ensure both relays are OFF (unenergized / open).
2. Energize Recovery relay (connects FC_REC to GND).
3. Wait 0.5s.
4. Pulse Reset relay (connects SYS_RST to GND for 0.5s, then release).
5. Wait 1.0s for Tegra to latch RCM strap pins.
6. De-energize Recovery relay (release FC_REC).
"""

import time
from machine import Pin

PIN_REC = 11    # Force Recovery relay pin
PIN_RST = 12    # System Reset relay pin

# Active LOW relay logic: 0 = energized (closed), 1 = off (open)
RELAY_ON = 0
RELAY_OFF = 1

print("=== [HW-PUPPET] NVIDIA Jetson Force Recovery Sequence ===")

# Initialize both pins as outputs in OFF state (open)
relay_rec = Pin(PIN_REC, Pin.OUT, value=RELAY_OFF)
relay_rst = Pin(PIN_RST, Pin.OUT, value=RELAY_OFF)
time.sleep(0.5)

# Step 1: Hold Force Recovery
print("-> 1. Holding FORCE RECOVERY (GPIO 11 -> GND)...")
relay_rec.value(RELAY_ON)
time.sleep(0.5)

# Step 2: Pulse Reset
print("-> 2. Triggering RESET pulse (GPIO 12 -> GND, 500ms)...")
relay_rst.value(RELAY_ON)
time.sleep(0.5)
relay_rst.value(RELAY_OFF)
print("->    RESET released.")

# Step 3: Hold Recovery while Tegra samples straps
print("-> 3. Latching RCM mode (waiting 1.0s)...")
time.sleep(1.0)

# Step 4: Release Force Recovery
print("-> 4. Releasing FORCE RECOVERY (GPIO 11 opened)...")
relay_rec.value(RELAY_OFF)

print("\n=== Sequence complete: Jetson should now be in Force Recovery (APX) mode ===")
