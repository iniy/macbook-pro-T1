#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild exact Ubuntu brcmfmac with the scoped RX DMA repair and load diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'dkms'))
import prepare


def stage(destination, kernel):
    prepare.source_version(kernel)  # Reject a mismatched ABI before copying anything.
    destination.mkdir(mode=0o755, parents=True, exist_ok=False)
    shutil.copytree(ROOT / 'dkms', destination / 'source',
                    ignore=shutil.ignore_patterns('build', '__pycache__'))
    source = destination / 'source'
    shutil.copytree(ROOT / 'patches', source / 'patches')
    manifest = json.loads((source / 'SOURCE-SHA256.json').read_text())
    for patch in (ROOT / '5ghz/patches').glob('*.patch'):
        name = 'patches/' + patch.name
        shutil.copy2(patch, source / name)
        manifest[name] = hashlib.sha256((source / name).read_bytes()).hexdigest()
    (source / 'SOURCE-SHA256.json').write_text(json.dumps(manifest, indent=2))
    return source


def build(destination, kernel):
    source = stage(destination, kernel)
    subprocess.run(['make', '-j2', 'KVERSION=' + kernel], cwd=source, check=True)
    module = source / 'build/brcmfmac/brcmfmac.ko'
    abi = subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).split()[0]
    if abi != kernel:
        raise RuntimeError('Built module ABI mismatch')
    subprocess.run(['modinfo', '-F', 'parm', str(module)], check=True)
    print('Built only; no driver or firmware installed:', module)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the repository')
    parser.add_argument('--kernel', default=__import__('os').uname().release)
    args = parser.parse_args()
    build(args.output.resolve(), args.kernel)
