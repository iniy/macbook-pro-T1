#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Optional exact-ABI 5 GHz deployment, with offline rollback and boot verification."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE if (HERE / 'check.py').exists() else HERE.parent))
sys.path.insert(0, str(ROOT / 'lib'))
import check
import radio
from component_support import host, signatures_required

STATE = Path('/var/lib/macbook-t1-wifi-5ghz')
PREFIX = Path('/usr/local/libexec/macbook-t1-wifi-5ghz')
PACKAGE, VERSION = 'macbook-t1-wifi-5ghz', '1.0.0'
SOURCE = Path('/usr/src') / (PACKAGE + '-' + VERSION)
FW = Path('/usr/lib/firmware/macbook-t1-5ghz/brcm')
CONF = Path('/etc/modprobe.d/macbook-t1-wifi-5ghz.conf')
UNIT = 'macbook-t1-wifi-5ghz-verify'
WATCHDOG = 'macbook-t1-wifi-5ghz-rollback'
REFERENCE_COMMIT = '35dd57c5b2b0fc8f76af5c6c2a45ead010692421'
REFERENCE_SHA = '9f757ace460a40c80a32202e09d507351a8c497f2dee22ba0f8a0a5cb1aebaf7'
REFERENCE_URL = ('https://raw.githubusercontent.com/Bogdan7c/macbook-bcm43602-wifi-fix/' +
                 REFERENCE_COMMIT + '/files/brcmfmac43602-pcie.txt')


def run(*args, timeout=300, required=True):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout, umask=0o022)
    if p.returncode and required:
        raise RuntimeError(args[0] + ' failed: ' + p.stdout[-3000:])
    return p.stdout.strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest(path):
    return {str(p.relative_to(path)): digest(p) for p in sorted(path.rglob('*'))
            if p.is_file() and 'build' not in p.relative_to(path).parts and '__pycache__' not in p.parts}


def save(name, data):
    path = STATE / name
    temp = path.with_name(path.name + '.new')
    with temp.open('w') as stream:
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.chmod(0o600)
    os.replace(temp, path)


def value(uuid, key):
    return run('nmcli', '--escape', 'no', '-g', key, 'connection', 'show', 'uuid', uuid, timeout=20)


def owned_files():
    record = json.loads((STATE / 'files.json').read_text())
    for path, sha in record.items():
        p = Path(path)
        if p.is_symlink() or not p.is_file() or digest(p) != sha:
            raise RuntimeError('Later file edit preserved: ' + path)
    return record


def cleanup_retired_firmware():
    if not FW.parent.exists():
        return
    live = Path('/sys/module/brcmfmac/parameters/alternative_fw_path')
    if live.exists() and live.read_text().strip() == 'macbook-t1-5ghz':
        raise RuntimeError('Reboot to the restored driver before reinstalling retired firmware')
    actual = {str(p): digest(p) for p in FW.parent.rglob('*') if p.is_file() and not p.is_symlink()}
    for archive in sorted(STATE.parent.glob(STATE.name + '-removed-*'), reverse=True):
        record = archive / 'files.json'
        if not record.exists():
            continue
        expected = {p: sha for p, sha in json.loads(record.read_text()).items() if p.startswith(str(FW.parent) + '/')}
        if actual == expected and actual and not any(p.is_symlink() for p in FW.parent.rglob('*')):
            for path in actual:
                Path(path).unlink()
            FW.rmdir()
            FW.parent.rmdir()
            return
    raise RuntimeError('Unowned or edited firmware directory; preserve/review it first')


def quiet_wifi():
    try:
        iface = check.interface(check.hardware())
    except RuntimeError:
        iface = None
    if iface:
        run('nmcli', 'device', 'set', iface, 'managed', 'no', timeout=20)
    for _ in range(40):
        devices = run('iw', 'dev', timeout=10)
        rc, supplicant = check.command('busctl', '--system', 'get-property', 'fi.w1.wpa_supplicant1',
                                      '/fi/w1/wpa_supplicant1', 'fi.w1.wpa_supplicant1', 'Interfaces')
        if 'type P2P-device' not in devices and rc == 0 and supplicant.strip() == 'ao 0':
            time.sleep(2)
            if 'type P2P-device' not in run('iw', 'dev', timeout=10):
                return
        time.sleep(.5)
    raise RuntimeError('P2P/supplicant did not quiesce; driver unload refused')


