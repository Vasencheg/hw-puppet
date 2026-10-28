"""PCA9536 4-bit GPIO expander, address 0x41.

Pin assignment on the example board:
  IO0 - output, indicator LED power enable
  IO1 - input, external button (active low)
  IO2 - input, unused
  IO3 - input, SIM card detect switch (active low)
"""

from . import i2cbus

ADDR = 0x41

REG_INPUT = 0x00
REG_OUTPUT = 0x01
REG_POLARITY = 0x02
REG_CONFIG = 0x03

PIN_LED_PWR_EN = 1 << 0
PIN_EXT_BTN = 1 << 1
PIN_NC = 1 << 2
PIN_SIM_ON = 1 << 3

# Mirrors the state last written to IO0: the expander has no readback for it.
_led_state = False


def init():
    """IO0 as output driven low, IO1/IO2/IO3 as inputs, no polarity inversion."""
    global _led_state
    i2cbus.write_byte(ADDR, REG_OUTPUT, 0x00)
    i2cbus.write_byte(ADDR, REG_POLARITY, 0x00)
    i2cbus.write_byte(ADDR, REG_CONFIG, PIN_EXT_BTN | PIN_NC | PIN_SIM_ON)
    _led_state = False


def set_led_pwr(enable):
    global _led_state
    out = i2cbus.read_byte(ADDR, REG_OUTPUT)
    if enable:
        out |= PIN_LED_PWR_EN
    else:
        out &= ~PIN_LED_PWR_EN & 0xFF
    i2cbus.write_byte(ADDR, REG_OUTPUT, out)
    _led_state = bool(enable)


def led_pwr_state():
    return _led_state


def read_raw():
    return i2cbus.read_byte(ADDR, REG_INPUT)


def read_inputs():
    """Return (btn_pressed, sim_present). Both lines are active low."""
    val = read_raw()
    return (val & PIN_EXT_BTN) == 0, (val & PIN_SIM_ON) == 0


def self_test():
    lines = ["Starting PCA9536 self-test (addr 0x%02X)..." % ADDR]
    if not i2cbus.ping(ADDR):
        lines.append("FAIL: PCA9536 not acknowledging on I2C bus")
        return False, lines

    try:
        orig_pol = i2cbus.read_byte(ADDR, REG_POLARITY)
        test_pattern = 0x0A  # lower 4 bits are writable
        i2cbus.write_byte(ADDR, REG_POLARITY, test_pattern)
        readback = i2cbus.read_byte(ADDR, REG_POLARITY)
        i2cbus.write_byte(ADDR, REG_POLARITY, orig_pol)
    except OSError as err:
        lines.append("FAIL: POLARITY register access error: %s" % err)
        return False, lines

    if (readback & 0x0F) != test_pattern:
        lines.append(
            "FAIL: POLARITY register R/W mismatch (wrote 0x%02X, read 0x%02X)"
            % (test_pattern, readback & 0x0F)
        )
        return False, lines

    try:
        init()
        btn, sim = read_inputs()
        # Output toggle test: pulse LED_PWR_EN and put it back.
        set_led_pwr(True)
        set_led_pwr(False)
    except OSError as err:
        lines.append("FAIL: I/O configuration error: %s" % err)
        return False, lines

    lines.append(
        "PASS: PCA9536 verified OK. Inputs state: EXT_BTN=%d, SIM_ON=%d" % (btn, sim)
    )
    return True, lines
