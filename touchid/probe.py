# SPDX-License-Identifier: MIT
"""Read-only host discovery. Reports deliberately exclude hardware identifiers."""
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
LEGACY = ('apple_ibridge', 'apple_touchbar', 'apple_ib_tb', 'apple_ib_als')
ACCEPTANCE = (
    'sensor', 'same_machine_import', 'enroll', 'match', 'nonmatch', 'sudo',
    'gnome_unlock', 'gdm_login', 'password_fallback', 'service_failure_fallback',
    'reboot_persistence', 'touchbar', 'speakers', 'headphones', 'microphone',
    'camera', 'wifi', 'keyboard', 'trackpad', 'suspend_resume', 'uninstall',
    'rollback', 'fresh_install', 'upgrade', 'repeat_install', 'kernel_update',
)


def read(path):
    try:
        return path.read_text().strip()
    except (OSError, UnicodeError):
        return ''


def os_release(text):
    result = {}
    for line in text.splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            words = shlex.split(value)
            result[key] = words[0] if words else ''
    return result


def inspect(root=Path('/'), kernel=None):
    kernel = kernel or platform.release()
    release = os_release(read(root / 'etc/os-release'))
    devices = []
    for device in sorted((root / 'sys/bus/usb/devices').glob('*')):
        if read(device / 'idVendor') == '05ac' and read(device / 'idProduct') == '8600':
            drivers = { (child / 'driver').resolve().name for child in device.glob('*:*')
                        if (child / 'driver').exists() }
            devices.append({'configuration': read(device / 'bConfigurationValue'),
                            'interfaces': sorted(drivers)})
    systemd_version = 0
    if root == Path('/') and shutil.which('systemctl'):
        result = subprocess.run(['systemctl', '--version'], capture_output=True, text=True, check=False)
        match = re.match(r'systemd (\d+)', result.stdout)
        systemd_version = int(match[1]) if match else 0
    fdr = []
    for mount in ('boot/efi', 'efi', 'boot'):
        candidate = root / mount / 'EFI/APPLE/EMBEDDEDOS/FDRData'
        try:
            if any(p.is_symlink() for p in (candidate, *candidate.parents)):
                fdr.append('unreadable')
            elif candidate.is_file() and candidate.stat().st_size > 0:
                fdr.append('present' if os.access(candidate, os.R_OK) else 'unreadable')
        except OSError:
            fdr.append('unreadable')
    headers = root / 'lib/modules' / kernel / 'build'
    return {
        'model': read(root / 'sys/class/dmi/id/product_name'),
        'arch': platform.machine(), 'distro': release.get('ID', 'unknown'),
        'version': release.get('VERSION_ID', 'rolling'), 'kernel': kernel,
        'init': 'systemd' if (root / 'run/systemd/system').is_dir() else 'unsupported',
        'systemd_version': systemd_version,
        'desktop': os.environ.get('XDG_CURRENT_DESKTOP', 'unknown'),
        't1_devices': devices, 'fdr': 'present' if 'present' in fdr else ('unreadable' if fdr else 'not-found-at-mounted-efi-paths'),
        'legacy_loaded': [m for m in LEGACY if (root / 'sys/module' / m).exists()],
        'headers_match': read(headers / 'include/config/kernel.release') == kernel,
        'tools': {t: bool(shutil.which(t)) for t in ('cargo', 'rustc', 'cc', 'make', 'meson', 'ninja', 'pkg-config', 'dkms')},
    }


def assessment(host, matrix=None, lock=None):
    matrix = matrix if matrix is not None else json.loads((HERE / 'compatibility.json').read_text())
    lock = lock if lock is not None else json.loads((HERE / 'sources.lock.json').read_text())
    reasons = []
    if host['model'] != 'MacBookPro13,2' or host['arch'] != 'x86_64':
        reasons.append('This integration has no hardware validation for this model/architecture')
    if len(host['t1_devices']) != 1:
        reasons.append('Expected exactly one Apple T1 USB 05ac:8600; sensor readiness is unproven')
    if host['fdr'] != 'present':
        reasons.append('Required local EFI FDRData: ' + host['fdr'] + '; inspect preserved EFI or a verified same-Mac backup')
    if host['init'] != 'systemd' or host['systemd_version'] < 256:
        reasons.append('Booted systemd >= 256 is required')
    if not host['headers_match']:
        reasons.append('Exact running-kernel headers are missing or mismatched')
    if host['legacy_loaded']:
        reasons.append('Working legacy Touch Bar drivers conflict; an audited reboot migration is required')
    row = next((r for r in matrix['validated'] if all(
        r.get(k) == host[k] for k in ('model', 'arch', 'distro', 'version', 'kernel'))
        and r.get('upstream_commit') == lock['t1bridge']['commit']), None)
    if not row or any(row.get('acceptance', {}).get(k) != 'pass' for k in ACCEPTANCE):
        reasons.append('Release gate closed: physical, authentication, persistence, recovery and complete installer acceptance is incomplete')
    return {'schema': 1, 'host': host, 'eligible': not reasons, 'status': 'blocked' if reasons else 'validated',
            'reasons': reasons, 'upstream_commit': lock['t1bridge']['commit'],
            'pam_changed': False}
