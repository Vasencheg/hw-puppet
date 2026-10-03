#!/usr/bin/env python3
"""
Host client example for HW-PUPPET MicroPython.
Demonstrates sending exec() commands via CDC 0.
"""

import os
import serial
import json
import time
import sys


class HWPuppetClient:
    def __init__(self, control_port: str, baudrate: int = 115200, timeout: float = 3.0):
        self.ser = serial.Serial(control_port, baudrate, timeout=timeout)
        time.sleep(0.1)
        self._enter_raw_repl()

    def _enter_raw_repl(self):
        """Switch MicroPython into Raw REPL mode."""
        self.ser.reset_input_buffer()
        # Send Ctrl-C (interrupt), then Ctrl-A (enter raw REPL)
        self.ser.write(b"\r\x03\x03\x01")
        time.sleep(0.1)
        data = self.ser.read_until(b"raw REPL; CTRL-B to exit\r\n>")
        if not data.endswith(b">"):
            # Retry
            self.ser.write(b"\r\x03\x03\x01")
            time.sleep(0.1)
            self.ser.read_until(b">")
        self.ser.reset_input_buffer()

    def exec(self, code: str) -> dict:
        """Execute Python code on board and return result."""
        self.ser.reset_input_buffer()
        # Code is sent in raw bytes terminated with Ctrl-D (\x04)
        self.ser.write(code.encode("utf-8") + b"\x04")

        # MicroPython raw REPL response format: 'OK' + stdout + \x04 + stderr + \x04>
        header = self.ser.read(2)
        if header != b"OK":
            self._enter_raw_repl()
            return {"ok": False, "error": f"Failed to execute (header: {header})"}

        stdout_bytes = self.ser.read_until(b"\x04")[:-1]
        stderr_bytes = self.ser.read_until(b"\x04")[:-1]
        self.ser.read(1)  # Read trailing '>' character

        out_str = stdout_bytes.decode("utf-8", errors="replace").strip()
        err_str = stderr_bytes.decode("utf-8", errors="replace").strip()

        if err_str:
            return {"ok": False, "error": err_str, "stdout": out_str}

        # If output is valid JSON, parse it
        try:
            return json.loads(out_str)
        except Exception:
            # Otherwise return structured payload
            return {"ok": True, "stdout": out_str, "result": out_str}

    def gpio_write(self, pin: int, state: bool) -> dict:
        return self.exec(f"from machine import Pin; p = Pin({pin}, Pin.OUT); p.value({int(state)}); print({{\"ok\": True, \"pin\": {pin}, \"val\": {int(state)}}})")

    def gpio_read(self, pin: int) -> dict:
        return self.exec(f"from machine import Pin; p = Pin({pin}, Pin.IN); print({{\"ok\": True, \"pin\": {pin}, \"val\": p.value()}})")

    def gpio_pulse(self, pin: int, duration_ms: int, active_low: bool = True) -> dict:
        active = 0 if active_low else 1
        idle = 1 if active_low else 0
        code = f"""
from machine import Pin
import time
p = Pin({pin}, Pin.OUT, value={idle})
p.value({active})
time.sleep_ms({duration_ms})
p.value({idle})
print({{"ok": True, "pin": {pin}, "pulse_ms": {duration_ms}}})
"""
        return self.exec(code)

    def reset_target(self, reset_pin: int = 4, duration_ms: int = 100) -> dict:
        """Full target reset cycle."""
        return self.gpio_pulse(reset_pin, duration_ms, active_low=True)

    def close(self):
        try:
            # Exit raw REPL back to friendly REPL (Ctrl-B)
            self.ser.write(b"\x02")
        except Exception:
            pass
        self.ser.close()


def main():
    import argparse
    default_port = "/dev/hw-puppet-control" if os.path.exists("/dev/hw-puppet-control") else "/dev/ttyACM0"
    parser = argparse.ArgumentParser(description="HW-PUPPET Raw REPL Host Client")
    parser.add_argument("--port", default=default_port, help=f"CDC 0 control port (default: {default_port})")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    client = HWPuppetClient(args.port, args.baud)

    try:
        # Examples
        print("=== GPIO write ===")
        r = client.gpio_write(4, True)
        print(json.dumps(r, indent=2))

        print("\n=== GPIO read ===")
        r = client.gpio_read(4)
        print(json.dumps(r, indent=2))

        print("\n=== GPIO pulse ===")
        r = client.gpio_pulse(5, 200)
        print(json.dumps(r, indent=2))

        print("\n=== Custom Python exec ===")
        r = client.exec("import machine; print('CPU freq:', machine.freq())")
        print(json.dumps(r, indent=2))

    finally:
        client.close()


if __name__ == "__main__":
    main()