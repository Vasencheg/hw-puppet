#!/usr/bin/env python3
"""Upload the pb package to a HW Puppet board.

    ./push.py                 # copy hw-puppet/device/pb -> /lib/pb on the board
    ./push.py --ram           # no upload, just check that the package imports
"""

import argparse
import os
import sys

from pkgstamp import STAMP_FILE, source_stamp, stamp_source
from rawrepl import DEFAULT_PORT, RawRepl, RawReplError

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.join(os.path.dirname(HERE), "device", "pb")
REMOTE_DIR = "/lib/pb"


def main():
    parser = argparse.ArgumentParser(description="Upload pb package to HW Puppet")
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--remote", default=REMOTE_DIR)
    parser.add_argument("--no-verify", action="store_true", help="skip the import check")
    args = parser.parse_args()

    files = sorted(
        f for f in os.listdir(PKG_DIR) if f.endswith(".py") and f != STAMP_FILE
    )
    if not files:
        print("No .py files found in %s" % PKG_DIR)
        return 1

    try:
        with RawRepl(args.port, args.baud) as repl:
            repl.makedirs(args.remote)
            for name in files:
                size = repl.put_file(os.path.join(PKG_DIR, name), "%s/%s" % (args.remote, name))
                print("  -> %-14s %5d bytes" % (name, size))
            stamp = source_stamp(PKG_DIR)
            repl.exec_(
                "f = open(%r, 'w')\nf.write(%r)\nf.close()"
                % ("%s/%s" % (args.remote, STAMP_FILE), stamp_source(stamp))
            )
            print("  -> %-14s %s" % (STAMP_FILE, stamp))
            if not args.no_verify:
                out = repl.exec_("import pb; print(pb.VERSION)").strip()
                print("Board imports pb %s from %s" % (out, args.remote))
    except RawReplError as err:
        print("Error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
