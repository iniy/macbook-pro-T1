#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Install the optional GNOME 51 OSD integration in the invoking user's account."""
import json
import os
from pathlib import Path
import subprocess

from transaction import Transaction, atomic, safe


def main():
    if os.geteuid() == 0:
        raise RuntimeError('Install the OSD extension as the desktop user')
    try:
        version = subprocess.run(['gnome-shell', '--version'], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print('OSD extension skipped: GNOME Shell is not installed.')
        return
    if version.returncode or not version.stdout.strip().startswith('GNOME Shell 51.'):
        print('OSD extension skipped: it currently supports GNOME Shell 51 only.')
        return
    from gi.repository import Gio
    source = Path(__file__).resolve().parent / 'gnome-volume-osd'
    uuid = json.loads((source / 'metadata.json').read_text())['uuid']
    base = safe(Path.home())
    state = base / '.local/state/macbook-t1-touchid-osd'
    tx = Transaction(state, base)
    settings = Gio.Settings.new('org.gnome.shell')
    enabled = list(settings.get_strv('enabled-extensions'))
    disabled = list(settings.get_strv('disabled-extensions'))
    if settings.get_boolean('disable-user-extensions') or uuid in disabled:
        print('OSD extension skipped: preserving the user\'s disabled-extension preference.')
        return
    if not settings.is_writable('enabled-extensions'):
        raise RuntimeError('GNOME extension policy is read-only')
    before = state / 'settings-before.json'
    if not before.exists():
        atomic(before, (json.dumps({'enabled': uuid in enabled}, indent=2) + '\n').encode())
    for name in ('metadata.json', 'extension.js'):
        relative = f'.local/share/gnome-shell/extensions/{uuid}/{name}'
        target = tx.target(relative)
        data = (source / name).read_bytes()
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError('Existing OSD extension differs; preserving local changes')
        tx.put(relative, data, replace=target.exists())
    if uuid not in enabled:
        if not settings.set_strv('enabled-extensions', enabled + [uuid]):
            raise RuntimeError('Could not enable the OSD extension')
        Gio.Settings.sync()
    print('GNOME volume/mute OSD installed; new extensions load at the next desktop login.')


if __name__ == '__main__':
    main()
