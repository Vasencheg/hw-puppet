"""LTC4162-L battery charger, address 0x68.

Scaling constants and register semantics follow the LTC4162-L datasheet. The
sense resistor values below describe the example bench; change them to match
your own board.
"""

from . import i2cbus

ADDR = 0x68

RSNSB_OHMS = 0.016  # 16 mR, battery charge current sense
RSNI_OHMS = 0.007   # 7 mR, input current limit sense
DEFAULT_CELLS = 4   # 4S Li-Ion pack

REG_CONFIG = 0x14
REG_ARM_SHIP_MODE = 0x19
REG_ICHARGE_DAC = 0x1A
REG_ICHARGE_JEITA_6_5 = 0x27
REG_ICHARGE_JEITA_4_3_2 = 0x28
REG_CHARGER_CONFIG = 0x29
REG_CHARGER_STATE = 0x34
REG_CHARGE_STATUS = 0x35
REG_SYSTEM_STATUS = 0x39
REG_VBAT = 0x3A
REG_VIN = 0x3B
REG_VOUT = 0x3C
REG_IBAT = 0x3D
REG_IIN = 0x3E
REG_DIE_TEMP = 0x3F
REG_CHEM_CELLS = 0x43
REG_TELEMETRY_STATUS = 0x4A

# Ship Mode magic constant ('S' 'M' -> 0x534D)
ARM_SHIP_MODE_MAGIC = 0x534D

# charger_config_bits (reg 0x29), reset value 1
CC_EN_C_OVER_X_TERM = 0x0004
CC_EN_JEITA = 0x0001

# Reset values of the JEITA charge current registers (datasheet defaults).
# 0x27: icharge_jeita_6 = icharge_jeita_5 = 15 (C/2)
# 0x28: icharge_jeita_4 = icharge_jeita_3 = 31 (full scale), icharge_jeita_2 = 15 (C/2)
ICHARGE_JEITA_6_5_RESET = 495
ICHARGE_JEITA_4_3_2_RESET = 32751

# charger_state (reg 0x34), mutually exclusive bits
CS_BAT_DETECT_FAILED = 0x1000
CS_BATTERY_DETECTION = 0x0800
CS_CHARGER_SUSPENDED = 0x0100
CS_PRECHARGE = 0x0080
CS_CC_CV_CHARGE = 0x0040
CS_NTC_PAUSE = 0x0020
CS_TIMER_TERM = 0x0010
CS_C_OVER_X_TERM = 0x0008
CS_MAX_CHARGE_TIME_FLT = 0x0004
CS_BAT_MISSING_FAULT = 0x0002
CS_BAT_SHORT_FAULT = 0x0001

# charge_status (reg 0x35), active only in charging states
CHS_ILIM_REG_ACTIVE = 0x0020
CHS_THERMAL_REG_ACTIVE = 0x0010
CHS_VIN_UVCL_ACTIVE = 0x0008
CHS_IIN_LIMIT_ACTIVE = 0x0004
CHS_CONSTANT_CURRENT = 0x0002
CHS_CONSTANT_VOLTAGE = 0x0001

# system_status (reg 0x39)
SS_EN_CHG = 0x0100
SS_CELL_COUNT_ERR = 0x0080
SS_NO_RT = 0x0020
SS_THERMAL_SHUTDOWN = 0x0010
SS_VIN_OVLO = 0x0008
SS_VIN_GT_VBAT = 0x0004
SS_VIN_GT_4P2V = 0x0002
SS_INTVCC_GT_2P8V = 0x0001

_CHARGER_STATE_STR = {
    CS_BAT_DETECT_FAILED: "BATTERY DETECTION FAILED (fault)",
    CS_BATTERY_DETECTION: "BATTERY DETECTION IN PROGRESS",
    CS_CHARGER_SUSPENDED: "CHARGER SUSPENDED / NO INPUT",
    CS_PRECHARGE: "PRECHARGE (low battery)",
    CS_CC_CV_CHARGE: "CC/CV CHARGING",
    CS_NTC_PAUSE: "PAUSED ON NTC TEMPERATURE",
    CS_TIMER_TERM: "TERMINATED BY TIMER (charged)",
    CS_C_OVER_X_TERM: "TERMINATED BY C/x (charged)",
    CS_MAX_CHARGE_TIME_FLT: "MAX CHARGE TIME FAULT",
    CS_BAT_MISSING_FAULT: "BATTERY MISSING (fault)",
    CS_BAT_SHORT_FAULT: "BATTERY SHORTED (fault)",
    0: "IDLE (no state bit set)",
}

