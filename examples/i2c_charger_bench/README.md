# I2C Charger Bench

A worked example where HW Puppet is the **I2C master**, not a reset-and-console
driver. The board under test has no UART at all: everything — telemetry,
configuration, a long-press power button — happens over one I2C bus.

The bench reads a Linear LTC4162-L battery charger, a PCA9536 GPIO expander and
an LM75B temperature sensor, and exposes them as named actions to an AI agent
through [`ae-hw-bridge`](https://github.com/Vasencheg/ae-hw-bridge).

## What makes this example different

The other examples in this directory are single scripts that pulse a pin and
watch the console. This one shows two patterns that scale to a real bench:

**1. A resident MicroPython package instead of code pushed per call.**
`device/pb` lives in `/lib/pb` on the puppet. It keeps state the host cannot:
a 25 ms soft-timer watching a button for a five-second hold, and the charger
settings that have to be replayed after the chip resets itself. A function
shipped over the wire per call cannot hold a timer between calls.

**2. Deployment that cannot go stale.**
Every uploader writes `_stamp.py` beside the package, holding a digest of the
sources it uploaded. Before any action the target compares that digest against
the files on disk and re-uploads when they differ. Edit a driver, call any
action, and the board is already running the new code — no deploy step to
forget, and no silent reading of a stale driver.

Re-uploading stops the running watcher *before* swapping the modules: its soft
timer holds a reference to the old callback and would otherwise keep polling
the bus through a lock the reloaded package knows nothing about, with the two
cutting into each other's transactions. It is brought back afterwards with the
settings it had.

## Wiring

| HW Puppet | Board under test | Note |
|---|---|---|
| GPIO5 | SDA | 100 kHz, pull-ups on the target board |
| GPIO4 | SCL | |
| GND | GND | mandatory common reference |

HW Puppet reserves only GPIO43/44 for its UART bridge, so the I2C pins are
free. The UART bridge simply goes unused here.

Devices: LTC4162-L at 0x68, PCA9536 at 0x41, LM75B at 0x49. Sense resistors in
`device/pb/ltc4162.py` are 16 mR (charge current) and 7 mR (input current) —
change them, and `DEFAULT_CELLS`, to match your own board.

## Layout

```
i2c_charger_bench/
  device/pb/          MicroPython package, resident in /lib/pb on the puppet
    i2cbus.py         shared I2C master, bus scan, locking
    lm75b.py          temperature sensor
    pca9536.py        GPIO expander: LED power, button, detect switch
    ltc4162.py        charger: telemetry, JEITA, ship mode
    btnpwr.py         soft-timer button watcher
    __init__.py       init(), snapshot_json(), selftest_json(), helpers
  host/
    rawrepl.py        Raw REPL client for CDC 0 (pyserial optional)
    pkgstamp.py       source fingerprint, shared by both uploaders
    push.py           upload device/pb -> /lib/pb
    pbtest.py         interactive console: live line, table, dashboard
  targets/            not used by HW Puppet itself, see below
    charger/
      target.py       ae-hw-bridge target definition
```

The first two directories are all you need to use the bench from a terminal.
`targets/` is for the ae-hw-bridge integration and is explained next.

## Running it standalone

No dependencies: `rawrepl.py` uses `pyserial` when installed and falls back to
a small stdlib tty backend otherwise.

```bash
cd host
./push.py              # copy device/pb -> /lib/pb on the puppet
./pbtest.py            # init, self-test, then a live monitor
./pbtest.py --push     # both at once
```

Console commands: `help`, `status`, `dash`, `live`, `table`, `mon off`, `test`,
`scan`, `ship`, `disarm`, `hold [ms]`, `jeita [on|off|default|custom A]`,
`led on|off`, `quit`.

Only one process can hold `/dev/ttyACM0`. If the `ae-hw-bridge` daemon is
running, stop it before using the console, or drive the bench through the
bridge instead.

## The `targets/` directory

`targets/charger/target.py` is **not** part of HW Puppet. It belongs to
[`ae-hw-bridge`](https://github.com/Vasencheg/ae-hw-bridge), the host gateway
that exposes a bench to AI agents over MCP. The bridge discovers target
definitions in a project's own `.ae-hw-bridge/targets/<name>/target.py`, where
the directory name becomes the target name and every public method becomes a
tool the agent can call. See the bridge's
[target development guide](https://github.com/Vasencheg/ae-hw-bridge/blob/main/docs/target_development.md)
for the full contract.

The copy here is shipped so the example is complete: it shows what a target
looks like for a bus-only board, and it is what turns the twelve actions below
into agent tools. Using the bench standalone, you can ignore the directory.

To wire it into a project, copy the whole `charger/` directory across — its
name is the target name:

```bash
mkdir -p my-project/.ae-hw-bridge/targets
cp -r examples/i2c_charger_bench/targets/charger my-project/.ae-hw-bridge/targets/
```

`target.py` finds `device/` and `host/` by walking up from its own location,
which works as shipped. Once copied into a project the bench files are usually
elsewhere, so point it at them:

```bash
export I2C_CHARGER_BENCH_DIR=/path/to/i2c_charger_bench
```

Then bind the target to the puppet in `.ae-hw-bridge/config.yml`:

```yaml
targets:
  charger:
    puppet: charger-bench      # badge set with: ae-hw-bridge label charger-bench
    # port: /dev/ttyACM0       # or bind by port, which needs no NVS write
```

A badge survives replugging; `/dev/ttyACM*` does not.

```bash
ae-hw-bridge actions
ae-hw-bridge call selftest --json
ae-hw-bridge call status
ae-hw-bridge call read_register ltc4162 0x39
ae-hw-bridge call jeita custom amps=1.2
```

| Action | What it does |
|---|---|
| `deploy` | upload the package (runs by itself when the board is behind) |
| `init` | bring up the bus, the three devices and the button watcher |
| `status` | full snapshot; temperatures in both degC and degF |
| `selftest` | four-phase suite, puppet status LED green or red on the result |
| `scan_i2c` | bus scan with the expected-device verdict |
| `read_register` | raw register from `ltc4162`, `pca9536` or `lm75b` |
| `set_led` | the expander's output line |
| `set_button_hold` | read or change the long-press duration |
| `jeita` | `show` / `on` / `off` / `default` / `custom` |
| `disarm_ship_mode` | clear reg 0x19 |
| `arm_ship_mode` | powers the board down; refuses unless `confirm=True` |
| `check_alive` | puppet reachable, package deployed, watcher running |

The CLI prints scalar fields only, so multi-line results (`report`) and lists
(`lines`) need `--json`. Over MCP the agent receives the whole dict either way.

## Raw access

Anything the actions do not cover is one `exec` away, because the package is
just a module on the board:

```python
import pb; print(pb.snapshot_json())
import pb; print(hex(pb.ltc4162.read_reg(0x39)))
import pb; pb.i2cbus.write_byte(0x41, 0x01, 0x01)
```

## Notes worth copying into your own bench

* **No sentinel numbers.** A reading that could not be taken is `None` on the
  board and a dash on screen. A `-1.00` in a telemetry column looks like a
  measurement and will eventually be read as one.
* **The watcher never prints.** The board is driven over the Raw REPL, where
  stray output corrupts the protocol framing. Background events go into a ring
  buffer that `snapshot()` hands to the host, which prints them.
* **Bus access is serialized.** The watcher takes the same lock as the
  telemetry reads; a tick that cannot get the lock is skipped rather than
  cutting into a transaction in progress.
* **Charger registers are re-applied, not assumed.** The LTC4162 drops every
  setting across a ship mode cycle, and the puppet does not reboot with the
  board, so each snapshot checks one bit and replays the configuration if it is
  gone.

## Verified on

HW Puppet firmware v0.3.0 (MicroPython 1.29.0, ESP32-S3) against a live
LTC4162-L board: full self-test suite, live telemetry during charge, and
auto-deploy exercised in both directions while the button watcher stayed up.
