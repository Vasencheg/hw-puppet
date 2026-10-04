# Persistent Hardware Badge API

HW-PUPPET boards support storing a persistent **hardware badge** (identifier) directly in the ESP32-S3 non-volatile storage (**NVS**).

---

## 1. Why Hardware Badges?

In multi-board test setups or hardware-in-the-loop (HIL) racks:
- Multiple ESP32-S3 boards share identical USB Vendor/Product IDs (`0x303a:0x4002`).
- Linux assigns dynamic device nodes (`/dev/ttyACM0`, `/dev/ttyACM2`, etc.) based on USB hub enumeration order.
- Hardcoded symlinks in udev rules overwrite each other when 2+ boards are attached.

By labeling each physical HW-Puppet with a badge (e.g. `jetson-bench`, `stm32-tester`, `rack-a-slot3`), host tools like [`ae-hw-bridge`](https://github.com/Vasencheg/ae-hw-bridge) can discover and route commands to the correct hardware regardless of which USB port or hub it is plugged into.

Because badges are saved in **ESP-IDF NVS** (Non-Volatile Storage partition), the badge:
* Persists across reboots and power cycles.
* Persists even if the MicroPython filesystem (LittleFS) is formatted or cleared.
* Is readable over USB CDC 0 via standard Raw REPL RPC.

---

## 2. Firmware API (`hw_puppet`)

The `hw_puppet` built-in module provides native badge methods:

### `hw_puppet.get_badge()` / `hw_puppet.badge()`
Returns the badge name string currently stored in NVS, or `""` if no badge has been configured.

```python
import hw_puppet

badge = hw_puppet.get_badge()
print(f"Current badge: {badge}")
```

### `hw_puppet.set_badge(name: str)`
Writes a new badge name to NVS. Passing an empty string `""` clears the stored badge.

* `name`: String identifier up to 63 characters (alphanumeric, dashes, underscores recommended).
* Returns `True` on success.
* Raises `ValueError` if the name exceeds 63 characters.

```python
import hw_puppet

hw_puppet.set_badge("jetson-bench")
print("New badge:", hw_puppet.get_badge())
```

### `hw_puppet.info()`
Returns a metadata dictionary containing firmware version, git commit, build timestamp, platform, and the active badge:

```python
>>> import hw_puppet
>>> hw_puppet.info()
{
    'version': '0.3.0-dev',
    'git_hash': '729c840',
    'build_date': 'Oct  5 2026 00:50:00',
    'platform': 'ESP32-S3',
    'badge': 'jetson-bench'
}
```

---

## 3. Host CLI Management (`tools/badge.py`)

A ready-to-use host script is provided in `tools/badge.py`:

```bash
# Read badge of the connected board
./tools/badge.py --port /dev/ttyACM0

# Set badge name
./tools/badge.py --port /dev/ttyACM0 --set jetson-bench

# Clear badge
./tools/badge.py --port /dev/ttyACM0 --clear
```

---

## 4. Integration with `ae-hw-bridge`

When configured in an `ae-hw-bridge` project (`.ae-hw-bridge/config.yml`), the host gateway matches target configurations to boards by badge:

```yaml
# .ae-hw-bridge/config.yml
targets:
  jetson:
    puppet: jetson-bench
  stm32:
    puppet: stm32-tester
```

`ae-hw-bridge` automatically scans available CDC 0 ports, queries `hw_puppet.info()['badge']`, and binds each target to the right physical device without manual port mappings.