_CHARGER_STATE_SHORT = {
    CS_BAT_DETECT_FAILED: "DETFAIL",
    CS_BATTERY_DETECTION: "BATDET ",
    CS_CHARGER_SUSPENDED: "SUSPEND",
    CS_PRECHARGE: "PRECHG ",
    CS_CC_CV_CHARGE: "CC/CV  ",
    CS_NTC_PAUSE: "NTCPAUS",
    CS_TIMER_TERM: "TMRTERM",
    CS_C_OVER_X_TERM: "C/X-END",
    CS_MAX_CHARGE_TIME_FLT: "MAXTIME",
    CS_BAT_MISSING_FAULT: "NO BATT",
    CS_BAT_SHORT_FAULT: "BATSHRT",
    0: "IDLE   ",
}

_CHARGE_STATUS_STR = {
    CHS_ILIM_REG_ACTIVE: "ILIM REGULATION ACTIVE",
    CHS_THERMAL_REG_ACTIVE: "THERMAL REGULATION ACTIVE",
    CHS_VIN_UVCL_ACTIVE: "VIN UNDERVOLTAGE LIMIT ACTIVE",
    CHS_IIN_LIMIT_ACTIVE: "INPUT CURRENT LIMIT ACTIVE",
    CHS_CONSTANT_CURRENT: "CONSTANT CURRENT",
    CHS_CONSTANT_VOLTAGE: "CONSTANT VOLTAGE",
    0: "CHARGER OFF",
}

# Last requested adaptive-JEITA setpoint. The LTC4162 loses every register
# setting across a ship mode cycle (datasheet Rev A, p.28: "no settings or
# state information will persist through a ship mode cycle") and HW Puppet is
# USB powered, so it does not reboot together with the board under test and
# init() never runs again by itself. ensure_configured() replays these.
_jeita_max_ilim = 0.0
_jeita_rsnsb = 0.0

# Desired en_jeita state (reg 0x29 bit 0). Its reset value is 1, so a request
# to turn JEITA off has to be replayed after a ship cycle as well. None means
# the user has not asked for anything and the chip default is left alone.
_jeita_enable_req = None


def read_reg(reg):
    return i2cbus.read_word_le(ADDR, reg)


def write_reg(reg, data):
    i2cbus.write_word_le(ADDR, reg, data)


def init():
    """Configure telemetry.

    Reg 0x19 is not touched here: it does not survive a ship mode cycle anyway
    (datasheet p.28), so clearing it on startup achieves nothing. Waking a board
    back up from ship mode is a hardware matter, not a register write.

    Reg 0x14 bit 2 = force_telemetry_on: "Causes the telemetry system to
    operate at all times, including times when only battery power is
    available." Without it VIN/VBAT/IBAT/IIN/die_temp are only measured while
    charging. Bit 3 (telemetry_speed) is deliberately left at 0: tel_high_speed
    polls every ~11 ms instead of ~5 s and the datasheet warns it increases
    battery drain when no input power is available.
    """
    conf = read_reg(REG_CONFIG)
    write_reg(REG_CONFIG, conf | (1 << 2))


def ensure_configured():
    """Re-apply the configuration if the chip has lost it.

    After a ship mode cycle the LTC4162 comes back with every register at its
    reset value, so force_telemetry_on is clear again. The part still answers
    on I2C, but with no input power the telemetry system stays off and vbat,
    vin, vout, ibat, iin and die_temp all read 0 (which shows up as VIN 0.00 V
    and T_die -264.4 C). Cheap to check: one register read per call.

    Returns None when the chip is on the bus and configured, or a message when
    it had to be reconfigured. Raises OSError when the chip is off the bus.
    """
    conf = read_reg(REG_CONFIG)
    if conf & (1 << 2):
        return None

    init()
    if _jeita_max_ilim > 0.0 and _jeita_rsnsb > 0.0:
        set_adaptive_jeita(_jeita_max_ilim, _jeita_rsnsb)
    if _jeita_enable_req is not None:
        jeita_enable(_jeita_enable_req)
    return "force_telemetry_on lost (CONFIG=0x%04X): reconfigured after ship cycle" % conf


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


