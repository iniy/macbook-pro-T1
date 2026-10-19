#!/usr/bin/env python3
"""Shared host checks and owned-file transactions for optional components."""
import importlib.util
import os
from pathlib import Path
import pwd
import subprocess

ROOT = Path(__file__).resolve().parents[1]
os.environ['PATH'] = '/usr/sbin:/usr/bin:/sbin:/bin'


def run(*args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def output(*args):
    return subprocess.check_output(list(map(str, args)), text=True).strip()


def session_command(*args):
    """Query the invoking desktop session without running its programs as root."""
    if os.geteuid() != 0:
        return list(map(str, args))
    uid = int(os.environ.get('SUDO_UID') or os.environ.get('PKEXEC_UID') or 0)
    if uid == 0 or not Path(f'/run/user/{uid}').is_dir():
        raise RuntimeError('A logged-in desktop user is required for PipeWire checks')
    user = pwd.getpwuid(uid)
    return ['runuser', '-u', user.pw_name, '--', 'env', f'XDG_RUNTIME_DIR=/run/user/{uid}',
            f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus', *map(str, args)]


def host(root=False):
    if os.uname().sysname != 'Linux' or os.uname().machine != 'x86_64':
        raise RuntimeError('Requires x86_64 Ubuntu')
    if root and os.geteuid() != 0:
        raise RuntimeError('Run this installation/removal command with sudo')
    if Path('/sys/class/dmi/id/product_name').read_text().strip() != 'MacBookPro13,2':
        raise RuntimeError('Only MacBookPro13,2 is supported')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '26.10':
        raise RuntimeError('Requires Ubuntu 26.10')


def audio_codec():
    matches = []
    for device in Path('/sys/bus/hdaudio/devices').glob('*'):
        if ((device / 'vendor_id').read_text().strip() == '0x10138409' and
                (device / 'subsystem_id').read_text().strip() == '0x106b3600'):
            matches.append(device)
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one CS8409 codec with Apple subsystem 106b:3600')
    return matches[0]


def transaction():
    spec = importlib.util.spec_from_file_location('owned_files', ROOT / 'lib/deploy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def signatures_required():
    required = False
    if Path('/sys/firmware/efi').exists():
        p = subprocess.run(['mokutil', '--sb-state'], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env=dict(os.environ, LC_ALL='C'))
        text = p.stdout.strip()
        if text == 'SecureBoot enabled' and p.returncode == 0:
            required = True
        elif text.startswith('SecureBoot disabled') and p.returncode == 0:
            pass
        elif text in ("This system doesn't support Secure Boot",
                      'Failed to read "SecureBoot" variable: No such file or directory'):
            efivars = Path('/sys/firmware/efi/efivars')
            if (output('findmnt', '-n', '-o', 'FSTYPE', '--target', efivars) != 'efivarfs' or
                    not os.access(efivars, os.R_OK | os.X_OK) or
                    (efivars / 'SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c').exists()):
                raise RuntimeError('Cannot establish Secure Boot state')
        else:
            raise RuntimeError('Unknown Secure Boot state; refusing installation')
    enforce = Path('/sys/module/module/parameters/sig_enforce')
    lockdown = Path('/sys/kernel/security/lockdown')
    if enforce.exists() and enforce.read_text().strip() in ('Y', '1'):
        required = True
    if lockdown.exists() and any(mode in lockdown.read_text() for mode in ('[integrity]', '[confidentiality]')):
        required = True
    return required
