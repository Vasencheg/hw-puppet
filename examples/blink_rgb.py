"""
Blink onboard WS2812 RGB LED on ESP32-S3-DevKitC-1 (GPIO 48).
Cycles through Red, Green, Blue, Yellow, Cyan, Magenta, White and turns off.
"""

import time
from machine import Pin
import neopixel

LED_PIN = 48

print(f"=== [HW-PUPPET] WS2812 RGB LED Demo (GPIO {LED_PIN}) ===")

try:
    np = neopixel.NeoPixel(Pin(LED_PIN), 1)
except Exception as e:
    print(f"Error initializing NeoPixel on GPIO {LED_PIN}: {e}")
    raise

palette = [
    ("Red",     (50, 0, 0)),
    ("Green",   (0, 50, 0)),
    ("Blue",    (0, 0, 50)),
    ("Yellow",  (50, 50, 0)),
    ("Cyan",    (0, 50, 50)),
    ("Magenta", (50, 0, 50)),
    ("White",   (30, 30, 30)),
    ("Rainbow 1", (60, 20, 0)),
    ("Rainbow 2", (0, 60, 20)),
    ("Rainbow 3", (20, 0, 60)),
    ("OFF",     (0, 0, 0)),
]

for name, rgb in palette:
    print(f"-> Color: {name:10} (R={rgb[0]}, G={rgb[1]}, B={rgb[2]})")
    np[0] = rgb
    np.write()
    time.sleep(0.3)

# Smooth rainbow cycle at the end
print("-> Rainbow pulse...")
for step in range(3):
    for r, g, b in [(40, 0, 0), (40, 20, 0), (0, 40, 0), (0, 40, 40), (0, 0, 40), (40, 0, 40)]:
        np[0] = (r, g, b)
        np.write()
        time.sleep(0.08)

# Turn off
np[0] = (0, 0, 0)
np.write()
print("=== RGB LED Demo Completed! (LED turned OFF) ===")
