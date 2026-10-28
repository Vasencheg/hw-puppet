"""Fingerprint of the pb package sources.

Both uploaders (push.py and the ae-hw-bridge target) write the fingerprint of
what they uploaded into `_stamp.py` next to the package on the board. Comparing
it against the repository tells us whether the board is running current code,
so a forgotten upload cannot leave an agent talking to a stale driver.
"""

import hashlib
import os

STAMP_FILE = "_stamp.py"


def source_stamp(pkg_dir):
    """Short digest over every .py source in the package, name and content.

    `_stamp.py` itself is generated at upload time and never part of the digest.
    """
    digest = hashlib.sha256()
    for name in sorted(f for f in os.listdir(pkg_dir) if f.endswith(".py")):
        if name == STAMP_FILE:
            continue
        with open(os.path.join(pkg_dir, name), "rb") as fh:
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(fh.read())
            digest.update(b"\0")
    return digest.hexdigest()[:12]


def stamp_source(stamp):
    """Contents of the _stamp.py written onto the board."""
    return 'STAMP = "%s"\n' % stamp
