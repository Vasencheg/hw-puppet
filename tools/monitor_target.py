#!/usr/bin/env python3
"""
Target console monitor for HW-PUPPET (CDC 1).
Reads UART stream forwarded from the target board.
"""

import os
import sys
import time
import argparse

try:
    import serial
except ImportError:
    print("Error: pyserial is not installed. Run: pip install pyserial")
    sys.exit(1)


def main():
    default_port = "/dev/hw-puppet-uart" if os.path.exists("/dev/hw-puppet-uart") else "/dev/ttyACM1"
    parser = argparse.ArgumentParser(description="Target UART Monitor for HW-PUPPET")
    parser.add_argument("--port", default=default_port, help=f"Serial port (default: {default_port})")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    args = parser.parse_args()

    print(f"[MONITOR] Opening {args.port} at {args.baud} baud...", flush=True)
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
        print(f"[MONITOR] Listening on {args.port}... Ready for target output (Ctrl+C to stop)!", flush=True)
        while True:
            data = ser.read(ser.in_waiting or 1)
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.flush()
            else:
                time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n[MONITOR] Stopped.", flush=True)
    except Exception as e:
        print(f"[MONITOR] Error: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
