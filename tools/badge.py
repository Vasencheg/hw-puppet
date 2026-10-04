#!/usr/bin/env python3
"""
Inspect, set, or clear the hardware badge on an HW-PUPPET board (ESP32-S3).

Communicates with MicroPython Raw REPL over CDC 0 to read/write persistent NVS badge.
"""

import sys
import os
import time
import argparse
import glob

try:
    import serial
except ImportError:
    print("Error: pyserial library is not installed.")
    print("Install it with: pip install pyserial")
    sys.exit(1)


def find_default_port() -> str:
    if os.path.exists("/dev/hw-puppet-control"):
        return "/dev/hw-puppet-control"
    candidates = sorted(glob.glob("/dev/ttyACM*"))
    return candidates[0] if candidates else "/dev/ttyACM0"


def execute_rpc(port: str, baudrate: int, code: str) -> str:
    try:
        ser = serial.Serial(port, baudrate, timeout=1.5)
    except Exception as e:
        print(f"Error opening port {port}: {e}")
        sys.exit(1)

    try:
        # Enter Raw REPL (Ctrl-C, Ctrl-C, Ctrl-A)
        ser.reset_input_buffer()
        ser.write(b"\r\x03\x03\x01")
        time.sleep(0.1)

        raw_prompt = ser.read_until(b"raw REPL; CTRL-B to exit\r\n>")
        if not raw_prompt.endswith(b">"):
            ser.write(b"\r\x03\x03\x01")
            time.sleep(0.1)
            raw_prompt = ser.read_until(b">")
            if not raw_prompt.endswith(b">"):
                print("Error: MicroPython did not respond to Raw REPL prompt.")
                sys.exit(1)

        ser.write(code.encode("utf-8") + b"\x04")

        header = ser.read(2)
        if header != b"OK":
            print(f"Execution error (response header: {header})")
            sys.exit(1)

        stdout_buf = bytearray()
        while True:
            b = ser.read(1)
            if not b or b == b"\x04":
                break
            stdout_buf.extend(b)

        stderr_buf = bytearray()
        while True:
            b = ser.read(1)
            if not b or b == b"\x04":
                break
            stderr_buf.extend(b)

        ser.read(1)  # trailing '>'

        if stderr_buf:
            err_msg = stderr_buf.decode("utf-8", errors="replace").strip()
            print(f"Error on board: {err_msg}")
            sys.exit(1)

        return stdout_buf.decode("utf-8", errors="replace").strip()

    finally:
        try:
            ser.write(b"\x02")  # Exit Raw REPL
        except Exception:
            pass
        ser.close()


def main():
    parser = argparse.ArgumentParser(description="Inspect or set persistent HW-PUPPET badge name")
    parser.add_argument("--port", default=find_default_port(), help=f"Control port CDC 0 (default: {find_default_port()})")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate (default: 115200)")
    parser.add_argument("--set", dest="new_badge", metavar="NAME", help="Set badge name in persistent NVS storage")
    parser.add_argument("--clear", action="store_true", help="Clear current badge name from NVS")
    args = parser.parse_args()

    if args.clear:
        code = "import hw_puppet; hw_puppet.set_badge(''); print('OK')"
        execute_rpc(args.port, args.baud, code)
        print(f"[{args.port}] Badge cleared.")
        return

    if args.new_badge is not None:
        new_val = args.new_badge.strip()
        code = f"import hw_puppet; hw_puppet.set_badge({repr(new_val)}); print(hw_puppet.get_badge())"
        result = execute_rpc(args.port, args.baud, code)
        print(f"[{args.port}] Badge successfully set to: '{result}'")
        return

    # Default action: read badge and info
    code = """
import hw_puppet
badge = hw_puppet.get_badge()
info = hw_puppet.info()
print(f"BADGE:{badge}")
print(f"VERSION:{info.get('version', 'unknown')}")
print(f"PLATFORM:{info.get('platform', 'ESP32-S3')}")
"""
    out = execute_rpc(args.port, args.baud, code)
    badge = ""
    version = ""
    platform = ""
    for line in out.splitlines():
        if line.startswith("BADGE:"):
            badge = line[len("BADGE:"):]
        elif line.startswith("VERSION:"):
            version = line[len("VERSION:"):]
        elif line.startswith("PLATFORM:"):
            platform = line[len("PLATFORM:"):]

    print(f"Device at {args.port}:")
    print(f"  Badge    : {badge if badge else '<not set>'}")
    print(f"  Version  : {version}")
    print(f"  Platform : {platform}")


if __name__ == "__main__":
    main()
