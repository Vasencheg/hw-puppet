"""
Test script for controlling 4-channel relay module (pins 11, 12, 13, 14).
Each pin is toggled sequentially for 0.5 seconds.

Run with launcher:
python3 tools/run_script.py examples/relay_test.py --port /dev/ttyACM0
"""

import time
from machine import Pin

# Relay GPIO pins
RELAY_PINS = [11, 12, 13, 14]

# Active LOW relay logic:
RELAY_ON = 0
RELAY_OFF = 1

print("=== [HW-PUPPET] Relay Switching Test (GPIO 11-14) ===")
print(f"Active level: {'HIGH (1)' if RELAY_ON == 1 else 'LOW (0)'}")

# Initialize all pins as outputs in OFF state
relays = {}
for pin_num in RELAY_PINS:
    p = Pin(pin_num, Pin.OUT)
    p.value(RELAY_OFF)
    relays[pin_num] = p

print("All relays initialized and turned OFF.\n")
time.sleep(0.5)

# Sequentially energize each relay for 0.5s
for pin_num in RELAY_PINS:
    p = relays[pin_num]
    print(f"-> Turning ON relay at GPIO {pin_num}...")
    p.value(RELAY_ON)
    time.sleep(0.5)

    print(f"   Turning OFF relay at GPIO {pin_num}.")
    p.value(RELAY_OFF)
    time.sleep(0.2)

print("\n=== Test complete: all relays verified and turned OFF ===")