def activate(meta):
    devices = run('nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'device', 'status').splitlines()
    wired = [line.split(':', 2)[0] for line in devices if ':ethernet:connected' in line]
    if not wired:
        raise RuntimeError('--activate requires independent connected Ethernet; use staged install/reboot otherwise')
    eth = wired[0]
    uuid = run('nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', eth)
    run('nmcli', '--wait', '35', 'connection', 'up', 'uuid', uuid, 'ifname', eth, timeout=40)
    run('curl', '--silent', '--fail', '--noproxy', '*', '--interface', 'if!' + eth,
        '--max-time', '15', '--output', '/dev/null', 'https://example.com/', timeout=20)
    (STATE / 'live-attempt').touch()
    quiet_wifi()
    modules = [m for m in ['brcmfmac_wcc', 'brcmfmac'] if Path('/sys/module', m).exists()]
    if modules:
        run('modprobe', '-r', *modules, timeout=45)
    run('modprobe', 'brcmfmac', timeout=30)
    time.sleep(5)
    iface = check.interface(check.hardware())
    run('iw', 'reg', 'set', 'IN')
    run('nmcli', 'device', 'set', iface, 'managed', 'yes')
    run('nmcli', '--wait', '40', 'connection', 'up', 'uuid', meta['profile'], 'ifname', iface, timeout=45)
    time.sleep(8)
    snap = check.snapshot(online=True, radio_info=True)
    save('activation.json', snap)
    if not check.healthy(snap, True) or not 4900 < (snap['link']['frequency_mhz'] or 0) < 5900:
        raise RuntimeError('Installed driver failed 5 GHz online verification')
    if snap['loaded_driver_srcversion'] != meta['installed_srcversion']:
        raise RuntimeError('Loaded module differs from the DKMS installation')
    print('Installed DKMS module active on 5 GHz; rollback remains armed for extended validation.')


def rollback_live():
    meta = json.loads((STATE / 'state.json').read_text())
    remove()
    try:
        loaded = Path('/sys/module/brcmfmac/srcversion')
        if not loaded.exists() or loaded.read_text().strip() != meta['previous_srcversion']:
            if loaded.exists():
                quiet_wifi()
                modules = [m for m in ['brcmfmac_wcc', 'brcmfmac'] if Path('/sys/module', m).exists()]
                run('modprobe', '-r', *modules, timeout=45)
            run('modprobe', 'brcmfmac', timeout=30)
            time.sleep(5)
        iface = check.interface(check.hardware())
        run('nmcli', 'device', 'set', iface, 'managed', 'yes')
        run('nmcli', '--wait', '40', 'connection', 'up', 'uuid', meta['original_profile'], 'ifname', iface, timeout=45)
        print('Previous wireless connection restored live.')
    except (OSError, RuntimeError, subprocess.SubprocessError):
        print('Disk rollback is complete; one recovery reboot is required.', flush=True)
        run('systemctl', 'reboot')


def install(args):
    host(root=True)
    dev = check.hardware()
    if (dev / 'revision').read_text().strip() != '0x02':
        raise RuntimeError('Requires Apple BCM43602 PCI revision 02')
    if STATE.is_symlink() or SOURCE.is_symlink():
        raise RuntimeError('Refusing symlink installation/state')
    if (STATE / 'complete').exists():
        owned_files()
        if source_manifest(SOURCE) != json.loads((STATE / 'source.json').read_text()):
            raise RuntimeError('Installed DKMS source changed; preserve/review before updating')
        meta = json.loads((STATE / 'state.json').read_text())
        if value(meta['profile'], '802-11-wireless.band') != 'a':
            raise RuntimeError('Installed 5 GHz profile was edited')
        print('5 GHz installation already complete; configuration preserved.')
        return
    if not STATE.exists():
        cleanup_retired_firmware()
    if STATE.exists() or SOURCE.exists() or CONF.exists() or PREFIX.is_symlink():
        raise RuntimeError('Existing/incomplete 5 GHz installation requires recovery/review')
    kernel = os.uname().release
    if not re.fullmatch(r'7\.3\.0-\d+-generic', kernel):
        raise RuntimeError('Requires an audited Ubuntu 7.3.0 generic kernel')
    if args.install_deps:
        run('apt-get', 'update', timeout=600)
        run('apt-get', 'install', '--no-remove', '-y', 'build-essential', 'dkms',
            'linux-headers-' + kernel, 'linux-source-7.3.0', 'linux-firmware-broadcom-wireless',
            'wireless-regdb', 'iw', 'ethtool', 'iputils-ping', 'curl', 'zstd', 'mokutil', timeout=900)
    if signatures_required():
        raise RuntimeError('Signature enforcement is active; enrolled-key deployment is required')
    spec = importlib.util.spec_from_file_location('fiveg_builder', ROOT / 'wifi/build-5ghz.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.prepare.source_version(kernel)
    iface = check.interface(dev)
    profile = args.profile or run('nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', iface)
    if not args.profile and profile in ('', '--'):
        saved = run('nmcli', '-t', '-f', 'UUID,TYPE', 'connection', 'show').splitlines()
        choices = [line.split(':')[0] for line in saved if line.endswith((':802-11-wireless', ':wifi'))]
        if len(choices) == 1:
            profile = choices[0]
    if not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}', profile):
        raise RuntimeError('Select an existing trusted Wi-Fi profile with --profile UUID')
    if value(profile, 'connection.type') != '802-11-wireless':
        raise RuntimeError('Selected profile is not Wi-Fi')
    if value(profile, '802-11-wireless-security.key-mgmt') not in ('wpa-psk', 'sae'):
        raise RuntimeError('Only an existing WPA personal profile is supported by this component')
    if value(profile, '802-11-wireless-security.key-mgmt') == 'sae':
        raise RuntimeError('Use a separately saved WPA2 profile offered by your router; WPA3 is not rewritten')
    if check.command('nmcli', 'connection', 'show', 'MacBook T1 5 GHz')[0] == 0:
        raise RuntimeError('An unowned profile already uses the deployment name')
    for p in Path('/etc/modprobe.d').glob('*.conf'):
        if re.search(r'^\s*(?:options|install|blacklist)\s+brcmfmac\b', p.read_text(), re.M):
            raise RuntimeError('Existing brcmfmac module policy requires review: ' + str(p))
    previous = Path(run('modinfo', '-n', 'brcmfmac')).resolve()
    old_dkms = 'macbook-t1-wifi-dma'
    old_status = run('dkms', 'status', '-m', old_dkms, '-v', '1.0.0')
    if '/updates/dkms/' in str(previous) and ': installed' in old_status:
        previous_kind = 'dma'
    elif run('modinfo', '-F', 'intree', 'brcmfmac') == 'Y':
        previous_kind = 'stock'
    else:
        raise RuntimeError('Unowned wireless module selected; preserve/review it first')
    binary = Path('/usr/lib/firmware/brcm/brcmfmac43602-pcie.bin.zst')
    raw_binary = subprocess.check_output(['zstd', '-dc', str(binary)])
    if hashlib.sha256(raw_binary).hexdigest() != 'bf4cfc23ee952a3d82ef33a0f5f87853201c98f1bed034876a910f354f37862d':
        raise RuntimeError('Firmware differs from the verified 7.35.177.61 image')
    reference = args.reference_file.read_bytes() if args.reference_file else urllib.request.urlopen(REFERENCE_URL, timeout=30).read()
    if hashlib.sha256(reference).hexdigest() != REFERENCE_SHA:
        raise RuntimeError('Reference board-data checksum mismatch')
    mac = (Path('/sys/class/net') / iface / 'address').read_text().strip()
    text = reference.decode('ascii')
    for key, replacement in [('macaddr', mac), ('ccode', 'IN'), ('regrev', '0')]:
        text, count = re.subn('^' + key + '=.*$', key + '=' + replacement, text, flags=re.M)
        if count != 1:
            raise RuntimeError('Unexpected reference board-data format')
    STATE.mkdir(mode=0o700)
    meta = dict(kernel=kernel, original_profile=profile, previous_kind=previous_kind,
                previous_module=str(previous), previous_sha256=digest(previous),
                previous_srcversion=run('modinfo', '-F', 'srcversion', str(previous)),
                original_autoconnect=value(profile, 'connection.autoconnect'),
                initrd_sha256=digest(Path('/boot/initrd.img-' + kernel)),
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), profile=None)
    save('state.json', meta)
    save('files.json', {})
    shutil.copy2(previous, STATE / 'previous-module')
    shutil.copy2('/boot/initrd.img-' + kernel, STATE / 'previous-initrd')
    run('tar', '-cpf', str(STATE / 'network-before.tar'), '/etc/NetworkManager', '/etc/netplan', '/etc/modprobe.d')
    (STATE / 'network-before.tar').chmod(0o600)
    files = {}

    def deploy(path, data, mode=0o644):
        if path.exists() or path.is_symlink():
            raise RuntimeError('Refusing unowned destination: ' + str(path))
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        # Write-ahead ownership record permits interrupted-install cleanup.
        files[str(path)] = hashlib.sha256(data).hexdigest()
        save('files.json', files)
        with path.open('xb') as stream:
            stream.write(data)
        path.chmod(mode)

    try:
        print('Staging exact-source DKMS build...', flush=True)
        staged = builder.stage(STATE / 'build-stage', kernel)
        shutil.copytree(staged, SOURCE)
        conf = (SOURCE / 'dkms.conf').read_text().replace('macbook-t1-wifi-dma', PACKAGE)
        (SOURCE / 'dkms.conf').write_text(conf)
        save('source.json', source_manifest(SOURCE))
        run('dkms', 'add', '-m', PACKAGE, '-v', VERSION)
        log = run('dkms', 'build', '-m', PACKAGE, '-v', VERSION, '-k', kernel, timeout=600)
        (STATE / 'build.log').write_text(log)
        built = next((Path('/var/lib/dkms') / PACKAGE / VERSION / kernel / 'x86_64/module').glob('brcmfmac.ko*'))
        if run('modinfo', '-F', 'vermagic', str(built)).split()[0] != kernel:
            raise RuntimeError('DKMS module ABI mismatch')
        for name in ['check.py', 'radio.py', 'country.py']:
            deploy(PREFIX / name, (ROOT / 'wifi' / name).read_bytes())
        deploy(PREFIX / 'component_support.py', (ROOT / 'lib/component_support.py').read_bytes())
        deploy(PREFIX / 'deploy.py', Path(__file__).read_bytes())
        deploy(FW / 'brcmfmac43602-pcie.bin.zst', binary.read_bytes())
        deploy(FW / 'brcmfmac43602-pcie.txt', text.encode(), 0o600)
        # MODULE_FIRMWARE names do not include alternative_fw_path. Explicitly
        # include these files for Ubuntu 26.10's early-boot dracut driver load.
        dracut = ('# Owned by MacBook T1 5 GHz\ninstall_items+=" ' + str(FW / 'brcmfmac43602-pcie.bin.zst') +
                  ' ' + str(FW / 'brcmfmac43602-pcie.txt') + ' "\n')
        deploy(Path('/etc/dracut.conf.d/90-macbook-t1-wifi-5ghz.conf'), dracut.encode())
        unit = ('[Unit]\nDescription=Verify MacBook 5 GHz after boot; recover an unconfirmed deployment\nAfter=NetworkManager.service\n'
                '[Service]\nType=oneshot\nExecStart=/usr/bin/python3 ' + str(PREFIX / 'deploy.py') + ' boot-check\n')
        timer = '[Unit]\nDescription=Post-boot MacBook 5 GHz verification\n[Timer]\nOnBootSec=120s\nUnit=' + UNIT + '.service\n[Install]\nWantedBy=timers.target\n'
        deploy(Path('/etc/systemd/system') / (UNIT + '.service'), unit.encode())
        deploy(Path('/etc/systemd/system') / (UNIT + '.timer'), timer.encode())
        country = ('[Unit]\nDescription=Physical country for MacBook 5 GHz\nBefore=NetworkManager.service\n'
                   'After=systemd-udev-trigger.service\n[Service]\nType=oneshot\nRemainAfterExit=yes\n'
                   'ExecStart=/usr/bin/python3 ' + str(PREFIX / 'country.py') + ' IN\n'
                   '[Install]\nWantedBy=multi-user.target\n')
        deploy(Path('/etc/systemd/system/macbook-t1-wifi-5ghz-country.service'), country.encode())
        run('systemctl', 'daemon-reload')
        (STATE / 'boot-armed').touch()
        run('systemctl', 'enable', UNIT + '.timer')
        run('systemd-run', '--unit=' + WATCHDOG, '--on-active=45min', '--timer-property=AccuracySec=1s',
            '/usr/bin/python3', str(PREFIX / 'deploy.py'), 'rollback')
        if previous_kind == 'dma':
            (STATE / 'previous-dkms-removed').touch()
            run('dkms', 'remove', '-m', old_dkms, '-v', '1.0.0', '--all')
        run('dkms', 'install', '-m', PACKAGE, '-v', VERSION, '-k', kernel)
        run('depmod', '-a', kernel)
        expected = run('modinfo', '-k', kernel, '-F', 'srcversion', 'brcmfmac')
        meta['installed_srcversion'] = expected
        save('state.json', meta)
        deploy(CONF, b'# Owned by optional MacBook T1 5 GHz component\noptions brcmfmac alternative_fw_path=macbook-t1-5ghz fixed_regdom=1 legacy_80mhz=1\n')
        run('nmcli', 'connection', 'clone', 'uuid', profile, 'MacBook T1 5 GHz')
        meta['profile'] = run('nmcli', '-g', 'connection.uuid', 'connection', 'show', 'MacBook T1 5 GHz')
        save('state.json', meta)
        run('nmcli', 'connection', 'modify', 'uuid', meta['profile'], '802-11-wireless.band', 'a',
            '802-11-wireless.bssid', '', 'connection.autoconnect', 'yes',
            'connection.autoconnect-priority', '100')
        run('update-initramfs', '-u', '-k', kernel, timeout=300)
        run('systemctl', 'enable', '--now', 'macbook-t1-wifi-5ghz-country.service')
        (STATE / 'complete').touch()
        print('5 GHz installed on disk. Existing profile retained as fallback; no live driver unload performed.')
        print('A 45-minute rollback timer and first-boot verification are armed. Confirm after live validation.')
        if args.activate:
            activate(meta)
    except BaseException:
        if (STATE / 'live-attempt').exists():
            rollback_live()
        else:
            remove()
        raise


