#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Report touchpad settings and apply the requested per-user GNOME Bounce Keys policy."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from component_support import session_command

TOUCHPAD = 'org.gnome.desktop.peripherals.touchpad'
KEYBOARD = 'org.gnome.desktop.a11y.keyboard'
TOUCHPAD_KEYS = ['disable-while-typing', 'tap-to-click', 'tap-and-drag']
DESIRED = {'bouncekeys-delay': '100', 'bouncekeys-enable': 'true'}


def get(schema, key):
    return subprocess.check_output(['gsettings', 'get', schema, key], text=True).strip()


def set_value(key, value):
    subprocess.run(['gsettings', 'set', KEYBOARD, key, value], check=True)


def show():
    for key in TOUCHPAD_KEYS:
        print(f'{TOUCHPAD} {key}: {get(TOUCHPAD, key)}')
    for key in DESIRED:
        print(f'{KEYBOARD} {key}: {get(KEYBOARD, key)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--show', action='store_true', help='Read settings without changing them')
    mode.add_argument('--restore', action='store_true', help='Restore original owned values; preserve later edits')
    args = parser.parse_args()
    if os.geteuid() == 0:
        return subprocess.run(session_command(sys.executable, str(Path(__file__).resolve()), *sys.argv[1:])).returncode
    if args.show:
        show()
        return 0
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
    if not (runtime / 'bus').exists():
        raise RuntimeError('A running GNOME user session is required; use --no-desktop for a headless installation')
    state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'macbook-pro-T1/desktop'
    if state.is_symlink():
        raise RuntimeError('Refusing symlink settings state')
    os.umask(0o077)
    before_file = state / 'before.json'
    if args.restore:
        if not before_file.exists():
            print('No desktop-settings backup exists.')
            return 0
        before = json.loads(before_file.read_text())
        for key, installed in DESIRED.items():
            current = get(KEYBOARD, key)
            if current == installed:
                set_value(key, before[key])
            elif current != before[key]:
                print('Preserving later edit:', key)
        show()
        return 0
    # The requested touchpad commands were GETs: report, do not alter these keys.
    for key in TOUCHPAD_KEYS:
        print(f'{TOUCHPAD} {key}: {get(TOUCHPAD, key)}')
    current = {key: get(KEYBOARD, key) for key in DESIRED}
    for key in DESIRED:
        writable = subprocess.check_output(['gsettings', 'writable', KEYBOARD, key], text=True).strip()
        if writable != 'true':
            raise RuntimeError('GNOME policy makes this setting read-only: ' + key)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not before_file.exists():
        with before_file.open('x') as stream:
            json.dump(current, stream, indent=2)
    changed = []
    try:
        for key, desired in DESIRED.items():
            if current[key] != desired:
                set_value(key, desired)
                changed.append(key)
            if get(KEYBOARD, key) != desired:
                raise RuntimeError('Setting did not apply: ' + key)
    except BaseException:
        for key in reversed(changed):
            if get(KEYBOARD, key) == DESIRED[key]:
                set_value(key, current[key])
        raise
    print('Bounce Keys enabled with a 100 ms delay. Original values saved:', before_file)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
