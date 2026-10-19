#!/usr/bin/env python3
"""Prepare the CS8409 module from the exact Ubuntu kernel's HDA source."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
KERNEL_FILES = [
    'codecs/cirrus/cs8409.c', 'codecs/cirrus/cs8409.h',
    'codecs/cirrus/cs8409-tables.c', 'codecs/generic.h',
    'codecs/side-codecs/hda_component.h', 'common/hda_local.h',
    'common/hda_auto_parser.h', 'common/hda_jack.h',
]


def source_version(kernel):
    if not re.fullmatch(r'7\.3\.0-\d+-generic', kernel):
        raise RuntimeError('Audio supports audited Ubuntu 7.3.0 generic kernels only')
    headers = Path('/lib/modules') / kernel / 'build'
    if (headers / 'include/config/kernel.release').read_text().strip() != kernel:
        raise RuntimeError('Exact matching kernel headers are required')
    return subprocess.check_output(
        ['dpkg-query', '-W', '-f=${source:Version}', 'linux-headers-' + kernel], text=True).strip()


def prepare(kernel):
    version = source_version(kernel)
    for name, expected in json.loads((ROOT / 'SOURCE-SHA256.json').read_text()).items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Source integrity failure: ' + name)
    build = ROOT / 'build'
    if build.is_symlink():
        raise RuntimeError('Refusing symlink build directory')
    if build.exists():
        shutil.rmtree(build)
    build.mkdir()
    bundled = ROOT / 'kernel-source' / version
    if bundled.is_dir():
        for name in KERNEL_FILES:
            target = build / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled / name, target)
    else:
        installed = subprocess.check_output(
            ['dpkg-query', '-W', '-f=${Version}', 'linux-source-7.3.0'], text=True).strip()
        if installed != version:
            raise RuntimeError(f'Install linux-source-7.3.0={version}; refusing mismatched HDA structures')
        with tarfile.open('/usr/src/linux-source-7.3.0.tar.bz2', 'r:bz2') as archive:
            for name in KERNEL_FILES:
                member = archive.getmember('linux-source-7.3.0/sound/hda/' + name)
                if not member.isfile():
                    raise RuntimeError('Unexpected kernel source member')
                target = build / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    for header in (ROOT / 'upstream').glob('*.h'):
        shutil.copy2(header, build / 'codecs/cirrus' / header.name)
    for patch in sorted((ROOT / 'patches').glob('*.patch')):
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=build, check=True)
    for relative in ['Makefile', 'codecs/Makefile', 'codecs/cirrus/Makefile']:
        shutil.copy2(ROOT / 'kbuild' / relative, build / relative)
    (build / 'SOURCE-VERSION').write_text(version + '\n')
    print('Prepared exact Ubuntu HDA source:', version, 'for', kernel)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: prepare.py KERNEL')
    try:
        prepare(sys.argv[1])
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
