#!/usr/bin/env python3
"""
Run user Python script on HW-PUPPET board (ESP32-S3)
without writing to flash memory (executes directly in RAM).
"""

import sys
import os
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial library is not installed.")
    print("Install it with: pip install pyserial")
    sys.exit(1)


def run_script_on_board(port: str, baudrate: int, script_path: str):
    if not os.path.exists(script_path):
        print(f"Error: script file not found: {script_path}")
        sys.exit(1)

    with open(script_path, "r", encoding="utf-8") as f:
        script_code = f.read()

    print(f"-> Connecting to {port}...")
    try:
        ser = serial.Serial(port, baudrate, timeout=1.0)
    except Exception as e:
        print(f"Error opening port {port}: {e}")
        sys.exit(1)

    try:
        # Switch MicroPython to Raw REPL (Ctrl-C, Ctrl-C, Ctrl-A)
        ser.reset_input_buffer()
        ser.write(b"\r\x03\x03\x01")
        time.sleep(0.1)

        raw_prompt = ser.read_until(b"raw REPL; CTRL-B to exit\r\n>")
        if not raw_prompt.endswith(b">"):
            # Retry
            ser.write(b"\r\x03\x03\x01")
            time.sleep(0.1)
            raw_prompt = ser.read_until(b">")
            if not raw_prompt.endswith(b">"):
                print("Error: MicroPython did not respond to Raw REPL prompt.")
                sys.exit(1)

        print(f"-> Uploading and executing '{script_path}' in ESP32-S3 RAM...")
        print("-" * 50)

        # Send script code and execution terminator Ctrl-D (\x04)
        ser.write(script_code.encode("utf-8") + b"\x04")

        # Read execution start confirmation 'OK'
        header = ser.read(2)
        if header != b"OK":
            print(f"Execution error (response: {header})")
            sys.exit(1)

        # Stream stdout in real time until \x04
        ser.timeout = 0.1
        stdout_buf = bytearray()
        while True:
            b = ser.read(1)
            if not b:
                continue
            if b == b"\x04":
                break
            sys.stdout.buffer.write(b)
            sys.stdout.buffer.flush()

        # Read stderr until next \x04
        stderr_buf = bytearray()
        while True:
            b = ser.read(1)
            if not b:
                continue
            if b == b"\x04":
                break
            stderr_buf.extend(b)

        # Read trailing '>'
        ser.read(1)

        print("-" * 50)
        if stderr_buf:
            err_msg = stderr_buf.decode("utf-8", errors="replace")
            print("BOARD EXECUTION ERROR:")
            print(err_msg.strip())
        else:
            print("-> Script finished successfully.")

    finally:
        # Restore normal friendly REPL (Ctrl-B)
        try:
            ser.write(b"\x02")
        except Exception:
            pass
        ser.close()


def main():
    default_port = "/dev/hw-puppet-control" if os.path.exists("/dev/hw-puppet-control") else "/dev/ttyACM0"
    parser = argparse.ArgumentParser(description="Run Python script on HW-PUPPET board (in RAM)")
    parser.add_argument("script", help="Path to script file (.py)")
    parser.add_argument("--port", default=default_port, help=f"Control port (default: {default_port})")
    parser.add_argument("--baud", type=int, default=115200, help="Port baudrate (default: 115200)")
    args = parser.parse_args()

    run_script_on_board(args.port, args.baud, args.script)


if __name__ == "__main__":
    main()
