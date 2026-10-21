#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Install, verify or remove the guarded systemd s2idle workaround. Never sleeps."""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import stat
import tempfile

SOURCE = Path(__file__).resolve().parent
ROOT = Path('/')
POWER = Path('/sys/power')
BOOT_DROPIN = Path('etc/default/grub.d/99-macbook-t1-pcie-pm-trial.cfg')
# Exact contents installed during the initial controlled trial. No other
# differing local configuration may be overwritten or removed.
LEGACY_BOOT_SHA256 = '0f85bd65fe629115db5667ed22d3163506c55f6803122a59af66da358c8a4a9c'
# Published wrapper before playback recovery. Only this exact version may be
# replaced automatically; preserve any local edits as before.
LEGACY_WRAPPER_SHA256 = '5e07512470588db7f2eae16fa4d3e1a51a52db9fa1740a757c2c51aaa346b0b2'
SPEC = importlib.util.spec_from_file_location('resume_wrapper', SOURCE / 'suspend-wrapper.py')
WRAPPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WRAPPER)


def files():
    return {
        ROOT / 'usr/local/lib/macbook-t1-sleep/pm.py': SOURCE / 'test-stages.py',
        ROOT / 'usr/local/lib/macbook-t1-sleep/suspend.py': SOURCE / 'suspend-wrapper.py',
        ROOT / 'usr/local/lib/macbook-t1-sleep/audio.py': SOURCE / 'audio.py',
        ROOT / 'etc/systemd/sleep.conf.d/99-macbook-t1-s2idle.conf': SOURCE / '99-macbook-t1-s2idle.conf',
        ROOT / 'etc/systemd/system/systemd-suspend.service.d/99-macbook-t1-suspend.conf': SOURCE / '99-macbook-t1-suspend.conf',
        ROOT / BOOT_DROPIN: SOURCE / '99-macbook-t1-pcie-pm-trial.cfg',
    }


def command(*args):
    subprocess.run(args, check=True)


def check_paths():
    for target, source in files().items():
        if any(parent.is_symlink() for parent in (target, *target.parents)):
            raise RuntimeError('Refusing symlink in managed path: ' + str(target))
        if target.exists() and target.read_bytes() != source.read_bytes():
            legacy = {
                ROOT / BOOT_DROPIN: LEGACY_BOOT_SHA256,
                ROOT / 'usr/local/lib/macbook-t1-sleep/suspend.py': LEGACY_WRAPPER_SHA256,
            }
            if hashlib.sha256(target.read_bytes()).hexdigest() != legacy.get(target):
                raise RuntimeError('Existing file differs; preserving it: ' + str(target))


def boot_active():
    options = [word for word in WRAPPER.PM.CMDLINE.read_text().split()
               if word.startswith('pcie_port_pm=')]
    return options == ['pcie_port_pm=off']


def installation_preflight():
    if (ROOT / 'sys/class/dmi/id/product_name').read_text().strip() != 'MacBookPro13,2':
        raise RuntimeError('Unsupported model; no changes made.')
    if WRAPPER.PM.selected((POWER / 'pm_test').read_text()) != 'none':
        raise RuntimeError('A PM test is active; no changes made.')
    if 's2idle' not in (POWER / 'mem_sleep').read_text():
        raise RuntimeError('s2idle is unavailable; no changes made.')
    command('bash', str(SOURCE / 'manage.sh'), 'verify')


def check_boot_paths():
    for path in (ROOT / 'etc/default/grub', ROOT / 'boot/grub/grub.cfg'):
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
            raise RuntimeError('Expected a regular GRUB configuration: ' + str(path))


def linux_lines(text):
    return [words for line in text.splitlines()
            if (words := line.split()) and words[0] in ('linux', 'linuxefi')]


def validate_grub(text, previous=None):
    lines = linux_lines(text)
    normal = [line for line in lines if 'recovery' not in line]
    if not normal:
        raise RuntimeError('No normal Linux boot entries found.')
    for line in lines:
        options = [word for word in line if word.startswith('pcie_port_pm=')]
        if (line in normal or options) and options != ['pcie_port_pm=off']:
            raise RuntimeError('Missing, duplicate or conflicting PCIe port boot settings.')
    if previous is not None:
        def without_setting(entries):
            return [[word for word in line if word != 'pcie_port_pm=off'] for line in entries]
        if without_setting(lines) != without_setting(linux_lines(previous)):
            raise RuntimeError('GRUB kernel entries changed beyond the PCIe setting; review update-grub separately.')


