#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reversible, opt-in stock-brcmfmac configuration for the validated T1 model."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from component_support import host, transaction
from check import hardware, command

STATE = Path('/var/lib/macbook-t1-wifi')
PREFIX = '/usr/local/libexec/macbook-t1-wifi'
SERVICE = 'macbook-t1-wifi-country.service'
VERIFY = 'macbook-t1-wifi-verify.timer'


def run(*args):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f'{args[0]} failed (exit {p.returncode}); inspect local service/package logs')
    return p.stdout.strip()


def country(value):
    if value is None:
        return None
    codes = json.loads(Path('/usr/share/iso-codes/json/iso_3166-1.json').read_text())
    if value not in {item['alpha_2'] for item in codes['3166-1']}:
        raise ValueError('Use the actual physical country ISO alpha-2 code')
    return value


def settings(args, previous=None):
    values = dict(previous or {})
    for name in ['country', 'disable_offload', 'roamoff', 'profile', 'powersave', 'stable_mac']:
        value = getattr(args, name)
        if value is not None:
            values[name] = value
        else:
            values.setdefault(name, None)
    country(values['country'])
    if (values['powersave'] or values['stable_mac']) and not values['profile']:
        raise RuntimeError('Per-connection options require --profile UUID')
    if values['profile'] and not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}', values['profile']):
        raise RuntimeError('--profile requires a connection UUID, kept only in private local state')
    return values


def profile_changes(options):
    if not options['profile']:
        return {}
    if run('nmcli', '-g', 'connection.type', 'connection', 'show', 'uuid', options['profile']) != '802-11-wireless':
        raise RuntimeError('Selected profile is not Wi-Fi')
    changes = {}
    if options['powersave']:
        changes['802-11-wireless.powersave'] = '2' if options['powersave'] == 'off' else '3'
    if options['stable_mac']:
        changes['802-11-wireless.cloned-mac-address'] = 'stable'
    return changes


def profile_value(uuid, key):
    text = run('nmcli', '-g', key, 'connection', 'show', 'uuid', uuid)
    return text.split(' ', 1)[0] if key.endswith('.powersave') else text


def change_profile(options):
    changes = profile_changes(options)
    journal = []
    for key, value in changes.items():
        journal.append({'uuid': options['profile'], 'key': key,
                        'old': profile_value(options['profile'], key), 'new': value})
    transaction().atomic(STATE / 'profile.json', json.dumps(journal).encode(), 0o600)
    for record in journal:
        run('nmcli', 'connection', 'modify', 'uuid', record['uuid'], record['key'], record['new'])


def restore_profile(state=STATE):
    path = state / 'profile.json'
    if not path.exists():
        return True
    remaining = []
    for record in json.loads(path.read_text()):
        try:
            current = profile_value(record['uuid'], record['key'])
            if current == record['old']:
                continue
            if current != record['new']:
                remaining.append(record)
                continue
            run('nmcli', 'connection', 'modify', 'uuid', record['uuid'], record['key'], record['old'])
        except RuntimeError:
            remaining.append(record)
    transaction().atomic(path, json.dumps(remaining).encode(), 0o600)
    return not remaining


def payload(options):
    files = {
        PREFIX + '/check.py': (ROOT / 'wifi/check.py').read_bytes(),
        PREFIX + '/country.py': (ROOT / 'wifi/country.py').read_bytes(),
        '/etc/systemd/system/macbook-t1-wifi-verify.service': (ROOT / 'wifi/macbook-t1-wifi-verify.service').read_bytes(),
        '/etc/systemd/system/' + VERIFY: (ROOT / 'wifi/macbook-t1-wifi-verify.timer').read_bytes(),
    }
    opts = []
    if options['disable_offload']:
        opts.append('feature_disable=0x82000')
    if options['roamoff']:
        opts.append('roamoff=1')
    if opts:
        files['/etc/modprobe.d/macbook-t1-wifi.conf'] = (
            '# macbook-pro-T1: explicit compatibility options; see wifi/README.md\n'
            'options brcmfmac ' + ' '.join(opts) + '\n').encode()
    if options['country']:
        files['/etc/systemd/system/' + SERVICE] = (
            '[Unit]\nDescription=MacBook T1 physical Wi-Fi country\nBefore=NetworkManager.service\n'
            'After=systemd-udev-trigger.service\n\n[Service]\nType=oneshot\nRemainAfterExit=yes\n'
            f'ExecStart=/usr/bin/python3 {PREFIX}/country.py {options["country"]}\n'
            '\n[Install]\nWantedBy=multi-user.target\n').encode()
    return files


