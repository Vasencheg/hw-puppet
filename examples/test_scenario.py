"""
Example automation scenario for HW-PUPPET.
This script is sent by the host via `run_script.py` and executed
directly in ESP32-S3 RAM without touching Flash memory.
"""

import time
from machine import Pin
import hw_puppet
from hw_puppet import uart_bridge

print(f"=== [HW-PUPPET v{hw_puppet.__version__}] Running Test Scenario ===")
print(f"Platform info: {hw_puppet.info()}")

# 1. Configure hardware UART bridge baudrate
print(f"Current UART bridge baudrate: {uart_bridge.get_baud()} baud")
print("Setting baudrate to 115200 baud...")
uart_bridge.set_baud(115200)
print(f"New UART bridge baudrate: {uart_bridge.get_baud()} baud")

# 2. Control target power / control lines
# Example: pin 4 - RESET, pin 5 - BOOT
PIN_RESET = 4
PIN_BOOT = 5

boot_pin = Pin(PIN_BOOT, Pin.OUT, value=1)
rst_pin = Pin(PIN_RESET, Pin.OUT, value=1)

print(f"\n1. Putting target into normal run mode:")
print(f"   - Setting BOOT (GPIO {PIN_BOOT}) HIGH...")
boot_pin.value(1)

print(f"   - Sending active RESET pulse (GPIO {PIN_RESET}, 50 ms)...")
rst_pin.value(0)
time.sleep_ms(50)
rst_pin.value(1)
print("   - Reset completed!")

# 3. Wait for target to boot
print("\n2. Waiting for target boot (2 sec)...")
for i in range(1, 3):
    time.sleep(1)
    print(f"   ...elapsed {i} sec.")

# 4. Check pin state
val = rst_pin.value()
print(f"\n3. Current RESET pin state: {val}")

print("\n=== Scenario finished successfully! ===")
