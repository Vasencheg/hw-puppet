# `hw_puppet.uart_bridge` MicroPython API & Pattern Matcher

The `hw_puppet.uart_bridge` module is a high-performance C-extension built directly into the HW-PUPPET MicroPython firmware (`from hw_puppet import uart_bridge`). It runs a dedicated FreeRTOS task on ESP32-S3 **Core 0**, providing transparent, full-duplex forwarding between the hardware UART (`GPIO 43 TX` / `GPIO 44 RX`) and host USB CDC1 (`/dev/hw-puppet-uart`).

Simultaneously, the C engine inspects the incoming target byte stream using the **Knuth-Morris-Pratt (KMP)** algorithm in $O(1)$ time per byte with **zero dynamic heap allocations**, zero VM blocking, and zero loss of UART stream data.

---

## API Reference

### 1. `uart_bridge.on_match()`

Registers an asynchronous pattern trigger in the C engine and returns a `Match` handle.

```python
match = uart_bridge.on_match(
    pattern: str,
    callback: callable,
    reply: str | bytes = None,
    once: bool = False,
    debounce_ms: int = 100,
    case_sensitive: bool = True
) -> Match
```

#### Parameters:
- **`pattern`** (*str*, required): The ASCII substring to match in the incoming UART stream (max 64 bytes).
- **`callback`** (*callable*, required): Function called when the pattern is matched. Receives one argument: `pattern` string. Dispatched onto the MicroPython VM thread via `mp_sched_schedule`.
- **`reply`** (*str* | *bytes*, optional): String to immediately send to the target UART directly from the C task when matched (zero host roundtrip latency, max 32 bytes).
- **`once`** (*bool*, default `False`): If `True`, the trigger automatically deactivates after the first match.
- **`debounce_ms`** (*int*, default `100`): Minimum cooldown time in milliseconds between repeated callback invocations for this trigger.
- **`case_sensitive`** (*bool*, default `True`): If `False`, performs case-insensitive matching in $O(1)$ time per byte without allocations.

#### Returns:
- **`Match`**: A handle object representing the active trigger.

---

### 2. `Match` Handle Object

The `Match` object encapsulates the trigger slot in the C engine and controls its lifecycle.

#### Methods:
- **`match.cancel()`**: Disarms the trigger, frees the C trigger slot (0..7), and unroots the object from the MicroPython garbage collector.
- **`match.is_active() -> bool`**: Returns `True` if the trigger is currently armed in the C engine.

#### Context Manager:
`Match` supports Python's `with` statement for automatic cleanup:
```python
with uart_bridge.on_match("login:", on_login, once=True) as m:
    # Trigger is active inside the block
    do_something()
# Trigger is automatically cancelled on exiting block
```

---

### 3. `uart_bridge.clear_matches()`

```python
uart_bridge.clear_matches() -> None
```
Disarms and removes all currently active match triggers (up to 8 slots).

---

### 4. `uart_bridge.wait_for()` (Synchronous Helper)

```python
matched = uart_bridge.wait_for(pattern: str, reply: str = None, timeout_ms: int = 5000) -> bool
```
Blocks the calling MicroPython thread until `pattern` appears on UART or `timeout_ms` expires. Transparent USB CDC forwarding to the host is **not** interrupted during wait.

---

### 5. `uart_bridge.write()`

```python
bytes_written = uart_bridge.write(data: str | bytes) -> int
```
Transmits raw data directly to the target hardware UART.

---

### 6. Baud Rate & Bridge Lifecycle

- **`uart_bridge.set_baud(rate: int) -> bool`**: Changes target hardware UART baud rate (e.g. `115200`, `921600`).
- **`uart_bridge.get_baud() -> int`**: Returns current baud rate.
- **`uart_bridge.start() -> None`**: Starts or resumes the C bridge task.
- **`uart_bridge.stop() -> None`**: Suspends the C bridge task.

---

## Short Usage Examples

### Example 1: Basic Event Notification
```python
from hw_puppet import uart_bridge

def on_prompt(pattern):
    print(f"Target shell ready! (Matched: {pattern})")

# Register trigger
match = uart_bridge.on_match("tegra-ubuntu:", on_prompt, once=True)

# Later, or in exception cleanup:
# match.cancel()
```

---

### Example 2: Ultra-Fast U-Boot Autoboot Stop (Auto-Reply)
Immediate response in under 1 ms directly from Core 0 without waiting for Python VM scheduling:
```python
from hw_puppet import uart_bridge

def on_uboot(pattern):
    print("U-Boot autoboot intercepted!")

# When pattern is detected, C engine immediately sends '\n' to target
match = uart_bridge.on_match(
    pattern="Hit any key to stop autoboot:",
    callback=on_uboot,
    reply="\n",
    once=True
)
```

---

### Example 3: Scoped Trigger using Context Manager
```python
from hw_puppet import uart_bridge
import time

def on_panic(pattern):
    print("CRITICAL: Kernel panic during flash!")

with uart_bridge.on_match("Kernel panic", on_panic) as m:
    # Run dangerous operation
    flash_kernel_image()
    time.sleep(5)
# 'm' is automatically cancelled here
```

---

### Example 4: Multi-Pattern Boot Monitor (Warnings, Errors, Shell)
```python
from hw_puppet import uart_bridge
import time

def on_warn(p):
    print(f"[WARN] Boot warning: {p}")

def on_err(p):
    print(f"[ERR] Fatal error: {p}")

def on_ready(p):
    global ready
    ready = True
    print(f"[OK] Prompt reached: {p}")

ready = False
triggers = [
    uart_bridge.on_match("WARNING", on_warn, debounce_ms=500),
    uart_bridge.on_match("ERROR",   on_err,  debounce_ms=500),
    uart_bridge.on_match("login:",  on_ready, once=True),
]

while not ready:
    time.sleep(0.1)

# Cleanup
for t in triggers:
    t.cancel()
```

---

### Example 5: Repetitive Noise Debounce
If a target repeats a warning 100 times a second, `debounce_ms` prevents flooding the MicroPython VM queue:
```python
# Invokes callback at most once every 1000 ms, even if matched continuously
match = uart_bridge.on_match("undervoltage", on_warn, debounce_ms=1000)
```

---

## Substring Matching vs Regular Expressions (Regex)

### Why KMP Substrings Were Chosen:
1. **Deterministic Execution:** KMP guarantees $O(1)$ processing time per character. At 921,600 baud (approx. 92,000 chars/second), C-level pattern matching must not induce latency or buffer overruns in the FreeRTOS UART stream.
2. **Zero Heap Allocations:** KMP operates on static state buffers. Regular expressions typically require dynamic memory allocations, stack frames, and backtracking.
3. **No Stream Boundary Problem:** Regex engines expect fixed-size strings with a defined start and end. UART is an unbounded, infinite stream of bytes where traditional backtracking can cause catastrophic task lockups or require unbounded RAM buffering.

### Recommendations for Complex Matching:
- **Case-Insensitive Matches:** Register multiple triggers (e.g. `"warning"` and `"WARNING"`).
- **Wildcard / Group Extraction:** Use `uart_bridge.on_match()` as a fast hardware filter on an anchor prefix (e.g. `"IP-ADDR:"`). Inside the Python callback, inspect the incoming line and use MicroPython's `re` module (`import ure`) to extract variable parts (e.g. IP addresses or numbers).