def unchanged():
    tx = transaction()
    for record in json.loads((STATE / 'files.json').read_text()):
        path = Path(record['path'])
        if path.is_symlink() or not path.is_file() or tx.digest(path.read_bytes()) != record['installed_sha256']:
            return False
    for record in json.loads((STATE / 'profile.json').read_text()):
        if profile_value(record['uuid'], record['key']) != record['new']:
            return False
    return True


def remove():
    if STATE.is_symlink():
        raise RuntimeError('Refusing symlink state directory')
    if not STATE.exists():
        print('Wi-Fi component is not installed.')
        return
    for unit in [VERIFY, SERVICE]:
        command('systemctl', 'disable', '--now', unit)
    # Files and individual fields are restored only if still equal to our writes.
    profiles_ok = restore_profile()
    files_ok = transaction().restore(STATE)
    run('systemctl', 'daemon-reload')
    if not profiles_ok or not files_ok:
        raise RuntimeError('Later edits preserved; inspect private files.json/profile.json before completing rollback')
    if (STATE / 'module-options').exists():
        run('update-initramfs', '-u', '-k', os.uname().release)
    if (STATE / 'country-before').exists():
        installed = json.loads((STATE / 'options.json').read_text())['country']
        _, text = command('iw', 'reg', 'get')
        current = re.search(r'^country ([A-Z0-9]{2}):', text, re.M)
        if current and current[1] == installed:
            run('iw', 'reg', 'set', (STATE / 'country-before').read_text().strip())
    STATE.rename(STATE.with_name(STATE.name + '-removed-' + str(time.time_ns())))
    print('Wi-Fi-owned files and profile fields restored. Backups retained. Reboot applies module-option removal.')


