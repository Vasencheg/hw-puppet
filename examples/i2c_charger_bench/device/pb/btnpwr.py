"""Power button hold watcher: 5 s on SW1 arms LTC4162 Ship Mode.

Runs on the HW Puppet board from a soft timer so that it keeps working while
the host is idle or disconnected. It never prints: the board is driven over
the Raw REPL and stray output would corrupt the protocol stream. Events are
queued in a ring buffer instead and the host drains them with take_events().
"""

import time

from . import i2cbus, ltc4162, pca9536

DEFAULT_HOLD_MS = 5000
POLL_MS = 25
DEBOUNCE_TICKS = 3  # 3 * 25 ms = 75 ms debounce filter
MAX_EVENTS = 16

_timer = None
_hold_time_ms = DEFAULT_HOLD_MS
_events = []

_is_pressed = False
_hold_sec = 0

_startup_released = False
_debounced = False
_debounce_count = 0
_was_pressed = False
_action_triggered = False
_press_start_ms = 0


def _emit(msg):
    _events.append(msg)
    while len(_events) > MAX_EVENTS:
        _events.pop(0)


def _ship_mode_action():
    try:
        vin = ltc4162.get_vin()
    except OSError:
        vin = -1.0

    if vin < 1.0:
        _emit("[BTN] 5-second hold on BATTERY (VIN = %.2f V): entering Ship Mode now" % vin)
    else:
        _emit(
            "[BTN] 5-second hold with DC adapter (VIN = %.2f V): Ship Mode ARMED, "
            "board shuts down when the DC plug is removed" % vin
        )

    try:
        ltc4162.arm_ship_mode()
        _emit("[BTN] arm_ship_mode written (reg 0x19 = 0x534D)")
    except OSError as err:
        _emit("[BTN] FAILED to arm Ship Mode: %s" % err)


def _tick(_timer_obj):
    global _debounced, _debounce_count, _is_pressed, _hold_sec
    global _startup_released, _was_pressed, _action_triggered, _press_start_ms

    # Skip this tick rather than cut into a telemetry transaction in progress.
    if not i2cbus.lock(False):
        return
    try:
        raw_pressed = (i2cbus.bus().readfrom_mem(pca9536.ADDR, pca9536.REG_INPUT, 1)[0]
                       & pca9536.PIN_EXT_BTN) == 0
    except OSError:
        return
    finally:
        i2cbus.unlock()

    # Debounce integrator
    if raw_pressed != _debounced:
        _debounce_count += 1
        if _debounce_count >= DEBOUNCE_TICKS:
            _debounced = raw_pressed
            _debounce_count = 0
    else:
        _debounce_count = 0

    _is_pressed = _debounced

    # Startup safety: require the button to be released first. If the user held
    # SW1 to wake the board up, wait for them to let go.
    if not _startup_released:
        if not _debounced:
            _startup_released = True
            _emit("[BTN] startup release confirmed, long-press monitoring active")
        return

    if _debounced:
        if not _was_pressed:
            _was_pressed = True
            _action_triggered = False
            _press_start_ms = time.ticks_ms()
            _hold_sec = 0
        else:
            elapsed = time.ticks_diff(time.ticks_ms(), _press_start_ms)
            _hold_sec = elapsed // 1000
            if elapsed >= _hold_time_ms and not _action_triggered:
                _action_triggered = True
                _ship_mode_action()
    elif _was_pressed:
        elapsed = time.ticks_diff(time.ticks_ms(), _press_start_ms)
        if not _action_triggered and elapsed >= 800:
            _emit(
                "[BTN] released after %.1f sec (required %.1f sec for Ship Mode)"
                % (elapsed / 1000.0, _hold_time_ms / 1000.0)
            )
        _was_pressed = False
        _action_triggered = False
        _hold_sec = 0


def start(hold_time_ms=DEFAULT_HOLD_MS):
    """(Re)start the watcher. Soft timer id -1 runs the callback in its own
    task, so I2C access from it is allowed."""
    global _timer, _hold_time_ms, _startup_released
    from machine import Timer

    set_hold_time(hold_time_ms)
    stop()
    _startup_released = False
    _timer = Timer(-1)
    _timer.init(period=POLL_MS, mode=Timer.PERIODIC, callback=_tick)


def stop():
    global _timer
    if _timer is not None:
        _timer.deinit()
        _timer = None


def is_running():
    return _timer is not None


def set_hold_time(hold_ms):
    global _hold_time_ms
    if hold_ms > 0:
        _hold_time_ms = int(hold_ms)


def get_hold_time():
    return _hold_time_ms


def is_pressed():
    return _is_pressed


def hold_sec():
    return _hold_sec


def take_events():
    """Return queued events and clear the buffer."""
    global _events
    out = _events
    _events = []
    return out
