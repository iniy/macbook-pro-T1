#!/usr/bin/env python3
"""Own the small, unprivileged post-login verifier installed by --all."""
from pathlib import Path
import subprocess
import sys
import time

from component_support import ROOT, host, run, transaction

STATE = Path('/var/lib/macbook-t1-suite')
FILES = ['verify-ubuntu.sh', 'verify-audio.sh', 'verify-camera.sh', 'lib/common.sh',
         'lib/components.py', 'lib/component_support.py', 'lib/postboot.py', 'audio/check.py', 'camera/check.py',
         'verify-wifi.sh', 'wifi/check.py', 'wifi/radio.py']


def setup():
    host(root=True)
    if (STATE / 'complete').is_file():
        print('Post-login verification already installed.')
        return
    if STATE.exists() or STATE.is_symlink():
        raise RuntimeError('Incomplete verification transaction; uninstall the suite before retrying')
    tx = transaction()
    tx.FILES = {name: '/usr/local/libexec/macbook-t1-suite/' + name for name in FILES}
    tx.FILES['config/macbook-t1-verify.service'] = '/etc/systemd/user/macbook-t1-verify.service'
    try:
        tx.deploy(ROOT, STATE, usbmux=False)
        run('systemctl', '--global', 'enable', 'macbook-t1-verify.service')
        (STATE / 'complete').touch()
    except BaseException:
        subprocess.run(['systemctl', '--global', 'disable', 'macbook-t1-verify.service'])
        tx.restore(STATE)
        raise


def remove():
    host(root=True)
    if not STATE.exists():
        return
    if STATE.is_symlink():
        raise RuntimeError('Refusing symlink verification transaction')
    run('systemctl', '--global', 'disable', 'macbook-t1-verify.service')
    if not transaction().restore(STATE):
        raise RuntimeError('Later verification-file edits preserved; review suite files.json')
    STATE.rename(STATE.with_name(STATE.name + '-removed-' + str(time.time_ns())))


if __name__ == '__main__':
    try:
        {'install': setup, 'uninstall': remove}[sys.argv[1]]()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
