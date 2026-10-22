# SPDX-License-Identifier: MIT
"""Persistent selection of the isolated T1 image, with the normal Ubuntu fallback."""
import grp
import json
import os
from pathlib import Path
import platform
import pwd
import re
import stat
import subprocess
import tempfile

import trial
from build import digest
from deploy import verify
from transaction import Transaction, atomic, safe

ENTRY = 'macbook-t1-touchid'
DROPIN = 'etc/default/grub.d/zz-macbook-t1-touchid.cfg'
GENERATOR = 'etc/grub.d/42_macbook_t1_touchid'
MENU = 'boot/grub/grub.cfg'
OWNED = {GENERATOR, DROPIN, MENU}
DEFAULTS = (f'GRUB_DEFAULT="{ENTRY}"\n'
            'GRUB_SAVEDEFAULT=false\nGRUB_TIMEOUT_STYLE=menu\nGRUB_TIMEOUT=5\n')


def configured(root=Path('/')):
    path = root / DROPIN
    return path.is_file() and DEFAULTS in path.read_text()


def validate_files(tx):
    for item in tx.entries:
        path = tx.target(item['name'])
        if (not path.is_file() or digest(path) != item['sha256']
                or stat.S_IMODE(path.stat().st_mode) != item['mode']):
            raise RuntimeError('Managed Touch ID file changed; preserving it: ' + item['name'])


def validate_menu(text, entry):
    if f'set default="{ENTRY}"' not in text or text.count(f"--id '{ENTRY}'") != 1:
        raise RuntimeError('Generated GRUB menu does not select Touch ID exactly once')
    if not re.search(r"^menuentry ['\"]Ubuntu['\"]", text, re.M):
        raise RuntimeError('Normal Ubuntu fallback entry is missing')
    if entry not in text:
        raise RuntimeError('Generated menu changed the verified Touch ID boot command')


def enable(user, root=Path('/'), state=None):
    """Reuse staged files; never enroll, delete templates or switch live drivers."""
    state = state or trial.STATE
    target = lambda name: safe(root / name.lstrip('/'))
    if os.geteuid() != 0:
        raise RuntimeError('Persistent boot selection requires root')
    meta = json.loads((state / 'state.json').read_text())
    if meta['phase'] not in ('armed', 'staged') or meta['user'] != user or meta['kernel'] != platform.release():
        raise RuntimeError('Staged Touch ID account/kernel does not match; existing state preserved')
    tx = Transaction(state / 'files', root)
    validate_files(tx)
    manifest = verify(target(str(trial.PREFIX)))
    if manifest.get('kernel') != meta['kernel'] or not manifest.get('tests_requested'):
        raise RuntimeError('Require the verified bundle built for this kernel')
    account = pwd.getpwnam(user)
    if grp.getgrnam('t1bridge').gr_gid not in os.getgrouplist(user, account.pw_gid):
        raise RuntimeError('Selected account lacks T1Bridge access')

    marker = state / 'persistent-default.json'
    existing = json.loads(marker.read_text()) if marker.exists() else None
    baseline = json.loads((state / 'baseline-sha256.json').read_text())
    for name, expected in baseline.items():
        if existing and name == '/' + MENU:
            continue
        if digest(target(name)) != expected:
            raise RuntimeError('Normal boot artifact changed: ' + name)
    image = target('/boot/' + meta['image'])
    if existing:
        if (existing.get('default_entry') != ENTRY or existing.get('kernel') != meta['kernel']
                or existing.get('image_sha256') != digest(image)
                or existing.get('grub_sha256') != digest(target(MENU))
                or not OWNED <= {e['name'] for e in tx.entries} or not configured(root)):
            raise RuntimeError('Persistent boot configuration differs from its saved record')
        print('Persistent Touch ID already configured; saved fingerprints and boot files preserved.')
        return existing
    if OWNED & {e['name'] for e in tx.entries}:
        raise RuntimeError('Interrupted persistent setup; use rollback-trial from normal Ubuntu before reinstalling')

    grubenv = target('boot/grub/grubenv')
    env_before = subprocess.check_output(['grub-editenv', str(grubenv), 'list'], text=True)
    pending = next((s.partition('=')[2] for s in env_before.splitlines() if s.startswith('next_entry=')), '')
    if pending and pending != trial.ENTRY:
        raise RuntimeError('Another one-time boot selection is pending; preserving it')
    listing = subprocess.check_output(['lsinitrd', str(image)], text=True)
    for name in ('t1_cfgsel.ko', 'appletbdrm.ko', 'apple_t1_ncm.ko', 'uvcvideo.ko'):
        if 'updates/t1bridge-trial/' + name not in listing:
            raise RuntimeError('Staged image is missing ' + name)
    guard = subprocess.check_output(['lsinitrd', '-f', trial.LEGACY_UDEV_RULE, str(image)])
    if guard != target(trial.LEGACY_UDEV_RULE).read_bytes():
        raise RuntimeError('Staged image has a different legacy udev guard')

    entry = trial.menuentry(target(MENU).read_text(), meta['kernel'], meta['image'])
    entry = entry.replace('MacBook T1Bridge one-boot hardware trial', 'Ubuntu with Touch ID (MacBook T1)')
    entry = entry.replace("--id '" + trial.ENTRY + "'", "--id '" + ENTRY + "'")
    pam = target('etc/pam.d')
    snapshot = lambda: {str(p): digest(p) for p in pam.iterdir() if p.is_file()}
    before_pam = snapshot()
    # Keep generated configuration and rollback records private and machine-local.
    record = Path(tempfile.mkdtemp(prefix='persistent-', dir=state))
    try:
        generator = ("#!/bin/sh\n# Managed persistent T1Bridge boot.\n"
                     "cat <<'MACBOOK_T1_ENTRY'\n" + entry + 'MACBOOK_T1_ENTRY\n')
        tx.put(GENERATOR, generator.encode(), 0o755)
        tx.put(DROPIN, ('# Persistent Touch ID; normal Ubuntu remains selectable.\n' + DEFAULTS).encode())
        generated = record / 'grub.cfg'
        subprocess.run(['grub-mkconfig', '-o', str(generated)], check=True)
        subprocess.run(['grub-script-check', str(generated)], check=True)
        validate_menu(generated.read_text(), entry)
        tx.put(MENU, generated.read_bytes(), stat.S_IMODE(target(MENU).stat().st_mode), replace=True)
        if snapshot() != before_pam:
            raise RuntimeError('PAM configuration changed during boot selection')
        if any(digest(target(name)) != expected for name, expected in baseline.items() if name != '/' + MENU):
            raise RuntimeError('Normal kernel or initramfs changed during boot selection')
        if subprocess.check_output(['grub-editenv', str(grubenv), 'list'], text=True) != env_before:
            raise RuntimeError('GRUB environment changed concurrently')
        result = {'default_entry': ENTRY, 'kernel': meta['kernel'], 'image': meta['image'],
                  'image_sha256': digest(image), 'grub_sha256': digest(target(MENU)),
                  'pam_preserved': True, 'normal_kernel_and_initramfs_preserved': True}
        if pending:
            subprocess.run(['grub-editenv', str(grubenv), 'unset', 'next_entry'], check=True)
        atomic(marker, (json.dumps(result, indent=2) + '\n').encode())
    except BaseException:
        marker.unlink(missing_ok=True)
        tx.rollback(names=OWNED)
        raise
    print('Persistent Touch ID configured. Restart into Ubuntu with Touch ID (MacBook T1).')
    print('Normal Ubuntu remains in the five-second boot menu. Password authentication is unchanged.')
    return result
