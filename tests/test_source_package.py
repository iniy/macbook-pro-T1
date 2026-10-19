#!/usr/bin/env python3
"""Verify bundled patches exactly reconstruct the pinned source, offline."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
patches = sorted((ROOT / 'patches').glob('*.patch'))
with tempfile.TemporaryDirectory() as name:
    tmp = Path(name)
    dest = tmp / 'apple-ib-drv'
    shutil.copytree(ROOT / 'driver', dest)
    for patch in reversed(patches):
        subprocess.run(['git', 'apply', '--reverse', str(patch)], cwd=tmp, check=True)
    for line in (ROOT / 'patches/UPSTREAM.sha256').read_text().splitlines():
        expected, filename = line.split(None, 1)
        assert hashlib.sha256((dest / filename).read_bytes()).hexdigest() == expected, filename
    for patch in patches:
        subprocess.run(['git', 'apply', str(patch)], cwd=tmp, check=True)
    for path in (ROOT / 'driver').iterdir():
        assert path.read_bytes() == (dest / path.name).read_bytes(), path.name
print('PASS patches reverse to pinned upstream SHA256s and reapply byte-for-byte')