def get_vbat(cells=DEFAULT_CELLS):
    return read_reg(REG_VBAT) * 0.0001924 * cells


def get_vin():
    return i2cbus.s16(read_reg(REG_VIN)) * 0.001649


def get_vout():
    return i2cbus.s16(read_reg(REG_VOUT)) * 0.001653


def get_ibat(rsnsb_ohms=RSNSB_OHMS):
    """Battery current through Rsnsb (CSP/CSN).

    Reg 0x3D (ibat): signed, 1.466 uV / RSNSB amperes per LSB. Positive while
    charging; when the charger is not running the value is the drain on the
    battery and goes negative.
    """
    return i2cbus.s16(read_reg(REG_IBAT)) * 1.466e-6 / rsnsb_ohms


def get_iin(rsni_ohms=RSNI_OHMS):
    """Input current through Rsni (CLP/CLN). Reg 0x3E, same 1.466 uV/R scale."""
    return i2cbus.s16(read_reg(REG_IIN)) * 1.466e-6 / rsni_ohms


def get_die_temp():
    """T_die (deg C) = die_temp * 0.0215 - 264.4, signed.

    The (die_temp - 12010) / 45.6 form belongs to the LTC4015 and does not
    apply to this part.
    """
    return i2cbus.s16(read_reg(REG_DIE_TEMP)) * 0.0215 - 264.4


def get_charger_state():
    return read_reg(REG_CHARGER_STATE)


def get_charge_status():
    return read_reg(REG_CHARGE_STATUS)


def get_system_status():
    return read_reg(REG_SYSTEM_STATUS)


def charger_state_str(state):
    return _CHARGER_STATE_STR.get(state, "UNKNOWN")


def charger_state_short(state):
    return _CHARGER_STATE_SHORT.get(state, "UNKNOWN")


def charge_status_str(status):
    return _CHARGE_STATUS_STR.get(status, "UNKNOWN")


# ---------------------------------------------------------------------------
# Charge current and JEITA
# ---------------------------------------------------------------------------


def _dac_from_current(current, rsnsb_ohms):
    dac = int(current * rsnsb_ohms / 0.001 + 0.5) - 1
    if dac < 0:
        dac = 0
    if dac > 31:
        dac = 31
    return dac


def ilim_set(ilim, rsnsb_ohms=RSNSB_OHMS):
    write_reg(REG_ICHARGE_DAC, _dac_from_current(ilim, rsnsb_ohms))


def ilim_get(rsnsb_ohms=RSNSB_OHMS):
    dac = read_reg(REG_ICHARGE_DAC) & 0x1F
    return (dac + 1) * (0.001 / rsnsb_ohms)


def set_adaptive_jeita(max_ilim, rsnsb_ohms=RSNSB_OHMS):
    global _jeita_max_ilim, _jeita_rsnsb
    _jeita_max_ilim = max_ilim
    _jeita_rsnsb = rsnsb_ohms

    dac_100 = _dac_from_current(max_ilim, rsnsb_ohms)
    dac_50 = _dac_from_current(max_ilim * 0.5, rsnsb_ohms)
    dac_25 = _dac_from_current(max_ilim * 0.25, rsnsb_ohms)

    write_reg(REG_ICHARGE_JEITA_6_5, (dac_25 << 5) | dac_50)
    write_reg(REG_ICHARGE_JEITA_4_3_2, (dac_100 << 10) | (dac_100 << 5) | dac_50)


def jeita_enable(enable):
    """Enable or disable the JEITA temperature qualified charging system.

    Reg 0x29 bit 0 (en_jeita), reset value 1. With JEITA off the charger
    follows icharge_dac / vcharge_setting directly and no longer derates by
    thermistor temperature.
    """
    global _jeita_enable_req
    conf = read_reg(REG_CHARGER_CONFIG)
    if enable:
        conf |= CC_EN_JEITA
    else:
        conf &= ~CC_EN_JEITA & 0xFFFF
    write_reg(REG_CHARGER_CONFIG, conf)
    _jeita_enable_req = bool(enable)
    return conf


