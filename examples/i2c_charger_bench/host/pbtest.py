#!/usr/bin/env python3
"""Charger bench interactive console.

The measurement logic lives in MicroPython on the HW Puppet board
(device/pb); this script only drives it over the CDC 0 Raw REPL and renders
the output.

    ./pbtest.py              # connect, self-test, live monitor
    ./pbtest.py --push       # upload the pb package first
    ./pbtest.py --no-test    # skip the boot self-test
"""

import argparse
import select
import sys
import termios
import time
import tty

from rawrepl import DEFAULT_PORT, RawRepl, RawReplError

MON_OFF, MON_LIVE, MON_TABLE = 0, 1, 2

STAGE_STR = {
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

STAGE_SHORT = {
    0x1000: "DETFAIL",
    0x0800: "BATDET ",
    0x0100: "SUSPEND",
    0x0080: "PRECHG ",
    0x0040: "CC/CV  ",
    0x0020: "NTCPAUS",
    0x0010: "TMRTERM",
    0x0008: "C/X-END",
    0x0004: "MAXTIME",
    0x0002: "NO BATT",
    0x0001: "BATSHRT",
    0: "IDLE   ",
}

CHARGE_STATUS_STR = {
    0x0020: "ILIM REGULATION ACTIVE",
    0x0010: "THERMAL REGULATION ACTIVE",
    0x0008: "VIN UNDERVOLTAGE LIMIT ACTIVE",
    0x0004: "INPUT CURRENT LIMIT ACTIVE",
    0x0002: "CONSTANT CURRENT",
    0x0001: "CONSTANT VOLTAGE",
    0: "CHARGER OFF",
}

HELP = """
Available commands:
  help / ?       - Show this command reference
  status / stat  - Print detailed telemetry box
  dash           - Enter full-screen live dashboard
  live           - Switch monitoring to in-place single line (no scrolling)
  table          - Switch monitoring to aligned table format
  mon off        - Turn off periodic monitoring
  test           - Re-run complete self-test suite
  scan           - Scan I2C bus
  ship           - Arm Ship Mode (shuts down on battery, or when DC removed)
  disarm         - Disarm Ship Mode (cancel pending shutdown)
  hold [ms]      - Get or set button hold duration for Ship Mode (e.g. 'hold 5000')
  jeita          - Show JEITA state (reg 0x29 bit 0, regs 0x27/0x28)
  jeita off      - Disable JEITA temperature qualified charging
  jeita on       - Enable JEITA (chip default)
  jeita default  - Restore stock JEITA charge current registers
  jeita custom [A] - Apply adaptive JEITA curve (default 1.5 A)
  led on         - Turn ON indicator board LED power (PCA9536 IO0)
  led off        - Turn OFF indicator board LED power (PCA9536 IO0)
  quit / exit    - Leave the console (the board keeps running)
"""


def num(val, fmt, width):
    """Format a reading, or a dash of the same width when it is missing.

    A failed read is shown as '-' rather than a sentinel number, so nothing on
    screen can be mistaken for a measurement."""
    if val is None:
        return "-".center(width)
    return fmt % val


def stage_of(snap, short=False):
    state = snap.get("chg_state")
    if state is None:
        return "  ---  " if short else "UNAVAILABLE (chip off the bus)"
    table = STAGE_SHORT if short else STAGE_STR
    return table.get(state, "UNKNOWN")


class Console:
    def __init__(self, repl):
        self.repl = repl
        self.mon_mode = MON_LIVE
        self.in_dashboard = False
        self.typing = False
        self.line = ""
        self.table_rows = 0
        self.live_line_open = False

    # -- board calls --------------------------------------------------------

    def snapshot(self):
        return self.repl.exec_json("import pb; print(pb.snapshot_json())")

    def run_lines(self, code):
        out = self.repl.exec_(code)
        if out.strip():
            print(out.rstrip())

    # -- rendering ----------------------------------------------------------

    def close_live_line(self):
        if self.live_line_open:
            sys.stdout.write("\n")
            self.live_line_open = False

    def print_events(self, snap):
        events = snap.get("events") or []
        if events:
            self.close_live_line()
            for ev in events:
                print(ev)

    def print_detailed(self, snap):
        io = snap.get("raw_io")
        io_str = (
            "0x%02X (IO1=%d, IO3=%d)" % (io, (io >> 1) & 1, (io >> 3) & 1)
            if io is not None
            else "unavailable"
        )
        sys_status = snap.get("sys_status")
        if sys_status is None:
            sys_str = "unavailable"
        else:
            sys_str = "0x%04X  en_chg=%d vin>vbat=%d vin>4.2V=%d" % (
                sys_status,
                1 if sys_status & 0x0100 else 0,
                1 if sys_status & 0x0004 else 0,
                1 if sys_status & 0x0002 else 0,
            )
        ibat = snap.get("ibat")
        print("")
        print("+--------------------------------------------------------------------+")
        print("|                     DETAILED TELEMETRY                             |")
        print("+--------------------------------------------------------------------+")
        print("|  LM75B Board Temperature  : %s C" % num(snap.get("t_brd"), "%+6.2f", 6))
        print("|  LTC4162 Die Temperature  : %s C" % num(snap.get("t_die"), "%+6.2f", 6))
        print("|  PCA9536 Raw Input Port   : %s" % io_str)
        print("|  PCA9536 Button (IO1)     : %s" % (
            "unavailable" if snap.get("btn") is None
            else "PRESSED / ACTIVE (LOW)" if snap["btn"] else "RELEASED / INACTIVE (HIGH)"))
        print("|  PCA9536 SIM Detect (IO3) : %s" % (
            "unavailable" if snap.get("sim") is None
            else "SIM CARD PRESENT" if snap["sim"] else "NO SIM CARD"))
        print("|  PCA9536 LED Power (IO0)  : %s" % ("ENABLED (ON)" if snap.get("led") else "DISABLED (OFF)"))
        print("|  Input Voltage (VIN)      : %s V" % num(snap.get("vin"), "%6.2f", 6))
        print("|  System Output Rail (VOUT): %s V" % num(snap.get("vout"), "%6.2f", 6))
        print("|  Battery Pack (VBAT 4S)   : %s V" % num(snap.get("vbat"), "%6.2f", 6))
        print("|  Input Current (IIN)      : %s A" % num(snap.get("iin"), "%+6.3f", 6))
        print("|  Battery Current (IBAT)   : %s A  (Current Limit: %s A)"
              % (num(ibat, "%+6.3f", 6), num(snap.get("ilim"), "%4.2f", 4)))
        print("|  IBAT sign                : %s" % (
            "unavailable" if ibat is None
            else "NEGATIVE = BATTERY DISCHARGING" if ibat < -0.005 else "POSITIVE = CHARGING / IDLE"))
        print("|  JEITA Charging (0x29.0)  : %s" % (
            "unavailable" if snap.get("jeita") is None
            else "ENABLED" if snap["jeita"] else "DISABLED"))
        print("|  Charger Stage (0x34)     : %s" % stage_of(snap))
        print("|  Charge Status (0x35)     : %s" % (
            "unavailable" if snap.get("chg_status") is None
            else CHARGE_STATUS_STR.get(snap["chg_status"], "UNKNOWN")))
        print("|  System Status (0x39)     : %s" % sys_str)
        print("|  LTC4162 Ship Mode Status : %s" % (
            "unavailable" if snap.get("ship_armed") is None
            else "ARMED (0x534D) [WILL SHUT DOWN]" if snap["ship_armed"]
            else "DISARMED (0x0000) [NORMAL]"))
        print("+--------------------------------------------------------------------+")
        print("")

    def print_dashboard(self, snap):
        ibat = snap.get("ibat")
        sys.stdout.write("\033[2J\033[H")
        print("+--------------------------------------------------------------------+")
        print("|                  I2C CHARGER BENCH DASHBOARD                       |")
        print("+--------------------------------------------------------------------+")
        print("|  TEMPERATURES                                                      |")
        print("|    - Board Temp (LM75B U5)     : %s C" % num(snap.get("t_brd"), "%+6.2f", 6))
        print("|    - Charger Die Temp (LTC4162): %s C" % num(snap.get("t_die"), "%+6.2f", 6))
        print("|                                                                    |")
        print("|  GPIO & SIGNALS (PCA9536 U6)                                       |")
        print("|    - External Button (IO1)     : %s" % (
            "unavailable" if snap.get("btn") is None
            else "PRESSED / ACTIVE (LOW)" if snap["btn"] else "RELEASED / INACTIVE (HIGH)"))
        print("|    - SIM Card Detect (IO3)     : %s" % (
            "unavailable" if snap.get("sim") is None
            else "SIM CARD PRESENT" if snap["sim"] else "NO SIM CARD DETECTED"))
        print("|    - Indicator LED Power (IO0) : %s" % ("ENABLED (HIGH)" if snap.get("led") else "DISABLED (LOW)"))
        print("|                                                                    |")
        print("|  POWER & BATTERY (LTC4162 U1)                                      |")
        print("|    - Input Voltage (VIN)       : %s V" % num(snap.get("vin"), "%6.2f", 6))
        print("|    - Output Rail (VOUT)        : %s V" % num(snap.get("vout"), "%6.2f", 6))
        print("|    - Battery Voltage (VBAT 4S) : %s V" % num(snap.get("vbat"), "%6.2f", 6))
        print("|    - Input Current (IIN)       : %s A" % num(snap.get("iin"), "%+6.3f", 6))
        print("|    - Battery Current (IBAT)    : %s A  (Limit: %s A)"
              % (num(ibat, "%+6.3f", 6), num(snap.get("ilim"), "%4.2f", 4)))
        print("|    - Battery Direction         : %s" % (
            "unavailable" if ibat is None
            else "DISCHARGING (running on battery)" if ibat < -0.005 else "CHARGING / IDLE"))
        print("|    - Charger Stage             : %s" % stage_of(snap))
        print("|    - Charge Status             : %s" % (
            "unavailable" if snap.get("chg_status") is None
            else CHARGE_STATUS_STR.get(snap["chg_status"], "UNKNOWN")))
        print("|    - Ship Mode State           : %s" % (
            "unavailable" if snap.get("ship_armed") is None
            else "ARMED (0x534D) [WILL SHUT DOWN]" if snap["ship_armed"]
            else "DISARMED (0x0000) [NORMAL]"))
        print("+--------------------------------------------------------------------+")
        print("|  [Press ENTER to exit dashboard and return to console]             |")
        print("+--------------------------------------------------------------------+")
        sys.stdout.flush()

    @staticmethod
    def table_header():
        print("")
        print("+--------+------------+---------+--------+---------+--------+---------+--------+---------+")
        print("| T_brd  |  EXT_BTN   | SIM_ON  |  VIN   |   IIN   |  VBAT  |  IBAT   | T_die  |  STAGE  |")
        print("+--------+------------+---------+--------+---------+--------+---------+--------+---------+")

    @staticmethod
    def btn_text(snap):
        if snap.get("btn_pressed") and snap.get("btn_hold_s"):
            return "HOLD %d/%ds" % (snap["btn_hold_s"], snap.get("hold_time_ms", 5000) // 1000)
        if snap.get("btn_pressed"):
            return "PRESSED"
        if snap.get("btn") is None:
            return "n/a"
        return "RELEASED"

    def print_monitor(self, snap):
        sim = snap.get("sim")
        sim_str = "n/a" if sim is None else ("PRESENT" if sim else "NO SIM")
        fields = (
            num(snap.get("t_brd"), "%+6.1f", 6),
            self.btn_text(snap),
            sim_str,
            num(snap.get("vin"), "%6.2f", 6),
            num(snap.get("iin"), "%+7.3f", 7),
            num(snap.get("vbat"), "%6.2f", 6),
            num(snap.get("ibat"), "%+7.3f", 7),
            num(snap.get("t_die"), "%+6.1f", 6),
            stage_of(snap, short=True),
        )
        if self.mon_mode == MON_LIVE:
            sys.stdout.write(
                "\r\033[K[MON] T_brd:%sC | BTN:%-10s | SIM:%-7s | VIN:%sV | IIN:%sA | "
                "VBAT:%sV | IBAT:%sA | T_die:%sC | %s" % fields
            )
            sys.stdout.flush()
            self.live_line_open = True
        else:
            if self.table_rows % 20 == 0:
                self.table_header()
            self.table_rows += 1
            print("| %s | %-10s | %-7s | %s | %s | %s | %s | %s | %-7s |" % fields)

    # -- commands -----------------------------------------------------------

    def handle(self, cmd):
        cmd = cmd.strip()
        if not cmd:
            return True
        print("\n[CLI] > %s" % cmd)

        if cmd in ("help", "?"):
            print(HELP)
        elif cmd in ("quit", "exit"):
            return False
        elif cmd in ("status", "stat"):
            self.print_detailed(self.snapshot())
        elif cmd == "dash":
            self.in_dashboard = True
        elif cmd in ("live", "mon live", "mon on"):
            self.mon_mode = MON_LIVE
            print("Monitoring mode: LIVE (in-place single line update).")
        elif cmd in ("table", "mon table"):
            self.mon_mode = MON_TABLE
            self.table_rows = 0
            self.table_header()
        elif cmd == "mon off":
            self.mon_mode = MON_OFF
            print("Periodic monitoring disabled. Use 'status' or 'dash' to view data.")
        elif cmd == "test":
            res = self.repl.exec_json("import pb; print(pb.selftest_json())")
            for line in res["lines"]:
                print(line)
        elif cmd == "scan":
            res = self.repl.exec_json("import pb; print(pb.scan_json())")
            for line in res["lines"]:
                print(line)
        elif cmd == "ship":
            self.cmd_ship()
        elif cmd == "disarm":
            before, after = self.repl.exec_json(
                "import pb, json; print(json.dumps(pb.disarm()))"
            )
            print("[OK] Ship Mode DISARMED (reg 0x19: 0x%04X -> 0x%04X)." % (before, after))
        elif cmd.startswith("hold"):
            self.cmd_hold(cmd[4:].strip())
        elif cmd.startswith("jeita"):
            self.cmd_jeita(cmd[5:].strip())
        elif cmd == "led on":
            self.repl.exec_("import pb; pb.led(True)")
            print("[OK] LED_PWR_EN set HIGH")
        elif cmd == "led off":
            self.repl.exec_("import pb; pb.led(False)")
            print("[OK] LED_PWR_EN set LOW")
        else:
            print("[?] Unknown command: '%s'. Type 'help' for options." % cmd)
        return True

    def cmd_ship(self):
        vin = self.repl.exec_json("import pb, json; print(json.dumps(pb._safe(pb.ltc4162.get_vin)))")
        if vin is None:
            print("\n[WARN] Could not read VIN; the charger may already be off the bus.")
        elif vin < 1.0:
            print("\n[WARN] BOARD IS ON BATTERY (VIN = %.2f V)!" % vin)
            print("[WARN] Arming Ship Mode: POWER WILL SHUT DOWN IMMEDIATELY!")
        else:
            print("\n[INFO] DC ADAPTER CONNECTED (VIN = %.2f V)." % vin)
            print("[INFO] Ship Mode armed: board will SHUT DOWN when adapter is unplugged.")
        time.sleep(0.5)
        try:
            self.repl.exec_("import pb; pb.ltc4162.arm_ship_mode()")
            print("[OK] Ship Mode successfully ARMED (reg 0x19 = 0x534D).")
        except RawReplError as err:
            print("[FAIL] Failed to write arm_ship_mode: %s" % err)

    def cmd_hold(self, arg):
        if arg:
            try:
                ms = int(arg)
            except ValueError:
                print("[!] Invalid hold time: '%s'." % arg)
                return
            if 500 <= ms <= 60000:
                self.repl.exec_("import pb; pb.hold(%d)" % ms)
                print("[OK] Button hold time set to %d ms (%.1f sec)." % (ms, ms / 1000.0))
            else:
                print("[!] Invalid hold time: %d ms (allowed range: 500..60000 ms)." % ms)
        else:
            ms = int(self.repl.exec_("import pb; print(pb.hold())").strip())
            print("Current button hold time: %d ms (%.1f sec)." % (ms, ms / 1000.0))

    def cmd_jeita(self, arg):
        if arg == "off":
            self.repl.exec_("import pb; pb.ltc4162.jeita_enable(False)")
            print("[OK] JEITA DISABLED (reg 0x29 bit 0 = 0).")
            print("     Charge current now follows icharge_dac only, no temperature derating.")
        elif arg == "on":
            self.repl.exec_("import pb; pb.ltc4162.jeita_enable(True)")
            print("[OK] JEITA ENABLED (reg 0x29 bit 0 = 1, chip default).")
        elif arg == "default":
            self.repl.exec_("import pb; pb.ltc4162.jeita_restore_defaults()")
            print("[OK] JEITA charge current registers restored to reset values.")
            print("     0x27 = 495, 0x28 = 32751. Custom curve will no longer be replayed.")
        elif arg.startswith("custom"):
            rest = arg[6:].strip()
            try:
                amps = float(rest) if rest else 1.5
            except ValueError:
                print("[!] Invalid current: '%s'." % rest)
                return
            if amps <= 0.0 or amps > 2.0:
                print("[!] Invalid current: %.3f A (allowed range: 0.01..2.00 A)." % amps)
                return
            self.repl.exec_("import pb; pb.jeita_custom(%r)" % amps)
            print("[OK] Custom adaptive JEITA applied for %.2f A max, JEITA enabled." % amps)
        elif not arg:
            st = self.repl.exec_json("import pb; print(pb.jeita_state_json())")
            print("JEITA system   : %s" % ("ENABLED" if st["enabled"] else "DISABLED"))
            print("  reg 0x29     : 0x%04X (en_jeita=%d, en_c_over_x_term=%d)"
                  % (st["r29"], int(st["enabled"]), int(st["c_over_x_term"])))
            print("  reg 0x27     : %d %s" % (st["r27"], "(stock)" if st["r27_stock"] else "(custom)"))
            print("  reg 0x28     : %d %s" % (st["r28"], "(stock)" if st["r28_stock"] else "(custom)"))
        else:
            print("[?] Usage: jeita | jeita on | jeita off | jeita default | jeita custom [A]")

    # -- main loop ----------------------------------------------------------

    def run(self):
        print("\n>>> Charger bench console ready. Type 'help' for options. <<<\n")
        next_poll = 0.0
        while True:
            period = 0.5 if self.in_dashboard else 1.0
            now = time.monotonic()
            if now >= next_poll:
                next_poll = now + period
                try:
                    snap = self.snapshot()
                except RawReplError as err:
                    self.close_live_line()
                    print("[ERR] board call failed: %s" % err)
                    time.sleep(1.0)
                    continue
                self.print_events(snap)
                if self.in_dashboard:
                    self.print_dashboard(snap)
                elif self.mon_mode != MON_OFF and not self.typing:
                    self.print_monitor(snap)

            if not select.select([sys.stdin], [], [], 0.05)[0]:
                continue
            ch = sys.stdin.read(1)
            if not ch:
                continue
            if self.in_dashboard:
                self.in_dashboard = False
                print("\nExited dashboard. Returned to console.")
                continue
            if ch in ("\r", "\n"):
                line, self.line = self.line, ""
                self.typing = False
                self.close_live_line()
                if not self.handle(line):
                    return
            elif ch in ("\x7f", "\b"):
                if self.line:
                    self.line = self.line[:-1]
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                self.typing = bool(self.line)
            elif ch == "\x03":
                raise KeyboardInterrupt
            else:
                if not self.typing:
                    self.close_live_line()
                self.typing = True
                self.line += ch
                sys.stdout.write(ch)
                sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Charger bench console via HW Puppet")
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--push", action="store_true", help="upload the pb package before starting")
    parser.add_argument("--no-test", action="store_true", help="skip the boot self-test")
    parser.add_argument("--no-button", action="store_true", help="do not start the button watcher")
    args = parser.parse_args()

    if args.push:
        import push

        sys.argv = ["push.py", "--port", args.port, "--baud", str(args.baud)]
        if push.main() != 0:
            return 1

    try:
        repl = RawRepl(args.port, args.baud)
    except RawReplError as err:
        print("Error: %s" % err, file=sys.stderr)
        return 1

    try:
        print("Initializing charger bench...")
        res = repl.exec_json(
            "import pb, json; print(json.dumps(pb.init(start_button=%s)))"
            % (not args.no_button)
        )
        print("  pb %s on board: %s" % (res.get("version"), res))

        if not args.no_test:
            out = repl.exec_json("import pb; print(pb.selftest_json())")
            for line in out["lines"]:
                print(line)

        console = Console(repl)
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            console.run()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            print("")
    except KeyboardInterrupt:
        print("")
    except RawReplError as err:
        print("Error: %s" % err, file=sys.stderr)
        return 1
    finally:
        repl.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
