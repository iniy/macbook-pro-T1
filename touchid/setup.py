# SPDX-License-Identifier: MIT
"""One-shot Touch ID installation for the recorded Ubuntu/MacBook build target."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile

import adapters
import build
import deploy
import persistent
from probe import inspect
import trial

HERE = Path(__file__).resolve().parent
TARGET = ('MacBookPro13,2', 'ubuntu', '26.10', '7.3.0-9-generic', 'x86_64')
RUNTIME_PACKAGES = ['dracut-core', 'kmod', 'grub-common', 'grub2-common', 'fprintd',
                    'libpam-fprintd', 'python3-dbus', 'python3-gi', 'pipewire-bin', 'dbus-user-session']


def supported(host):
    return tuple(host[k] for k in ('model', 'distro', 'version', 'kernel', 'arch')) == TARGET


def account(user=None):
    try:
        if user:
            result = pwd.getpwnam(user)
        else:
            uid = int(os.environ.get('SUDO_UID') or os.environ.get('PKEXEC_UID') or os.getuid())
            result = pwd.getpwuid(uid)
    except KeyError as error:
        raise RuntimeError('The selected Touch ID account does not exist') from error
    if result.pw_uid < 1000:
        raise RuntimeError('Run sudo from the desktop account, or specify --user for Touch ID')
    return result


def existing_state():
    path = trial.STATE / 'state.json'
    if path.exists():
        data = json.loads(path.read_text())
        if data.get('phase') != 'rolled-back':
            return data
    return None


def preflight(user=None, install_deps=False):
    if os.geteuid() != 0:
        raise RuntimeError('Touch ID installation requires root')
    owner = account(user)
    host = inspect()
    if not supported(host):
        raise RuntimeError('Persistent Touch ID currently requires MacBookPro13,2, Ubuntu 26.10, '
                           'x86_64 and kernel 7.3.0-9-generic; use --no-touchid for other kernels')
    adapters.Systemd.require(host)
    if host['fdr'] != 'present' or len(host['t1_devices']) != 1:
        raise RuntimeError('Exactly one T1 and readable same-Mac EFI FDRData are required')
    if not host['headers_match'] and not install_deps:
        raise RuntimeError('Exact kernel headers are missing; allow dependency installation')
    for path in (Path('/sys/module/module/parameters/sig_enforce'), Path('/sys/kernel/security/lockdown')):
        if path.exists() and (path.read_text().strip() in ('Y', '1') or
                             any(x in path.read_text() for x in ('[integrity]', '[confidentiality]'))):
            raise RuntimeError('Signature-enforced Touch ID installation is not implemented')
    previous = existing_state()
    if previous:
        if previous.get('phase') not in ('armed', 'staged') or previous['user'] != owner.pw_name or previous['kernel'] != host['kernel']:
            raise RuntimeError('Existing Touch ID installation has a different owner/kernel or is incomplete')
        persistent.validate_files(trial.Transaction(trial.STATE / 'files'))
    elif trial.booted() or host['t1_devices'][0]['configuration'] != '1':
        raise RuntimeError('A fresh setup must start from normal Ubuntu USB configuration 1')
    print('Touch ID installation preflight passed for the supported host and desktop account.')
    return owner, host


def ensure_bundle(owner, host, install_deps):
    if build.PREFIX.exists():
        manifest = deploy.verify(build.PREFIX)
        if manifest.get('kernel') != host['kernel'] or not manifest.get('tests_requested'):
            raise RuntimeError('Installed bundle was not built and checked for this kernel')
        print('Reusing the verified private Touch ID bundle.')
        return
    if install_deps:
        subprocess.run(adapters.dependency_command(host['distro'], host['kernel']), check=True)
    # Source compilation and its subprocesses never run as root. Failed build
    # directories remain available for diagnostics; each attempt gets a new one.
    work = Path(tempfile.mkdtemp(prefix='macbook-t1-build-', dir='/var/tmp'))
    os.chown(work, owner.pw_uid, owner.pw_gid)
    subprocess.run(['runuser', '-u', owner.pw_name, '--', 'python3',
                    str(HERE / 'manage.py'), 'build', '--work', str(work)], check=True)
    deploy.install(work / 'stage' / build.PREFIX.relative_to('/'))


def ensure_runtime(install_deps):
    result = subprocess.run(['dpkg-query', '-W', '-f=${Package} ${db:Status-Status}\n',
                             *RUNTIME_PACKAGES], capture_output=True, text=True, check=False)
    installed = {line.split()[0] for line in result.stdout.splitlines() if line.endswith(' installed')}
    missing = [name for name in RUNTIME_PACKAGES if name not in installed]
    if missing and not install_deps:
        raise RuntimeError('Missing Touch ID runtime packages: ' + ', '.join(missing))
    if missing:
        subprocess.run(['apt-get', 'install', '--no-remove', '-y', *missing], check=True)


def install(user=None, install_deps=False, desktop=True):
    owner, host = preflight(user, install_deps)
    # The desktop integration can be installed without altering active drivers.
    ensure_runtime(install_deps)
    ensure_bundle(owner, host, install_deps)
    if desktop:
        runtime = Path('/run/user') / str(owner.pw_uid)
        if not (runtime / 'bus').exists():
            raise RuntimeError('Desktop session unavailable; use --no-desktop or run from the desktop account')
        subprocess.run(['runuser', '-u', owner.pw_name, '--', 'env',
                        'XDG_RUNTIME_DIR=' + str(runtime), 'DBUS_SESSION_BUS_ADDRESS=unix:path=' + str(runtime / 'bus'),
                        'python3', str(HERE / 'install-osd.py')], check=True)
    fresh = existing_state() is None
    if fresh:
        trial.prepare(owner.pw_name, arm=False)
    try:
        persistent.enable(owner.pw_name)
    except BaseException:
        if fresh:
            trial.rollback()
        raise
    print('After reboot: Settings → System → Users → Fingerprint Login. Existing enrollments are retained.')
    print('GNOME uses its distribution fingerprint PAM service; common password/sudo PAM rules are unchanged.')