def jeita_is_enabled():
    return (read_reg(REG_CHARGER_CONFIG) & CC_EN_JEITA) != 0


def jeita_restore_defaults():
    """Put the JEITA charge current registers back to their reset values and
    stop replaying the custom curve after a ship cycle."""
    global _jeita_max_ilim, _jeita_rsnsb
    write_reg(REG_ICHARGE_JEITA_6_5, ICHARGE_JEITA_6_5_RESET)
    write_reg(REG_ICHARGE_JEITA_4_3_2, ICHARGE_JEITA_4_3_2_RESET)
    _jeita_max_ilim = 0.0
    _jeita_rsnsb = 0.0


# ---------------------------------------------------------------------------
# Ship mode
# ---------------------------------------------------------------------------


def arm_ship_mode():
    write_reg(REG_ARM_SHIP_MODE, ARM_SHIP_MODE_MAGIC)


def disarm_ship_mode():
    """Clear reg 0x19 and return (value_before, value_after)."""
    before = read_reg(REG_ARM_SHIP_MODE)
    write_reg(REG_ARM_SHIP_MODE, 0x0000)
    return before, read_reg(REG_ARM_SHIP_MODE)


def is_ship_mode_armed():
    val = read_reg(REG_ARM_SHIP_MODE)
    return val in (ARM_SHIP_MODE_MAGIC, 0x4D53)


def self_test():
    lines = ["Starting LTC4162 self-test (addr 0x%02X)..." % ADDR]
    if not i2cbus.ping(ADDR):
        lines.append("FAIL: LTC4162 not acknowledging on I2C bus")
        return False, lines

    try:
        init()
    except OSError as err:
        lines.append("FAIL: Could not enable telemetry in CONFIG register: %s" % err)
        return False, lines

    # R/W check on the charge current DAC, original value restored afterwards.
    try:
        orig_dac = read_reg(REG_ICHARGE_DAC)
        test_dac = 0x0B if orig_dac == 0x0A else 0x0A
        write_reg(REG_ICHARGE_DAC, test_dac)
        readback = read_reg(REG_ICHARGE_DAC)
        write_reg(REG_ICHARGE_DAC, orig_dac)
    except OSError as err:
        lines.append("FAIL: REG_ICHARGE_DAC access error: %s" % err)
        return False, lines

    if (readback & 0x1F) != (test_dac & 0x1F):
        lines.append(
            "FAIL: REG_ICHARGE_DAC R/W mismatch (wrote 0x%02X, read 0x%02X)"
            % (test_dac, readback)
        )
        return False, lines

    lines.append("Telemetry Readings:")
    lines.append("  - VIN:      %.2f V" % get_vin())
    lines.append("  - VOUT:     %.2f V" % get_vout())
    lines.append("  - VBAT:     %.2f V (4S cells)" % get_vbat())
    lines.append("  - IBAT:     %.3f A (Rsnsb=16mR)" % get_ibat())
    lines.append("  - IIN:      %.3f A (Rsni=7mR)" % get_iin())
    lines.append("  - DIE TEMP: %.1f C" % get_die_temp())

    chg_state = get_charger_state()
    chg_status = get_charge_status()
    sys_status = get_system_status()
    lines.append("  - CHARGER STATE:  0x%04X %s" % (chg_state, charger_state_str(chg_state)))
    lines.append("  - CHARGE STATUS:  0x%04X %s" % (chg_status, charge_status_str(chg_status)))
    lines.append(
        "  - SYSTEM STATUS:  0x%04X (en_chg=%d vin_gt_vbat=%d vin_gt_4p2v=%d)"
        % (
            sys_status,
            1 if sys_status & SS_EN_CHG else 0,
            1 if sys_status & SS_VIN_GT_VBAT else 0,
            1 if sys_status & SS_VIN_GT_4P2V else 0,
        )
    )

    # Verify ship mode is disarmed; never arm it during a self-test.
    armed = is_ship_mode_armed()
    if armed:
        lines.append("Notice: Ship Mode was armed; actively disarming now.")
        disarm_ship_mode()
    lines.append("Ship Mode Status: %s" % ("DISARMED (was armed)" if armed else "DISARMED (OK)"))
    lines.append("PASS: LTC4162 verified OK.")
    return True, lines
