"""Shared I2C master bus for the charger bench.

SDA on GPIO5, SCL on GPIO4, 100 kHz. HW Puppet reserves only GPIO43/44 for
the UART bridge, so these pins are free for anything else.
"""

from machine import I2C, Pin

SDA_PIN = 5
SCL_PIN = 4
FREQ_HZ = 100000

ADDR_PCA9536 = 0x41
ADDR_LM75B = 0x49
ADDR_LTC4162 = 0x68

_DESC = {
    ADDR_PCA9536: "PCA9536 (4-bit GPIO Expander)",
    ADDR_LM75B: "LM75B (Temperature Sensor)",
    ADDR_LTC4162: "LTC4162 (Battery Charger)",
}

_i2c = None

# The button watcher runs from a soft timer in its own task, so every bus
# transaction is serialized against the host-driven telemetry reads.
try:
    import _thread

    _lock = _thread.allocate_lock()
except ImportError:  # pragma: no cover - only if the port lacks _thread
    class _DummyLock:
        def acquire(self, waitflag=1):
            return True

        def release(self):
            pass

    _lock = _DummyLock()


def init():
    global _i2c
    if _i2c is None:
        _i2c = I2C(0, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=FREQ_HZ)
    return _i2c


def bus():
    if _i2c is None:
        init()
    return _i2c


def lock(block=True):
    return _lock.acquire(1 if block else 0)


def unlock():
    _lock.release()


def describe(addr):
    return _DESC.get(addr, "Unknown / Other Device")


def ping(addr):
    i2c = bus()
    lock()
    try:
        i2c.writeto(addr, b"")
        return True
    except OSError:
        return False
    finally:
        unlock()


def scan():
    """Return the list of 7-bit addresses answering in 0x08..0x77."""
    i2c = bus()
    lock()
    try:
        found = [a for a in i2c.scan() if 0x08 <= a <= 0x77]
    finally:
        unlock()
    return found


def read_byte(addr, reg):
    i2c = bus()
    lock()
    try:
        return i2c.readfrom_mem(addr, reg, 1)[0]
    finally:
        unlock()


def write_byte(addr, reg, val):
    i2c = bus()
    lock()
    try:
        i2c.writeto_mem(addr, reg, bytes((val & 0xFF,)))
    finally:
        unlock()


def read_word_le(addr, reg):
    """SMBus word read, little endian (LTC4162)."""
    i2c = bus()
    lock()
    try:
        b = i2c.readfrom_mem(addr, reg, 2)
    finally:
        unlock()
    return b[0] | (b[1] << 8)


def write_word_le(addr, reg, val):
    i2c = bus()
    lock()
    try:
        i2c.writeto_mem(addr, reg, bytes((val & 0xFF, (val >> 8) & 0xFF)))
    finally:
        unlock()


def read_word_be(addr, reg):
    """Word read, MSB first (LM75B)."""
    i2c = bus()
    lock()
    try:
        b = i2c.readfrom_mem(addr, reg, 2)
    finally:
        unlock()
    return (b[0] << 8) | b[1]


def write_word_be(addr, reg, val):
    i2c = bus()
    lock()
    try:
        i2c.writeto_mem(addr, reg, bytes(((val >> 8) & 0xFF, val & 0xFF)))
    finally:
        unlock()


def s16(val):
    """Reinterpret a 16-bit register value as signed."""
    return val - 0x10000 if val & 0x8000 else val


def self_test():
    """Scan the bus and report whether all three required devices answered."""
    found = scan()
    lines = ["==================== I2C BUS SCAN ===================="]
    for addr in found:
        lines.append("  -> [FOUND] 0x%02X (%3d): %s" % (addr, addr, describe(addr)))
    lines.append("Scan complete: %d device(s) found." % len(found))
    ok = True
    for addr in (ADDR_PCA9536, ADDR_LM75B, ADDR_LTC4162):
        present = addr in found
        ok = ok and present
        lines.append(
            "  - %-8s (0x%02X): [%s]"
            % (describe(addr).split(" ")[0], addr, " PASS " if present else "!FAIL!")
        )
    lines.append("======================================================")
    return ok, lines