def remove():
    if not STATE.exists():
        print('5 GHz component is not installed.')
        return
    meta = json.loads((STATE / 'state.json').read_text())
    # Preserve later user edits; do not blindly remove files.
    records = json.loads((STATE / 'files.json').read_text())
    for path, sha in records.items():
        p = Path(path)
        if p.is_symlink() or (p.exists() and digest(p) != sha):
            raise RuntimeError('Later edit preserved; recovery needs review: ' + path)
    if SOURCE.exists() and (STATE / 'source.json').exists() and source_manifest(SOURCE) != json.loads((STATE / 'source.json').read_text()):
        raise RuntimeError('Installed 5 GHz source was edited; preserve/review before removal')
    run('systemctl', 'stop', WATCHDOG + '.timer', required=False)
    run('systemctl', 'disable', '--now', UNIT + '.timer', required=False)
    run('systemctl', 'disable', '--now', 'macbook-t1-wifi-5ghz-country.service', required=False)
    if meta.get('profile'):
        run('nmcli', 'connection', 'delete', 'uuid', meta['profile'], required=False)
    run('dkms', 'remove', '-m', PACKAGE, '-v', VERSION, '--all', required=False)
    if meta['previous_kind'] == 'dma' and (STATE / 'previous-dkms-removed').exists():
        run('dkms', 'add', '-m', 'macbook-t1-wifi-dma', '-v', '1.0.0', required=False)
        run('dkms', 'install', '-m', 'macbook-t1-wifi-dma', '-v', '1.0.0', '-k', meta['kernel'], timeout=600, required=False)
    previous = Path(meta['previous_module'])
    previous.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STATE / 'previous-module', previous)
    previous.chmod(0o644)
    if digest(previous) != meta['previous_sha256']:
        raise RuntimeError('Original module restoration checksum failed')
    # Keep the board-data directory as a private recovery artifact: a still-live
    # driver may request it before reboot. Default module configuration is restored.
    live = Path('/sys/module/brcmfmac/parameters/alternative_fw_path')
    retain_fw = live.exists() and live.read_text().strip() == 'macbook-t1-5ghz'
    for path in reversed(list(records)):
        if not retain_fw or not path.startswith(str(FW.parent) + '/'):
            Path(path).unlink(missing_ok=True)
    if not retain_fw and FW.exists():
        FW.rmdir()
        FW.parent.rmdir()
    run('depmod', '-a', meta['kernel'])
    if digest(STATE / 'previous-initrd') != meta['initrd_sha256']:
        raise RuntimeError('Backup initramfs checksum mismatch; current boot image preserved')
    shutil.copy2(STATE / 'previous-initrd', '/boot/initrd.img-' + meta['kernel'])
    run('nmcli', 'connection', 'modify', 'uuid', meta['original_profile'],
        'connection.autoconnect', meta['original_autoconnect'])
    run('systemctl', 'daemon-reload')
    (STATE / 'boot-armed').unlink(missing_ok=True)
    if SOURCE.exists():
        SOURCE.rename(STATE / 'retired-source')
    archive = STATE.with_name(STATE.name + '-removed-' + str(time.time_ns()))
    STATE.rename(archive)
    print('Previous module/initramfs/profile restored on disk. Reboot applies driver recovery. Backup: ' + str(archive))


