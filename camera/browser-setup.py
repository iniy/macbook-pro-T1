#!/usr/bin/env python3
"""Install the on-demand camera adapter, including from the root one-shot flow."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'lib'))
from component_support import host

OPTIONS = 'options v4l2loopback video_nr=10 card_label="FaceTime HD (Browser)" exclusive_caps=1 max_buffers=4\n'
SYSTEM_FILES = {
    Path('/etc/modprobe.d/macbook-t1-camera-browser.conf'): OPTIONS,
    Path('/etc/modules-load.d/macbook-t1-camera-browser.conf'): 'v4l2loopback\n',
}
SERVICE = 'macbook-t1-camera-browser.service'
USER_FILES = ('browser-bridge', 'browser-bridge.py', 'check.py')
PACKAGES = ('build-essential', 'ffmpeg', 'v4l-utils', 'kmod', 'dbus-user-session', 'pipewire-bin')


def account(name=None):
    try:
        owner = (pwd.getpwnam(name) if name else
                 pwd.getpwuid(int(os.environ.get('SUDO_UID') or os.environ.get('PKEXEC_UID') or os.getuid())))
    except (KeyError, ValueError) as error:
        raise RuntimeError('Select a desktop account with --account, or invoke sudo from that account') from error
    home = Path(owner.pw_dir)
    if (not 1000 <= owner.pw_uid < 60000 or not home.is_absolute() or home == Path('/')
            or home.is_symlink() or not home.is_dir() or home.stat().st_uid != owner.pw_uid
            or Path(owner.pw_shell).name in ('false', 'nologin')):
        raise RuntimeError('The camera adapter needs a normal desktop account with its own home')
    return owner


def dependencies(install=False):
    missing = [tool for tool in ('cc', 'ffmpeg', 'v4l2-ctl', 'modinfo', 'modprobe', 'systemctl', 'runuser')
               if not shutil.which(tool)]
    module = subprocess.run(['modinfo', '-F', 'vermagic', 'v4l2loopback'], text=True,
                            capture_output=True) if shutil.which('modinfo') else None
    module_missing = module is None or module.returncode != 0
    if (missing or module_missing) and not install:
        raise RuntimeError('Missing camera dependencies: ' + ', '.join(missing +
                           (['v4l2loopback for ' + os.uname().release] if module_missing else [])) +
                           '; rerun with --install-deps')
    if missing or module_missing:
        packages = list(PACKAGES) if missing else []
        if module_missing:
            # Ubuntu 26.10 supplies this signed, per-kernel module separately.
            packages.append('linux-main-modules-v4l2loopback-' + os.uname().release)
        subprocess.run(['apt-get', 'install', '--no-remove', '-y', *packages], check=True)
    abi = subprocess.check_output(['modinfo', '-F', 'vermagic', 'v4l2loopback'], text=True)
    version = subprocess.check_output(['modinfo', '-F', 'version', 'v4l2loopback'], text=True).strip()
    numbers = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', version)
    if not abi.startswith(os.uname().release + ' ') or not numbers or tuple(map(int, numbers.groups())) < (0, 15, 3):
        raise RuntimeError('A matching v4l2loopback module version 0.15.3 or newer is required')


def system_install(remove=False):
    host(root=True)
    for path, expected in SYSTEM_FILES.items():
        if path.is_symlink() or (path.exists() and path.read_text() != expected):
            raise RuntimeError('Refusing to replace locally modified configuration: ' + str(path))
    if remove:
        for path in SYSTEM_FILES:
            path.unlink(missing_ok=True)
        print('Browser camera boot configuration removed; current devices retained until restart.')
        return
    subprocess.run(['modinfo', 'v4l2loopback'], check=True, stdout=subprocess.DEVNULL)
    device = Path('/sys/class/video4linux/video10/name')
    if device.exists() and device.read_text().strip() != 'FaceTime HD (Browser)':
        raise RuntimeError('/dev/video10 is already used by another camera')
    if Path('/sys/module/v4l2loopback').exists() and not device.exists():
        raise RuntimeError('v4l2loopback is already in use with another configuration; no changes made')
    if not device.exists():
        subprocess.run(['modprobe', 'v4l2loopback', 'video_nr=10',
                        'card_label=FaceTime HD (Browser)', 'exclusive_caps=1', 'max_buffers=4'], check=True)
    if device.read_text().strip() != 'FaceTime HD (Browser)':
        raise RuntimeError('Expected loopback camera was not created')
    if Path('/sys/module/v4l2loopback/parameters/max_buffers').read_text().strip() != '4':
        raise RuntimeError('Expected four loopback buffers; refusing a different existing configuration')
    for path, expected in SYSTEM_FILES.items():
        if not path.exists():
            with path.open('x') as stream:
                stream.write(expected)
            path.chmod(0o644)
    print('Browser camera module configured for future boots; T1 USB and boot images preserved.')


def unit_text(destination):
    destination = str(destination).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    return f'''[Unit]
Description=On-demand FaceTime HD browser camera
ConditionKernelCommandLine=t1bridge.trial=1
Before=wireplumber.service
PartOf=graphical-session.target
StartLimitIntervalSec=0

[Service]
Type=notify
ExecStart=/usr/bin/python3 "{destination}/browser-bridge.py"
Restart=on-failure
RestartSec=5
TimeoutStartSec=20
TimeoutStopSec=4
KillMode=control-group
NoNewPrivileges=true

[Install]
WantedBy=default.target graphical-session.target
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def user_paths(home):
    destination = home / '.local/lib/macbook-t1-camera-browser'
    paths = {name: destination / name for name in USER_FILES}
    paths['service'] = home / '.config/systemd/user' / SERVICE
    return destination, paths, destination / 'installed-files.json'


def validate_files(paths, expected, manifest, removing=False):
    if manifest.is_symlink():
        raise RuntimeError('Refusing symlink camera installation record')
    saved = json.loads(manifest.read_text()) if manifest.exists() else {}
    if (not isinstance(saved, dict) or set(saved) - set(paths) or
            any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value)
                for value in saved.values())):
        raise RuntimeError('Invalid camera installation record')
    for name, path in paths.items():
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RuntimeError('Refusing unsafe camera file: ' + str(path))
        allowed = (saved.get(name),) if removing and manifest.exists() else (saved.get(name), digest(expected[name]))
        if path.exists() and digest(path.read_bytes()) not in allowed:
            raise RuntimeError('Preserving locally modified camera file: ' + str(path))


def session_environment():
    runtime = Path('/run/user') / str(os.getuid())
    bus = runtime / 'bus'
    live = (runtime.is_dir() and runtime.stat().st_uid == os.getuid() and
            bus.exists() and stat.S_ISSOCK(bus.stat().st_mode) and bus.stat().st_uid == os.getuid())
    environment = dict(os.environ)
    environment.pop('DBUS_SESSION_BUS_ADDRESS', None)
    environment.pop('XDG_RUNTIME_DIR', None)
    if live:
        environment.update(XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(bus))
    return environment, live


def user_install(remove=False, check=False):
    host()
    if os.geteuid() == 0:
        raise RuntimeError('Run --user as the ordinary desktop user')
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    destination, paths, manifest = user_paths(home)
    pending = destination / 'pending-activation.json'
    unit = paths['service']
    if destination.is_symlink() or pending.is_symlink():
        raise RuntimeError('Refusing symlink installation paths')
    expected = {name: (HERE / name).read_bytes() for name in USER_FILES[1:]}
    expected['service'] = unit_text(destination).encode()
    if remove and not destination.exists() and not unit.exists():
        print('No user camera adapter to remove.')
        return
    if remove and manifest.exists():
        # Recorded installations can be removed without a compiler.
        expected['browser-bridge'] = b''
    else:
        with tempfile.TemporaryDirectory(prefix='t1-browser-camera-') as temporary:
            binary = Path(temporary) / 'browser-bridge'
            subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-o', str(binary), str(HERE / 'browser-bridge.c')], check=True)
            expected['browser-bridge'] = binary.read_bytes()
    validate_files(paths, expected, manifest, removing=remove)
    activation = json.loads(pending.read_text()) if pending.exists() else None
    if activation is not None and (not isinstance(activation, dict) or set(activation) != {'new_unit'}
                                   or not isinstance(activation['new_unit'], bool)):
        raise RuntimeError('Invalid camera activation record')
    if check:
        print('Camera user installation preflight passed.')
        return
    env, live = session_environment()
    def systemctl(*args, **kwargs):
        return subprocess.run(['systemctl', '--user', *args], env=env, **kwargs)
    if remove:
        if unit.exists():
            systemctl('disable', *(['--now'] if live else ['--no-reload']), SERVICE, check=True)
        unit.unlink(missing_ok=True)
        # Only the adapter files are removed; unrelated local files are retained.
        for name in USER_FILES:
            (destination / name).unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        pending.unlink(missing_ok=True)
        cache = destination / '__pycache__'
        if cache.is_dir() and not cache.is_symlink():
            for path in cache.glob('check.cpython-*.pyc'):
                path.unlink()
            if not any(cache.iterdir()):
                cache.rmdir()
        if destination.exists() and not any(destination.iterdir()):
            destination.rmdir()
        if live:
            systemctl('daemon-reload', check=True)
        print('User browser camera adapter removed.')
        return
    new_unit = not unit.exists()
    changed = [name for name, path in paths.items() if not path.exists() or path.read_bytes() != expected[name]]
    if not changed and activation is None:
        if not manifest.exists():
            atomic_write(manifest, (json.dumps({name: digest(data) for name, data in expected.items()}, indent=2) + '\n').encode(), 0o600)
        print('Camera adapter already installed; running services and user preferences preserved.')
        return
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if activation is None:
        activation = {'new_unit': new_unit}
        atomic_write(pending, (json.dumps(activation) + '\n').encode(), 0o600)
    # Record both old and new contents across a possible interrupted update:
    # each unchanged/new file is also accepted by validate_files on retry.
    old = {name: digest(path.read_bytes()) for name, path in paths.items() if path.exists()}
    atomic_write(manifest, (json.dumps(old, indent=2) + '\n').encode(), 0o600)
    for name in changed:
        atomic_write(paths[name], expected[name], 0o755 if name == 'browser-bridge' else 0o644)
    atomic_write(manifest, (json.dumps({name: digest(data) for name, data in expected.items()}, indent=2) + '\n').encode(), 0o600)
    if live:
        systemctl('daemon-reload', check=True)
    if activation['new_unit']:
        systemctl('enable', *(['--now'] if live else ['--no-reload']), SERVICE, check=True)
    elif live and systemctl('is-enabled', '--quiet', SERVICE).returncode == 0:
        systemctl('restart', SERVICE, check=True)
    # The current session may have discovered an output-only loopback device
    # before the producer started. On future logins the notify/Before ordering
    # ensures readiness before WirePlumber's first scan.
    if activation['new_unit'] and live and systemctl('is-active', '--quiet', SERVICE).returncode == 0:
        systemctl('try-restart', 'wireplumber.service', check=True)
    pending.unlink()
    print('User adapter installed; existing enable/disable preferences preserved. Select FaceTime HD (Browser).')


def install(name=None, install_deps=False, remove=False):
    host(root=True)
    owner = account(name)
    if not remove:
        dependencies(install_deps)
    # The checkout may be inside another account's private home. Stage only
    # these sources as root-readable data, then compile and write as the user.
    with tempfile.TemporaryDirectory(prefix='macbook-t1-camera-', dir='/var/tmp') as temporary:
        stage = Path(temporary)
        (stage / 'camera').mkdir()
        (stage / 'lib').mkdir()
        for filename in ('browser-setup.py', 'browser-bridge.c', 'browser-bridge.py', 'check.py'):
            shutil.copyfile(HERE / filename, stage / 'camera' / filename)
        shutil.copyfile(HERE.parent / 'lib/component_support.py', stage / 'lib/component_support.py')
        for path in [stage, *stage.rglob('*')]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        command = ['/usr/sbin/runuser', '-u', owner.pw_name, '--', '/usr/bin/python3',
                   str(stage / 'camera/browser-setup.py'), '--user']
        environment = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'}
        if remove:
            subprocess.run([*command, '--remove'], env=environment, cwd='/', check=True)
            system_install(remove=True)
        else:
            subprocess.run([*command, '--check'], env=environment, cwd='/', check=True)
            system_install()
            subprocess.run(command, env=environment, cwd='/', check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--install', action='store_true', help='Install system support and the selected desktop account together')
    scope.add_argument('--system', action='store_true')
    scope.add_argument('--user', action='store_true')
    parser.add_argument('--remove', action='store_true')
    parser.add_argument('--account', help='Desktop account for --install; defaults to the sudo/pkexec account')
    parser.add_argument('--install-deps', action='store_true', help='Install missing build tools and the signed Ubuntu loopback module')
    parser.add_argument('--check', action='store_true', help='With --user, check local files without changing them')
    args = parser.parse_args()
    if (args.account or args.install_deps) and not args.install:
        parser.error('--account and --install-deps require --install')
    if args.check and (not args.user or args.remove):
        parser.error('--check requires --user and cannot remove files')
    if args.install:
        install(args.account, args.install_deps, args.remove)
    elif args.system:
        system_install(args.remove)
    else:
        user_install(args.remove, args.check)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
