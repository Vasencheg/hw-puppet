#!/usr/bin/env python3
"""Minimal MicroPython Raw REPL client for HW Puppet CDC 0.

Protocol (see hw-puppet examples/host_client.py):
  enter   -> b"\\r\\x03\\x03\\x01", board answers "raw REPL; CTRL-B to exit\\r\\n>"
  execute -> code + b"\\x04"
  answer  -> b"OK" + stdout + b"\\x04" + stderr + b"\\x04>"
"""

import base64
import json
import os
import time

try:
    import serial
except ImportError:  # pyserial is optional, see TtyPort below
    serial = None

DEFAULT_PORT = (
    "/dev/hw-puppet-control" if os.path.exists("/dev/hw-puppet-control") else "/dev/ttyACM0"
)


class TtyPort:
    """Minimal stdlib stand-in for serial.Serial, enough for the Raw REPL.

    The CDC ACM endpoint ignores the line settings, but the tty still has to be
    put in raw mode or the kernel would eat the control characters the Raw REPL
    protocol is built from.
    """

    def __init__(self, port, baudrate=115200, timeout=5.0):
        import termios

        self.timeout = timeout
        self._buf = b""
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
        attrs = termios.tcgetattr(self.fd)
        cc = list(attrs[6])
        cc[termios.VMIN] = 0
        cc[termios.VTIME] = 0
        speed = getattr(termios, "B%d" % baudrate, termios.B115200)
        cflag = termios.CS8 | termios.CREAD | termios.CLOCAL
        termios.tcsetattr(self.fd, termios.TCSANOW, [0, 0, cflag, 0, speed, speed, cc])
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def _fill(self, deadline):
        """Append one chunk from the port to the buffer. False means timeout."""
        import select

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        if not select.select([self.fd], [], [], remaining)[0]:
            return False
        chunk = os.read(self.fd, 4096)
        if not chunk:
            return False
        self._buf += chunk
        return True

    def read(self, size=1):
        deadline = time.monotonic() + self.timeout
        while len(self._buf) < size:
            if not self._fill(deadline):
                break
        out, self._buf = self._buf[:size], self._buf[size:]
        return out

    def read_until(self, expected):
        deadline = time.monotonic() + self.timeout
        while True:
            idx = self._buf.find(expected)
            if idx >= 0:
                cut = idx + len(expected)
                out, self._buf = self._buf[:cut], self._buf[cut:]
                return out
            if not self._fill(deadline):
                out, self._buf = self._buf, b""
                return out

    def write(self, data):
        written = 0
        while written < len(data):
            written += os.write(self.fd, data[written:])
        return written

    def reset_input_buffer(self):
        import termios

        self._buf = b""
        termios.tcflush(self.fd, termios.TCIFLUSH)

    def close(self):
        os.close(self.fd)


class RawReplError(RuntimeError):
    pass


class RawRepl:
    def __init__(self, port=DEFAULT_PORT, baudrate=115200, timeout=5.0):
        try:
            if serial is not None:
                self.ser = serial.Serial(port, baudrate, timeout=timeout)
            else:
                self.ser = TtyPort(port, baudrate, timeout)
        except Exception as err:
            raise RawReplError(
                "cannot open %s: %s\n"
                "If ae-hw-bridge is running it holds this port; stop the daemon "
                "or drive the board through its MCP exec tool instead." % (port, err)
            )
        time.sleep(0.1)
        self.enter()

    def enter(self):
        self.ser.reset_input_buffer()
        self.ser.write(b"\r\x03\x03\x01")
        time.sleep(0.1)
        data = self.ser.read_until(b"raw REPL; CTRL-B to exit\r\n>")
        if not data.endswith(b">"):
            self.ser.write(b"\r\x03\x03\x01")
            time.sleep(0.1)
            data = self.ser.read_until(b">")
            if not data.endswith(b">"):
                raise RawReplError("board did not answer the Raw REPL prompt")
        self.ser.reset_input_buffer()

    def exec_(self, code):
        """Run code on the board, return stdout. Raises on a board exception."""
        self.ser.reset_input_buffer()
        self.ser.write(code.encode("utf-8") + b"\x04")

        header = self.ser.read(2)
        if header != b"OK":
            self.enter()
            raise RawReplError("execution refused (header %r)" % header)

        stdout = self.ser.read_until(b"\x04")[:-1]
        stderr = self.ser.read_until(b"\x04")[:-1]
        self.ser.read(1)  # trailing '>'

        err = stderr.decode("utf-8", "replace").strip()
        if err:
            raise RawReplError(err)
        return stdout.decode("utf-8", "replace")

    def exec_json(self, code):
        out = self.exec_(code).strip()
        if not out:
            raise RawReplError("no output from: %s" % code)
        return json.loads(out.splitlines()[-1])

    def makedirs(self, path):
        self.exec_(
            "import os\n"
            "p = ''\n"
            "for part in %r.split('/'):\n"
            "    if not part:\n"
            "        continue\n"
            "    p += '/' + part\n"
            "    try:\n"
            "        os.mkdir(p)\n"
            "    except OSError:\n"
            "        pass\n" % path
        )

    def put_file(self, local_path, remote_path, chunk=512):
        """Upload a file to the board filesystem, base64 framed."""
        with open(local_path, "rb") as fh:
            data = fh.read()
        self.exec_("import ubinascii\nf = open(%r, 'wb')" % remote_path)
        for off in range(0, len(data), chunk):
            blob = base64.b64encode(data[off : off + chunk]).decode("ascii")
            self.exec_("f.write(ubinascii.a2b_base64(%r))" % blob)
        self.exec_("f.close()")
        return len(data)

    def close(self):
        try:
            self.ser.write(b"\x02")  # back to the friendly REPL
        except Exception:
            pass
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