def atomic_write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def configuration_transaction():
    paths = [*files(), ROOT / 'boot/grub/grub.cfg']
    before = {p: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) if p.exists() else None for p in paths}
    old_mode = WRAPPER.PM.selected((POWER / 'mem_sleep').read_text())
    backup = Path(tempfile.mkdtemp(prefix='macbook-t1-resume-install-', dir='/var/tmp'))
    (backup / 'previous-sleep-mode').write_text(old_mode + '\n')
    for path, snapshot in before.items():
        if snapshot is not None:
            saved = backup / path.relative_to(ROOT)
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(snapshot[0])
            saved.chmod(snapshot[1])
    print('Configuration backup:', backup, flush=True)
    try:
        yield before
    except BaseException as error:
        failures = []
        for path, snapshot in before.items():
            try:
                if snapshot is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, *snapshot)
            except OSError as restore_error:
                failures.append(str(restore_error))
        try:
            (POWER / 'mem_sleep').write_text(old_mode + '\n')
            command('systemctl', 'daemon-reload')
        except Exception as restore_error:
            failures.append(str(restore_error))
        if failures:
            raise RuntimeError(f'{error}; rollback needs attention: {failures}; backup={backup}') from error
        raise


def check_idle():
    state = subprocess.check_output(['systemctl', 'show', '--value', '--property=ActiveState',
                                     'systemd-suspend.service'], text=True).strip()
    if state not in ('inactive', 'failed'):
        raise RuntimeError('The suspend service is busy; no configuration changes made.')


def validate_sleep_config(text):
    # cat-config provides the configuration files in their effective order.
    # These settings are whitespace-separated lists; empty values reset them.
    values = {'MemorySleepMode': [], 'SuspendState': []}
    section = ''
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        elif section == 'Sleep' and '=' in line and not line.startswith(('#', ';')):
            key, value = (part.strip() for part in line.split('=', 1))
            if key in values:
                if value:
                    values[key].extend(value.split())
                else:
                    values[key] = []
    if values != {'MemorySleepMode': ['s2idle'], 'SuspendState': ['mem']}:
        raise RuntimeError('Effective sleep configuration conflicts with guarded s2idle: ' + str(values))


def verify(allow_pending_boot=False):
    for target, source in files().items():
        if target.is_symlink() or not target.exists() or target.read_bytes() != source.read_bytes():
            raise RuntimeError('Installed file is missing or different: ' + str(target))
        print('MATCH:', target)
    effective = subprocess.check_output(['systemctl', 'show', '--value', '--property=ExecStart',
                                         'systemd-suspend.service'], text=True)
    if 'argv[]=/usr/bin/python3 /usr/local/lib/macbook-t1-sleep/suspend.py ;' not in effective:
        raise RuntimeError('The effective suspend service does not use the managed wrapper.')
    validate_sleep_config(subprocess.check_output(
        ['systemd-analyze', 'cat-config', 'systemd/sleep.conf'], text=True))
    if not boot_active():
        print('RESTART REQUIRED: pcie_port_pm=off is configured but is not active in this boot.')
        print('The suspend guard refuses normal sleep until the required boot setting is active.')
        if not allow_pending_boot:
            raise RuntimeError('Restart, then verify again.')
    print('Configuration matches. Normal desktop/lid/idle sleep still requires physical validation.')


def install():
    installation_preflight()
    check_idle()
    check_paths()
    check_boot_paths()
    effective = subprocess.check_output(['systemctl', 'show', '--value', '--property=ExecStart',
                                         'systemd-suspend.service'], text=True)
    expected = ('argv[]=/usr/lib/systemd/systemd-sleep suspend ;',
                'argv[]=/usr/bin/python3 /usr/local/lib/macbook-t1-sleep/suspend.py ;')
    if not any(value in effective for value in expected) or effective.count('argv[]=') != 1:
        raise RuntimeError('Unexpected existing suspend command; preserving it.')
    with configuration_transaction() as before:
        grub = ROOT / 'boot/grub/grub.cfg'
        for target, source in files().items():
            atomic_write(target, source.read_bytes())
        command('update-grub')
        command('grub-script-check', str(grub))
        validate_grub(grub.read_text(), before[grub][0].decode())
        command('systemctl', 'daemon-reload')
        command('systemd-analyze', 'verify', 'systemd-suspend.service')
        if boot_active():
            (POWER / 'mem_sleep').write_text('s2idle\n')
            if WRAPPER.PM.selected((POWER / 'mem_sleep').read_text()) != 's2idle':
                raise RuntimeError('Could not select s2idle.')
        verify(allow_pending_boot=True)
    print('Installed for normal suspend. No sleep or restart was initiated.')


def uninstall():
    check_idle()
    check_paths()
    check_boot_paths()
    with configuration_transaction():
        for target in files():
            target.unlink(missing_ok=True)
        command('update-grub')
        command('grub-script-check', str(ROOT / 'boot/grub/grub.cfg'))
        command('systemctl', 'daemon-reload')
    print('Removed the guarded suspend configuration; live sleep mode is unchanged until reboot.')
    print('The independent NVMe rule remains installed. The PCIe boot change is removed on restart.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'verify', 'uninstall'))
    args = parser.parse_args()
    if args.action != 'verify' and os.geteuid() != 0:
        parser.error('Administrator authentication is required for configuration changes.')
    try:
        {'install': install, 'verify': verify, 'uninstall': uninstall}[args.action]()
    except Exception as error:
        print('ERROR:', error, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
