#!/usr/bin/env python3
"""Owned-file transaction with write-ahead backups and edit-aware restoration."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

STATE = Path('/var/lib/macbook-t1-ubuntu')
FILES = {
    'config/macbook-t1-touchbar.conf': '/etc/modprobe.d/macbook-t1-touchbar.conf',
    'config/90-macbook-t1-touchbar.rules': '/etc/udev/rules.d/90-macbook-t1-touchbar.rules',
    'config/macbook-t1-touchbar.service': '/etc/systemd/system/macbook-t1-touchbar.service',
    'lib/activate.sh': '/usr/local/libexec/macbook-t1-touchbar/activate.sh',
    'lib/common.sh': '/usr/local/libexec/macbook-t1-touchbar/common.sh',
    'config/dkms-signing.conf': '/etc/dkms/framework.conf.d/zz-macbook-t1-touchbar.conf',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.t1-new')
    if tmp.exists() or tmp.is_symlink():
        raise RuntimeError(f'Refusing preexisting temporary path: {tmp}')
    with tmp.open('xb') as f:
        f.write(data)
    tmp.chmod(mode)
    os.replace(tmp, path)


def deploy(source, state=STATE, root=Path('/'), *, usbmux=True):
    if (state / 'files.json').exists():
        raise RuntimeError('Transaction already exists; uninstall before replacing.')
    entries = [(dst, (source / src).read_bytes(), 0o755 if src.endswith('.sh') else 0o644)
               for src, dst in FILES.items()]
    # Override only the effective usbmuxd rule, preserving iPhone/iPad support.
    rules = {}
    for directory in (['usr/lib/udev/rules.d', 'lib/udev/rules.d', 'etc/udev/rules.d'] if usbmux else []):
        for rule in (root / directory).glob('*usbmuxd*.rules'):
            rules[rule.name] = rule
    for name, rule in sorted(rules.items()):
        if rule.is_symlink() and rule.resolve() == Path('/dev/null'):
            continue
        content = rule.read_bytes()
        if b'8600' not in content:
            continue
        guard = (b'# T1-only exclusion; vendor snapshot, re-check after usbmuxd updates.\n'
                 b'SUBSYSTEM=="usb", ATTR{idVendor}=="05ac", ATTR{idProduct}=="8600", GOTO="macbook_t1_usbmuxd_end"\n')
        entries.append(('/etc/udev/rules.d/' + name, guard + content +
                        b'\nLABEL="macbook_t1_usbmuxd_end"\n', 0o644))
    records = []
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = state / 'backups'
    backup.mkdir(exist_ok=True)
    for number, (dst, data, mode) in enumerate(entries):
        path = root / dst.lstrip('/')
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RuntimeError(f'Refusing non-regular destination: {dst}')
        record = {'path': dst, 'installed_sha256': digest(data), 'backup': None}
        if path.exists():
            saved = backup / str(number)
            shutil.copy2(path, saved)
            record['backup'] = str(number)
            record['original_sha256'] = digest(path.read_bytes())
        records.append(record)
    # Journal the full operation BEFORE the first config write.
    atomic(state / 'files.json', json.dumps(records, indent=2).encode(), 0o600)
    for dst, data, mode in entries:
        atomic(root / dst.lstrip('/'), data, mode)


def restore(state=STATE, root=Path('/')):
    journal = state / 'files.json'
    if not journal.exists():
        return True
    records = json.loads(journal.read_text())
    remaining = []
    for record in reversed(records):
        path = root / record['path'].lstrip('/')
        saved = state / 'backups' / str(record['backup'])
        if path.is_symlink():
            remaining.append(record)
            continue
        current = digest(path.read_bytes()) if path.exists() else None
        if current == record.get('original_sha256') and current is not None:
            continue  # Never written, or already restored after an interrupted run.
        if current is not None and current != record['installed_sha256']:
            print('Preserving later edit:', record['path'], file=sys.stderr)
            remaining.append(record)
            continue
        if record['backup'] is not None:
            if digest(saved.read_bytes()) != record['original_sha256']:
                raise RuntimeError('Backup checksum mismatch: ' + record['path'])
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, path)
        elif path.exists():
            path.unlink()
    atomic(journal, json.dumps(list(reversed(remaining)), indent=2).encode(), 0o600)
    return not remaining


if __name__ == '__main__':
    if os.geteuid() != 0 or sys.platform != 'linux':
        raise SystemExit('Deployment requires root on Ubuntu.')
    if sys.argv[1:] == ['restore']:
        raise SystemExit(0 if restore() else 2)
    if len(sys.argv) == 3 and sys.argv[1] == 'install':
        deploy(Path(sys.argv[2]))
    else:
        raise SystemExit('Usage: deploy.py install SOURCE | restore')