def install(args):
    previous = None
    if STATE.is_symlink():
        raise RuntimeError('Refusing symlink state directory')
    if (STATE / 'complete').exists():
        previous = json.loads((STATE / 'options.json').read_text())
        requested = settings(args, previous)
        if not unchanged():
            raise RuntimeError('Installed files/profile fields were edited; preserve/review those edits before updating')
        if not args.update:
            if requested != previous:
                raise RuntimeError('Use --update to change an existing installation')
            print('Wi-Fi installation already complete; configuration preserved.')
            return
    elif STATE.exists():
        raise RuntimeError('Incomplete transaction; run uninstall-wifi.sh before retrying')
    options = settings(args, previous)
    device = hardware()
    if (device / 'driver').exists() and (device / 'driver').resolve().name != 'brcmfmac':
        raise RuntimeError('A different driver owns this adapter; resolve that conflict first')
    if run('modinfo', '-F', 'intree', 'brcmfmac') != 'Y':
        raise RuntimeError('This component requires the stock in-tree brcmfmac module')
    if options['disable_offload'] or options['roamoff']:
        for directory in ['/etc/modprobe.d', '/run/modprobe.d', '/usr/local/lib/modprobe.d', '/usr/lib/modprobe.d']:
            for path in Path(directory).glob('*.conf'):
                if previous and str(path) == '/etc/modprobe.d/macbook-t1-wifi.conf':
                    continue
                if re.search(r'^\s*(?:options|install|blacklist)\s+brcmfmac\b', path.read_text(), re.M):
                    raise RuntimeError('Existing brcmfmac policy requires review: ' + str(path))
    if options['disable_offload'] or options['roamoff']:
        if not re.fullmatch(r'7\.3\.0-\d+-generic', os.uname().release):
            raise RuntimeError('Compatibility bits were audited only against Ubuntu 7.3.0 source')
        params = run('modinfo', '-F', 'parm', 'brcmfmac')
        if not all(name + ':' in params for name in ['feature_disable', 'roamoff']):
            raise RuntimeError('Required module options unavailable')
    profile_changes(options)  # Validate before changing any files.
    if args.install_deps:
        run('apt-get', 'update')
        run('apt-get', 'install', '--no-remove', '-y', 'linux-firmware', 'wireless-regdb',
            'iw', 'ethtool', 'iputils-ping', 'curl', 'iso-codes')
    firmware = Path('/lib/firmware/brcm/brcmfmac43602-pcie.bin')
    if not any(Path(str(firmware) + suffix).is_file() for suffix in ['', '.zst', '.xz']):
        raise RuntimeError('Ubuntu firmware missing; re-run with --install-deps')
    if previous:
        remove()
    files = payload(options)
    for destination in files:
        path = Path(destination)
        if path.exists() or path.is_symlink():
            raise RuntimeError('Unowned destination already exists: ' + destination)
        if any(parent.is_symlink() for parent in path.parents if str(parent).startswith('/usr/local')):
            raise RuntimeError('Symlink in installation directory')
    Path(PREFIX).mkdir(parents=True, exist_ok=True, mode=0o755)
    Path(PREFIX).chmod(0o755)
    tx = transaction()
    STATE.mkdir(mode=0o700)
    tx.atomic(STATE / 'options.json', json.dumps(options).encode(), 0o600)
    # Secrets remain root-only, outside the repository and published reports.
    paths = [str(p) for p in map(Path, ['/etc/NetworkManager', '/etc/netplan', '/etc/modprobe.d']) if p.exists()]
    run('tar', '-cpf', str(STATE / 'network-config.tar'), *paths)
    try:
        with tempfile.TemporaryDirectory(prefix='t1-wifi-') as directory:
            source = Path(directory)
            tx.FILES = {}
            for n, (destination, data) in enumerate(files.items()):
                name = str(n)
                (source / name).write_bytes(data)
                tx.FILES[name] = destination
            tx.deploy(source, STATE, usbmux=False)
        change_profile(options)
        if options['disable_offload'] or options['roamoff']:
            (STATE / 'module-options').touch()
            run('update-initramfs', '-u', '-k', os.uname().release)
        run('systemctl', 'daemon-reload')
        if options['country']:
            _, text = command('iw', 'reg', 'get')
            match = re.search(r'^country ([A-Z0-9]{2}):', text, re.M)
            if not match:
                raise RuntimeError('Cannot back up current regulatory country')
            tx.atomic(STATE / 'country-before', match[1].encode(), 0o600)
            run('systemctl', 'enable', '--now', SERVICE)
        run('systemctl', 'enable', '--now', VERIFY)
        (STATE / 'complete').touch()
    except BaseException:
        remove()
        raise
    print('Wi-Fi component installed. Saved profile changes apply at next connection; module options at next boot.')
    print('Verify with ./verify-wifi.sh --online. Installation is not proof of association or throughput.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('--install-deps', action='store_true')
    parser.add_argument('--update', action='store_true', help='Refresh owned tools/configuration, retaining previous options')
    parser.add_argument('--country', help='Confirmed physical country, ISO alpha-2; no default override')
    parser.add_argument('--disable-offload', action='store_true', default=None, help='Opt-in FWSUP/SAE compatibility trial, not a default')
    parser.add_argument('--roamoff', action='store_true', default=None, help='Opt-in only for proven firmware roaming failures')
    parser.add_argument('--profile', help='Existing Wi-Fi profile UUID for targeted non-security changes')
    parser.add_argument('--powersave', choices=['on', 'off'])
    parser.add_argument('--stable-mac', action='store_true', default=None, help='NetworkManager-generated local per-profile address')
    args = parser.parse_args()
    if args.action == 'install':
        host(root=True)
    elif os.geteuid() != 0 or sys.platform != 'linux':
        raise RuntimeError('Removal requires root on Linux')
    os.umask(0o077)
    with Path('/run/macbook-t1-wifi.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'install':
            install(args)
        else:
            remove()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
