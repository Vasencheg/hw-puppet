"""ae-hw-bridge target for the I2C charger bench.

Unlike a typical ae-hw-bridge target, the board under test has no UART console:
HW Puppet talks to it purely over I2C (SDA GPIO5, SCL GPIO4, 100 kHz). The
measurement logic lives in the `pb` MicroPython package under device/pb,
resident in /lib/pb on the puppet; everything here is a thin orchestration
layer that calls into it and returns plain dicts for the agent.

The package uploads itself whenever the board is behind these sources, so
`deploy` rarely needs to be called by hand. See README.md for where to put
this file and how the fingerprint check works.
"""

import base64
import importlib.util
import json
import os
from typing import Any, Optional

from ae_hw_bridge.targets.base import BaseTarget, repl

def _resolve_bench_dir():
    """Locate the directory holding device/ and host/.

    Inside this example that is two levels up from targets/charger/. Once this
    directory is copied into a project's .ae-hw-bridge/targets/, the bench
    files usually sit somewhere else entirely, so the search walks up a few
    levels and an explicit path always wins.
    """
    env = os.environ.get("I2C_CHARGER_BENCH_DIR")
    if env:
        return os.path.abspath(env)
    candidate = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.isdir(os.path.join(candidate, "device", "pb")):
            return candidate
        candidate = os.path.dirname(candidate)
    raise RuntimeError(
        "cannot find device/pb; set I2C_CHARGER_BENCH_DIR to the i2c_charger_bench directory"
    )


_BENCH_DIR = _resolve_bench_dir()
_PKG_DIR = os.path.join(_BENCH_DIR, "device", "pb")


