#!/usr/bin/env python3
"""Fail-closed SHA-256 verification for a downloaded age archive."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_age_artifact.py ARCHIVE SHA256")
    path = Path(sys.argv[1])
    expected = sys.argv[2].removeprefix("sha256:").lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise SystemExit("invalid SHA-256 digest")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise SystemExit(f"digest mismatch for {path.name}")
    print(f"verified {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
