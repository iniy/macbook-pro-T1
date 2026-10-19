#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Owned, reversible DKMS deployment. Never unload a live wireless driver."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from check import hardware
from component_support import signatures_required, transaction

ROOT = Path(__file__).resolve().parent
STATE = Path('/var/lib/macbook-t1-wifi-dma')
PACKAGE = 'macbook-t1-wifi-dma'
VERSION = '1.0.0'
SOURCE = Path('/usr/src') / (PACKAGE + '-' + VERSION)


def run(*args):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode:
        raise RuntimeError(f'{args[0]} failed ({p.returncode}): {p.stdout[-4000:]}')
    return p.stdout.strip()


def manifest(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if '__pycache__' in path.parts or 'build' in path.relative_to(directory).parts:
            continue
        if path.is_symlink():
            raise RuntimeError('Unexpected source symlink')
        if path.is_file():
            result[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def save(name, value):
    transaction().atomic(STATE / name, json.dumps(value, indent=2).encode(), 0o600)


def module_path(kernel):
    return Path(run('modinfo', '-k', kernel, '-n', 'brcmfmac')).resolve()


def owned(kernel=None):
    if not (STATE / 'complete').is_file():
        return False
    kernel = kernel or os.uname().release
    path = module_path(kernel)
    return ('/updates/dkms/' in str(path) and
            any(line.startswith(f'{PACKAGE}/{VERSION}, {kernel},') and
                line.endswith(': installed')
                for line in run('dkms', 'status', '-m', PACKAGE, '-v', VERSION).splitlines()))


def remove():
    if STATE.is_symlink() or SOURCE.is_symlink():
        raise RuntimeError('Refusing symlink installation/state')
    if not STATE.exists():
        return
    if SOURCE.exists() and manifest(SOURCE) != json.loads((STATE / 'source.json').read_text()):
        raise RuntimeError('Installed DKMS source was edited; preserve/review it before removal')
    status = run('dkms', 'status', '-m', PACKAGE, '-v', VERSION)
    kernels = set(json.loads((STATE / 'kernels.json').read_text()))
    kernels.update(re.findall(r', (7\.3\.0-\d+-generic),', status))
    if status:
        run('dkms', 'remove', '-m', PACKAGE, '-v', VERSION, '--all')
    for kernel in sorted(kernels):
        run('depmod', '-a', kernel)
        if '/updates/' in str(module_path(kernel)):
            raise RuntimeError('A non-stock module still takes precedence; inspect before reboot')
        run('update-initramfs', '-u', '-k', kernel)
    if SOURCE.exists():
        SOURCE.rename(STATE / 'retired-source')
    STATE.rename(STATE.with_name(STATE.name + '-removed-' + str(time.time_ns())))
    print('DMA DKMS module removed from disk; stock module restored. Reboot to change the live driver.')


def install(install_deps=False):
    device = hardware()
    if (device / 'revision').read_text().strip() != '0x02':
        raise RuntimeError('DMA fix was validated only on PCI revision 02')
    kernel = os.uname().release
    if not re.fullmatch(r'7\.3\.0-\d+-generic', kernel):
        raise RuntimeError('DMA fix supports Ubuntu 7.3.0 generic only')
    if STATE.is_symlink() or SOURCE.is_symlink():
        raise RuntimeError('Refusing symlink installation/state')
    if (STATE / 'complete').is_file():
        if manifest(SOURCE) != json.loads((STATE / 'source.json').read_text()):
            raise RuntimeError('Installed DKMS source was edited')
        expected = manifest(ROOT / 'dkms')
        expected.update({'patches/' + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (ROOT / 'patches').glob('*.patch')})
        if manifest(SOURCE) != expected:
            raise RuntimeError('DMA source changed; uninstall the DMA component before upgrading its version')
        if owned(kernel):
            print('DMA DKMS installation already complete for this kernel.')
            return
        raise RuntimeError('DMA module missing for this kernel; inspect DKMS build status before continuing')
    if STATE.exists() or SOURCE.exists():
        raise RuntimeError('Incomplete/unowned DMA installation; inspect state and uninstall before retrying')
    if install_deps:
        run('apt-get', 'install', '--no-remove', '-y', 'dkms', 'build-essential', 'patch',
            'linux-headers-' + kernel, 'linux-source-7.3.0', 'mokutil')
    if signatures_required():
        raise RuntimeError('Module signatures are enforced; enroll and verify a DKMS signing key before deployment')
    stock = module_path(kernel)
    if '/kernel/drivers/net/wireless/broadcom/brcm80211/brcmfmac/' not in str(stock):
        raise RuntimeError('Another brcmfmac module takes precedence; resolve it first')
    if run('modinfo', '-F', 'intree', str(stock)) != 'Y':
        raise RuntimeError('Expected a packaged stock brcmfmac module')
    STATE.mkdir(mode=0o700)
    save('kernels.json', [kernel])
    save('stock.json', {'path': str(stock), 'sha256': hashlib.sha256(stock.read_bytes()).hexdigest()})
    initrd = Path('/boot/initrd.img-' + kernel)
    shutil.copy2(initrd, STATE / initrd.name)
    shutil.copytree(ROOT / 'dkms', SOURCE, ignore=shutil.ignore_patterns('build', '__pycache__'))
    shutil.copytree(ROOT / 'patches', SOURCE / 'patches')
    save('source.json', manifest(SOURCE))
    try:
        run('dkms', 'add', '-m', PACKAGE, '-v', VERSION)
        run('dkms', 'build', '-m', PACKAGE, '-v', VERSION, '-k', kernel)
        modules = Path('/var/lib/dkms') / PACKAGE / VERSION / kernel / 'x86_64/module'
        candidates = [p for p in modules.glob('brcmfmac.ko*') if p.name in
                      ('brcmfmac.ko', 'brcmfmac.ko.zst', 'brcmfmac.ko.xz', 'brcmfmac.ko.gz')]
        if len(candidates) != 1:
            raise RuntimeError('Expected exactly one built brcmfmac module')
        built = candidates[0]
        if run('modinfo', '-F', 'vermagic', str(built)).split()[0] != kernel:
            raise RuntimeError('Built module ABI does not match running kernel')
        run('dkms', 'install', '-m', PACKAGE, '-v', VERSION, '-k', kernel)
        run('depmod', '-a', kernel)
        if '/updates/dkms/' not in str(module_path(kernel)):
            raise RuntimeError('DKMS module is not selected by modprobe')
        run('update-initramfs', '-u', '-k', kernel)
        (STATE / 'complete').touch(mode=0o600)
    except BaseException:
        try:
            remove()
        except BaseException as rollback_error:
            raise RuntimeError('DMA installation failed; rollback needs attention: ' + str(rollback_error))
        raise
    print('DMA fix installed for next boot. The live driver was not unloaded.')