def _load_pkgstamp():
    """Load host/pkgstamp.py by path.

    The uploader in host/ and this target must compute the fingerprint the same
    way, so they share one implementation rather than two copies that can drift
    apart."""
    path = os.path.join(_BENCH_DIR, "host", "pkgstamp.py")
    spec = importlib.util.spec_from_file_location("pb_pkgstamp", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_pkgstamp = _load_pkgstamp()

CHARGER_STATE = {
    0x1000: "BATTERY DETECTION FAILED (fault)",
    0x0800: "BATTERY DETECTION IN PROGRESS",
    0x0100: "CHARGER SUSPENDED / NO INPUT",
    0x0080: "PRECHARGE (low battery)",
    0x0040: "CC/CV CHARGING",
    0x0020: "PAUSED ON NTC TEMPERATURE",
    0x0010: "TERMINATED BY TIMER (charged)",
    0x0008: "TERMINATED BY C/x (charged)",
    0x0004: "MAX CHARGE TIME FAULT",
    0x0002: "BATTERY MISSING (fault)",
    0x0001: "BATTERY SHORTED (fault)",
    0: "IDLE (no state bit set)",
}

CHARGE_STATUS = {
    0x0020: "ILIM REGULATION ACTIVE",
    0x0010: "THERMAL REGULATION ACTIVE",
    0x0008: "VIN UNDERVOLTAGE LIMIT ACTIVE",
    0x0004: "INPUT CURRENT LIMIT ACTIVE",
    0x0002: "CONSTANT CURRENT",
    0x0001: "CONSTANT VOLTAGE",
    0: "CHARGER OFF",
}

DEVICES = {"ltc4162": 0x68, "pca9536": 0x41, "lm75b": 0x49}


class ChargerBenchTarget(BaseTarget):
    """Charger bench: LTC4162-L charger, PCA9536 GPIO expander, LM75B temp sensor."""

    PIN_SDA: int = 5
    PIN_SCL: int = 4
    PIN_LED: int = 48  # HW Puppet onboard WS2812

    REMOTE_DIR: str = "/lib/pb"

    # Fingerprint the board was last confirmed to run. The bridge daemon keeps
    # this target alive across calls, so caching a plain boolean would hide an
    # edit made later in the same session; keyed by the fingerprint, a changed
    # source invalidates it by itself. Recomputing it reads six local files,
    # which is far cheaper than a round trip to the board.
    _verified_stamp: Optional[str] = None

    # ------------------------------------------------------------------
    # Low-level: executed inside the puppet's MicroPython VM
    # ------------------------------------------------------------------

    @repl
    def _repl_set_status_led(self, r: int, g: int, b: int, pin: int = 48):
        import neopixel
        from machine import Pin

        try:
            np = neopixel.NeoPixel(Pin(pin, Pin.OUT), 1)
            np[0] = (r, g, b)
            np.write()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers (private, not exposed as tools)
    # ------------------------------------------------------------------

    def _exec_json(self, code: str, timeout: float = 15.0) -> Any:
        """Run code on the puppet and parse the last stdout line as JSON."""
        res = self.run_custom_code(code, timeout=timeout)
        ok = res.get("ok") if isinstance(res, dict) else getattr(res, "ok", False)
        stdout = res.get("stdout") if isinstance(res, dict) else getattr(res, "stdout", "")
        stderr = res.get("stderr") if isinstance(res, dict) else getattr(res, "stderr", "")
        if not ok or stderr:
            raise RuntimeError(stderr or "execution failed on the puppet")
        lines = [ln for ln in (stdout or "").replace("\r", "").split("\n") if ln.strip()]
        if not lines:
            raise RuntimeError("no output from the puppet")
        return json.loads(lines[-1])

    def _board_state(self) -> dict[str, Any]:
        """Ask the board which package it is running, if any.

        Must survive meeting an older package than this file expects: that is
        exactly the case the auto-deploy exists for, so every attribute is
        probed rather than assumed.
        """
        return self._exec_json(
            "import json\n"
            "try:\n"
            "    import pb\n"
            "except ImportError:\n"
            "    print(json.dumps({'installed': False}))\n"
            "else:\n"
            "    fn = getattr(pb, 'stamp', None)\n"
            "    watcher = getattr(getattr(pb, 'btnpwr', None), 'is_running', None)\n"
            "    hold = getattr(pb, 'hold', None)\n"
            "    print(json.dumps({'installed': True,\n"
            "                      'version': getattr(pb, 'VERSION', None),\n"
            "                      'stamp': fn() if fn else None,\n"
            "                      'watcher': watcher() if watcher else None,\n"
            "                      'hold_time_ms': hold() if hold else None}))\n"
        )

    def _ensure_deployed(self) -> None:
        """Upload the package when the board has none, or an outdated one.

        Without this an edit to a driver that was never pushed would leave the
        agent reading a stale one with no sign that anything is wrong.
        """
        expected = _pkgstamp.source_stamp(_PKG_DIR)
        if self._verified_stamp == expected:
            return
        state = self._board_state()
        if state.get("installed") and state.get("stamp") == expected:
            self._verified_stamp = expected
            return
        self.deploy(self.REMOTE_DIR)

    def _pb_init(self, start_button: bool = True, hold_time_ms: int = 5000) -> Any:
        """init() straight on the board, bypassing the deploy check.

        deploy() calls this while the check is still false, so routing it
        through _pb_call would recurse."""
        return self._exec_json(
            "import pb, json; print(json.dumps(pb.init(start_button=%s, hold_time_ms=%d)))"
            % (bool(start_button), int(hold_time_ms))
        )

    def _pb_call(self, expr: str, timeout: float = 15.0) -> Any:
        """Call into the pb package, deploying it first if the board is stale."""
        self._ensure_deployed()
        return self._exec_json("import pb, json; print(json.dumps(%s))" % expr, timeout)

    @staticmethod
    def _c_to_f(celsius: Optional[float]) -> Optional[float]:
        return None if celsius is None else round(celsius * 9.0 / 5.0 + 32.0, 1)

    # ------------------------------------------------------------------
    # High-level tools exposed to the agent
    # ------------------------------------------------------------------

    def deploy(self, remote_dir: str = "/lib/pb") -> dict[str, Any]:
        """Upload the pb MicroPython package from this repo to the HW Puppet.

        Reads device/pb/*.py and writes them into the puppet filesystem
        over the Raw REPL. Run once after flashing the puppet, and again after
        changing any driver source.

        Args:
            remote_dir: Destination directory on the puppet (default: /lib/pb).
        """
        if not os.path.isdir(_PKG_DIR):
            raise RuntimeError("package directory not found: %s" % _PKG_DIR)

        # What the board was doing before, so the watcher comes back the same.
        previous = self._board_state()

        self.run_custom_code(
            "import os\n"
            "p = ''\n"
            "for part in %r.split('/'):\n"
            "    if part:\n"
            "        p += '/' + part\n"
            "        try:\n"
            "            os.mkdir(p)\n"
            "        except OSError:\n"
            "            pass\n" % remote_dir
        )

        uploaded = {}
        sources = sorted(
            f for f in os.listdir(_PKG_DIR)
            if f.endswith(".py") and f != _pkgstamp.STAMP_FILE
        )
        for name in sources:
            with open(os.path.join(_PKG_DIR, name), "rb") as fh:
                data = fh.read()
            remote = "%s/%s" % (remote_dir, name)
            self.run_custom_code("import ubinascii\nf = open(%r, 'wb')" % remote)
            for off in range(0, len(data), 512):
                blob = base64.b64encode(data[off : off + 512]).decode("ascii")
                self.run_custom_code("f.write(ubinascii.a2b_base64(%r))" % blob)
            self.run_custom_code("f.close()")
            uploaded[name] = len(data)

        stamp = _pkgstamp.source_stamp(_PKG_DIR)
        self.run_custom_code(
            "f = open(%r, 'w')\nf.write(%r)\nf.close()"
            % ("%s/%s" % (remote_dir, _pkgstamp.STAMP_FILE), _pkgstamp.stamp_source(stamp))
        )

        # Stop the running watcher BEFORE dropping the modules. Its soft timer
        # holds a reference to the old callback: left alone it would keep
        # polling the bus through the old i2cbus lock, which the reloaded
        # package knows nothing about, and the two would cut into each other's
        # transactions.
        self.run_custom_code(
            "import sys\n"
            "try:\n"
            "    import pb\n"
            "    pb.btnpwr.stop()\n"
            "except Exception:\n"
            "    pass\n"
            "for name in [m for m in sys.modules if m == 'pb' or m.startswith('pb.')]:\n"
            "    del sys.modules[name]\n"
        )

        # Bring the board back up the way it was before the upload.
        want_watcher = previous.get("watcher")
        hold_ms = previous.get("hold_time_ms") or 5000
        self._pb_init(
            start_button=True if want_watcher is None else bool(want_watcher),
            hold_time_ms=int(hold_ms),
        )

        state = self._board_state()
        verified = state.get("stamp") == stamp
        self._verified_stamp = stamp if verified else None
        return {"ok": True, "remote_dir": remote_dir, "files": uploaded,
                "stamp": stamp, "pb_version": state.get("version"),
                "watcher": state.get("watcher"), "hold_time_ms": state.get("hold_time_ms"),
                "verified": verified}

    def init(self, start_button_watcher: bool = True, hold_time_ms: int = 5000) -> dict[str, Any]:
        """Bring up the I2C bus and all three devices on the board under test.

        Args:
            start_button_watcher: Start the 25 ms soft-timer watcher that arms
                LTC4162 Ship Mode after a long press on SW1.
            hold_time_ms: Press duration that triggers Ship Mode (default 5000).
        """
        self._ensure_deployed()
        return self._pb_init(start_button_watcher, hold_time_ms)

    def status(self) -> dict[str, Any]:
        """Read the complete board state in a single round trip.

        Returns voltages, currents, both temperatures, charger stage, GPIO lines
        and Ship Mode state. A value that could not be read comes back as null
        rather than a sentinel number. Temperatures are given in both degC and
        degF.
        """
        snap = self._pb_call("pb.snapshot()")
        snap["t_brd_f"] = self._c_to_f(snap.get("t_brd"))
        snap["t_die_f"] = self._c_to_f(snap.get("t_die"))
        snap["stage"] = (
            CHARGER_STATE.get(snap.get("chg_state"), "UNKNOWN")
            if snap.get("chg_state") is not None
            else None
        )
        snap["charge_status_text"] = (
            CHARGE_STATUS.get(snap.get("chg_status"), "UNKNOWN")
            if snap.get("chg_status") is not None
            else None
        )
        return snap

    def selftest(self) -> dict[str, Any]:
        """Run the full hardware self-test suite: I2C scan, LM75B, PCA9536, LTC4162.

        Lights the puppet status LED green on success, red on failure.
        """
        res = self._pb_call("pb.selftest()", timeout=30.0)
        ok = bool(res[0]) if isinstance(res, list) else bool(res.get("ok"))
        lines = res[1] if isinstance(res, list) else res.get("lines", [])
        if ok:
            self._repl_set_status_led(0, 60, 0, pin=self.PIN_LED)
        else:
            self._repl_set_status_led(60, 0, 0, pin=self.PIN_LED)
        # `report` repeats `lines` as one string: the CLI prints scalars only.
        return {"ok": ok, "report": "\n".join(lines), "lines": lines}

    def scan_i2c(self) -> dict[str, Any]:
        """Scan the I2C bus and report which of the expected devices answered."""
        res = self._pb_call("pb.i2cbus.self_test()")
        ok = bool(res[0]) if isinstance(res, list) else bool(res.get("ok"))
        lines = res[1] if isinstance(res, list) else res.get("lines", [])
        return {"ok": ok, "report": "\n".join(lines), "lines": lines}

    def read_register(self, device: str, register: int) -> dict[str, Any]:
        """Read one raw register from a device on the bus.

        Args:
            device: One of 'ltc4162' (16-bit, little endian), 'pca9536' or
                'lm75b' (8-bit).
            register: Register address, e.g. 0x39 for LTC4162 system_status.
        """
        key = device.strip().lower()
        if key not in DEVICES:
            raise ValueError("unknown device %r, expected one of %s" % (device, sorted(DEVICES)))
        if key == "ltc4162":
            val = self._pb_call("pb.ltc4162.read_reg(%d)" % int(register))
        else:
            val = self._pb_call("pb.i2cbus.read_byte(%d, %d)" % (DEVICES[key], int(register)))
        return {"device": key, "address": DEVICES[key], "register": int(register),
                "value": val, "hex": "0x%04X" % val}

    def set_led(self, on: bool) -> dict[str, Any]:
        """Switch the indicator board LED power rail (PCA9536 IO0)."""
        return {"led": self._pb_call("pb.led(%s)" % bool(on))}

    def set_button_hold(self, hold_time_ms: Optional[int] = None) -> dict[str, Any]:
        """Get or set how long SW1 must be held to arm Ship Mode.

        Args:
            hold_time_ms: New duration in ms (500..60000). Omit to just read it.
        """
        if hold_time_ms is None:
            return {"hold_time_ms": self._pb_call("pb.hold()")}
        if not 500 <= int(hold_time_ms) <= 60000:
            raise ValueError("hold_time_ms must be between 500 and 60000")
        return {"hold_time_ms": self._pb_call("pb.hold(%d)" % int(hold_time_ms))}

    def jeita(self, mode: str = "show", amps: float = 1.5) -> dict[str, Any]:
        """Inspect or change JEITA temperature qualified charging.

        Args:
            mode: 'show' (default), 'on', 'off', 'default' to restore the stock
                charge current registers, or 'custom' to load the adaptive curve.
            amps: Maximum charge current for mode='custom' (0.01..2.00 A).
        """
        action = mode.strip().lower()
        if action == "show":
            pass
        elif action == "on":
            self._pb_call("pb.ltc4162.jeita_enable(True)")
        elif action == "off":
            self._pb_call("pb.ltc4162.jeita_enable(False)")
        elif action == "default":
            self.run_custom_code("import pb; pb.ltc4162.jeita_restore_defaults()")
        elif action == "custom":
            if not 0.0 < float(amps) <= 2.0:
                raise ValueError("amps must be in 0.01..2.00")
            self._pb_call("pb.jeita_custom(%r)" % float(amps))
        else:
            raise ValueError("mode must be show, on, off, default or custom")
        return self._pb_call("pb.jeita_state()")

    def disarm_ship_mode(self) -> dict[str, Any]:
        """Clear LTC4162 arm_ship_mode (reg 0x19), cancelling a pending shutdown."""
        before, after = self._pb_call("pb.disarm()")
        return {"reg_0x19_before": "0x%04X" % before, "reg_0x19_after": "0x%04X" % after,
                "armed": after != 0}

    def arm_ship_mode(self, confirm: bool = False) -> dict[str, Any]:
        """Arm LTC4162 Ship Mode. POWERS THE BOARD DOWN.

        On battery the board shuts down immediately; with the DC adapter
        connected it shuts down as soon as the adapter is unplugged. How it
        wakes up again is a property of your hardware, not of this target.

        Args:
            confirm: Must be True. Guards against an accidental shutdown.
        """
        if not confirm:
            return {"armed": False,
                    "error": "refused: call again with confirm=True, this powers the board down"}
        vin = self._pb_call("pb._safe(pb.ltc4162.get_vin)")
        self.run_custom_code("import pb; pb.ltc4162.arm_ship_mode()")
        return {"armed": True, "vin_before": vin,
                "note": "on battery the board is already down; on DC it drops when unplugged"}

    def check_alive(self) -> dict[str, Any]:
        """Check the puppet answers, and whether it runs the current package.

        Does not deploy anything; it reports what is there. Every other action
        deploys by itself when the board is behind the repository.
        """
        state = self._board_state()
        expected = _pkgstamp.source_stamp(_PKG_DIR)
        state["repo_stamp"] = expected
        state["up_to_date"] = state.get("installed", False) and state.get("stamp") == expected
        return state
