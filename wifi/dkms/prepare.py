#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build from exact Ubuntu source; never reuse an older kernel's private ABI."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent


def source_version(kernel):
    if not re.fullmatch(r'7\.3\.0-\d+-generic', kernel):
        raise RuntimeError('DMA fix supports audited Ubuntu 7.3.0 generic kernels only')
    headers = Path('/lib/modules') / kernel / 'build'
    if (headers / 'include/config/kernel.release').read_text().strip() != kernel:
        raise RuntimeError('Exact matching kernel headers required')
    return subprocess.check_output(['dpkg-query', '-W', '-f=${source:Version}',
                                    'linux-headers-' + kernel], text=True).strip()


def verify_sources():
    expected = json.loads((ROOT / 'SOURCE-SHA256.json').read_text())
    actual = {str(p.relative_to(ROOT)) for p in (ROOT / 'kernel-source').rglob('*') if p.is_file()}
    actual |= {str(p.relative_to(ROOT)) for p in (ROOT / 'patches').glob('*.patch')}
    if actual != set(expected):
        raise RuntimeError('Unexpected or missing source files')
    for name, digest in expected.items():
        path = ROOT / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Source integrity failure: ' + name)


def prepare(kernel):
    version = source_version(kernel)
    verify_sources()
    build = ROOT / 'build'
    if build.is_symlink():
        raise RuntimeError('Refusing symlink build directory')
    if build.exists():
        shutil.rmtree(build)
    bundled = ROOT / 'kernel-source' / version
    if bundled.is_dir():
        shutil.copytree(bundled, build)
    else:
        installed = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}',
                                             'linux-source-7.3.0'], text=True).strip()
        if installed != version:
            raise RuntimeError(f'Install linux-source-7.3.0={version}; refusing mismatched brcmfmac ABI')
        prefix = 'linux-source-7.3.0/drivers/net/wireless/broadcom/brcm80211/'
        with tarfile.open('/usr/src/linux-source-7.3.0.tar.bz2', 'r:bz2') as archive:
            for member in archive:
                if not member.name.startswith(prefix):
                    continue
                relative = Path(member.name[len(prefix):])
                if not relative.parts or relative.parts[0] not in ('brcmfmac', 'include'):
                    continue
                if relative.is_absolute() or '..' in relative.parts or not (member.isfile() or member.isdir()):
                    raise RuntimeError('Unsafe kernel source member')
                if member.isfile():
                    target = build / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
    for patch in sorted((ROOT / 'patches').glob('*.patch')):
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=build, check=True)
    (build / 'Makefile').write_text('# SPDX-License-Identifier: ISC\nobj-m += brcmfmac/\n')
    (build / 'SOURCE-VERSION').write_text(version + '\n')
    print('Prepared exact Ubuntu brcmfmac source:', version, 'for', kernel)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: prepare.py KERNEL')
    try:
        prepare(sys.argv[1])
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
