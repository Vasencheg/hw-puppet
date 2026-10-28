"""LM75B board temperature sensor, address 0x49."""

from . import i2cbus

ADDR = 0x49

REG_TEMP = 0x00
REG_CONF = 0x01
REG_THYST = 0x02
REG_TOS = 0x03

CONF_SHUTDOWN = 1 << 0
CONF_OS_INT_MODE = 1 << 1
CONF_OS_POL_HIGH = 1 << 2
CONF_FAULT_QUEUE_MASK = 0x03 << 3


def init():
    """Make sure the sensor is not in shutdown mode."""
    write_conf(0x00)


def read_temp():
    """Temperature in degrees Celsius, 0.125 degC resolution."""
    raw = i2cbus.read_word_be(ADDR, REG_TEMP)
    # D10..D0 live in bits [15:5] as an 11-bit two's complement value.
    return (i2cbus.s16(raw) >> 5) * 0.125


def read_conf():
    return i2cbus.read_byte(ADDR, REG_CONF)


def write_conf(conf):
    i2cbus.write_byte(ADDR, REG_CONF, conf)


def self_test():
    """Ping, verify CONF register R/W, check the reading is plausible."""
    lines = ["Starting LM75B self-test (addr 0x%02X)..." % ADDR]
    if not i2cbus.ping(ADDR):
        lines.append("FAIL: LM75B not acknowledging on I2C bus")
        return False, None, lines

    try:
        orig_conf = read_conf()
        test_conf = orig_conf ^ (0x03 << 3)
        write_conf(test_conf)
        readback = read_conf()
        write_conf(orig_conf)
    except OSError as err:
        lines.append("FAIL: CONF register access error: %s" % err)
        return False, None, lines

    if readback != test_conf:
        lines.append(
            "FAIL: CONF register R/W mismatch (wrote 0x%02X, read 0x%02X)"
            % (test_conf, readback)
        )
        return False, None, lines

    try:
        temp = read_temp()
    except OSError as err:
        lines.append("FAIL: Could not read temperature: %s" % err)
        return False, None, lines

    if temp < -20.0 or temp > 85.0:
        lines.append("FAIL: Temperature reading out of bounds: %.2f C" % temp)
        return False, temp, lines

    lines.append("PASS: LM75B verified OK. Current Temperature: %.2f C" % temp)
    return True, temp, lines