def boot_check():
    meta = json.loads((STATE / 'state.json').read_text())
    # DKMS can legitimately produce a different srcversion after a compatible
    # kernel update. Compare against the provider for the running ABI, not the
    # srcversion recorded on the original installation day.
    kernel = os.uname().release
    expected = None
    provider_ok = False
    try:
        status = run('dkms', 'status', '-m', PACKAGE, '-v', VERSION, '-k', kernel)
        expected = run('modinfo', '-k', kernel, '-F', 'srcversion', 'brcmfmac')
        provider = run('modinfo', '-k', kernel, '-F', 'filename', 'brcmfmac')
        provider_ok = ': installed' in status and '/updates/dkms/' in provider
    except (OSError, RuntimeError, subprocess.SubprocessError):
        pass  # A missing provider must reach the armed recovery path below.
    same_boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip() == meta['boot_id']
    success = False
    for _ in range(12):
        try:
            snap = check.snapshot(online=True, radio_info=True)
            freq = snap['link'].get('frequency_mhz') or 0
            success = (check.healthy(snap, True) and 4900 < freq < 5900 and
                       provider_ok and snap['loaded_driver_srcversion'] == expected)
        except (OSError, RuntimeError, ValueError) as error:
            snap = {'error': type(error).__name__}
        save('postboot.json', {'same_install_boot': same_boot, 'success': success, 'snapshot': snap})
        if success:
            if not same_boot:
                (STATE / 'boot-validated').touch()
                (STATE / 'boot-armed').unlink(missing_ok=True)
            print('5 GHz boot verification passed.' if not same_boot else '5 GHz live verification passed; reboot not tested.')
            return
        time.sleep(5)
    if (STATE / 'boot-armed').exists() and not same_boot:
        remove()
        # Disk, original initramfs and autoconnect state are restored before one
        # recovery reboot. Removing the armed state prevents a reboot loop.
        run('systemctl', 'reboot')
    raise RuntimeError('5 GHz verification failed; inspect private postboot.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall', 'rollback', 'boot-check', 'confirm'])
    parser.add_argument('--profile')
    parser.add_argument('--reference-file', type=Path, help='Optional offline pinned reference file')
    parser.add_argument('--activate', action='store_true', help='Activate after safe P2P quiescence; requires verified Ethernet')
    parser.add_argument('--install-deps', action='store_true', help='Install Ubuntu dependencies without replacing the kernel/initramfs provider')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    os.umask(0o077)
    with Path('/run/macbook-t1-wifi-5ghz.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'install':
            install(args)
        elif args.action == 'uninstall':
            remove()
        elif args.action == 'rollback':
            rollback_live()
        elif args.action == 'boot-check':
            boot_check()
        else:
            boot_check()
            run('systemctl', 'stop', WATCHDOG + '.timer')
            (STATE / 'live-confirmed').touch()
            print('Live configuration confirmed; first-boot recovery remains armed until a verified reboot.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
