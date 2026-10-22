# SPDX-License-Identifier: MIT
"""Ubuntu-only, one-boot hardware trial. The normal initramfs/modules stay intact."""
import grp
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import time

import adapters
from build import PREFIX, LOCK
from deploy import verify
from probe import inspect
from transaction import Transaction, atomic, safe

STATE = Path('/var/lib/macbook-t1-touchid-trial')
FLAG = 't1bridge.trial=1'
ENTRY = 'macbook-t1-touchid-trial'
HERE = Path(__file__).resolve().parent
UNITS = ('t1-touchbar-hw.service', 't1-touchid-auth.socket',
         't1bridge-fingerprint.socket', 't1bridge-import.service')


def run(*args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def booted():
    return FLAG in Path('/proc/cmdline').read_text().split()


def menuentry(config, kernel, image):
    """Clone the running-kernel menu's boot logic, changing only name/initrd/flag."""
    entries = []
    lines = config.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith('menuentry '):
            block, depth = [], 0
            while i < len(lines):
                line = lines[i]
                block.append(line)
                depth += line.count('{') - line.count('}')
                i += 1
                if depth == 0:
                    break
            linux = [x for x in block if x.lstrip().startswith(('linux ', 'linux\t'))]
            if len(linux) == 1 and '/vmlinuz-' + kernel in linux[0] and ' recovery' not in linux[0]:
                entries.append(block)
        else:
            i += 1
    if len(entries) != 1:
        raise RuntimeError('Expected one top-level normal GRUB entry for the running kernel')
    block = entries[0]
    block[0] = "menuentry 'MacBook T1Bridge one-boot hardware trial' --id '" + ENTRY + "' {"
    changed = 0
    for index, line in enumerate(block):
        words = line.split()
        if words and words[0] == 'linux':
            if any('t1bridge.trial' in w for w in words):
                raise RuntimeError('Existing kernel command already contains a trial flag')
            block[index] = line + ' ' + FLAG
        if words and words[0] == 'initrd':
            matches = [w for w in words[1:] if Path(w).name == 'initrd.img-' + kernel]
            if len(matches) != 1:
                raise RuntimeError('Unrecognized GRUB initrd layout')
            old = matches[0]
            block[index] = line.replace(old, str(Path(old).with_name(image)))
            changed += 1
    if changed != 1:
        raise RuntimeError('Expected one initrd command')
    return '\n'.join(block) + '\n'


def conditioned(text):
    if '[Unit]\n' not in text:
        raise RuntimeError('Unit has no Unit section')
    return text.replace('[Unit]\n', '[Unit]\nConditionKernelCommandLine=' + FLAG + '\n', 1)


def prepare(user):
    if os.geteuid() != 0:
        raise RuntimeError('Trial staging requires root')
    host = inspect()
    adapters.Systemd.require(host)
    if (host['model'], host['distro'], host['version'], host['kernel'], host['arch']) != (
            'MacBookPro13,2', 'ubuntu', '26.10', '7.3.0-9-generic', 'x86_64'):
        raise RuntimeError('One-boot trial adapter is only implemented for the recorded Ubuntu build host')
    if booted():
        raise RuntimeError('Already in the trial; finish physical tests before changing boot staging')
    if host['fdr'] != 'present' or not host['headers_match'] or len(host['t1_devices']) != 1:
        raise RuntimeError('EFI, headers or T1 preflight failed')
    if host['t1_devices'][0]['configuration'] != '1':
        raise RuntimeError('Unexpected T1 configuration; refusing migration')
    account = pwd.getpwnam(user)
    if account.pw_uid < 1000:
        raise RuntimeError('A normal local graphical account is required')
    manifest = verify(PREFIX)
    if manifest.get('kernel') != host['kernel'] or not manifest.get('tests_requested'):
        raise RuntimeError('Require a tested bundle built for the running kernel')
    for tool in ('dkms', 'dracut', 'depmod', 'grub-reboot', 'grub-editenv', 'lsinitrd'):
        if not shutil.which(tool):
            raise RuntimeError('Missing trial tool: ' + tool)
    for setting in (Path('/sys/module/module/parameters/sig_enforce'), Path('/sys/kernel/security/lockdown')):
        if setting.exists() and any(x in setting.read_text() for x in ('[integrity]', '[confidentiality]')):
            raise RuntimeError('Kernel lockdown requires a separately validated signing/boot adapter')
    enforce = Path('/sys/module/module/parameters/sig_enforce')
    if enforce.exists() and enforce.read_text().strip() in ('Y', '1'):
        raise RuntimeError('Signature-enforced trial is not implemented')
    if STATE.exists():
        previous = STATE / 'state.json'
        if previous.is_file() and json.loads(previous.read_text()).get('phase') == 'rolled-back':
            STATE.rename(STATE.with_name(STATE.name + '.history-' + str(time.time_ns())))
        else:
            raise RuntimeError('Trial state already exists; verify or roll it back before another staging attempt')
    grub = Path('/boot/grub/grub.cfg').read_text()
    if 'custom.cfg' not in grub:
        raise RuntimeError('GRUB does not include custom.cfg; refusing to rewrite normal boot entries')
    grubenv = subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True)
    if any(line.startswith('next_entry=') for line in grubenv.splitlines()):
        raise RuntimeError('A one-time boot choice is already pending; preserve it')
    kernel = host['kernel']
    image = 'initrd.img-' + kernel + '-t1bridge-trial'
    entry = menuentry(grub, kernel, image)
    if Path('/boot/grub/custom.cfg').exists() or Path('/boot', image).exists():
        raise RuntimeError('Existing custom GRUB file or trial image is not owned by this transaction')
    if 'ExecStart=/usr/libexec/fprintd\n' not in Path('/usr/lib/systemd/system/fprintd.service').read_text():
        raise RuntimeError('Unknown distro fprintd command; preserve local configuration')
    src = Path('/usr/src/t1bridge-dkms-' + LOCK['t1bridge']['version'])
    if src.exists() or 't1bridge-dkms' in subprocess.check_output(['dkms', 'status'], text=True):
        raise RuntimeError('Existing T1Bridge DKMS owner; refusing to overwrite')
    STATE.mkdir(mode=0o700)
    tx = Transaction(STATE / 'files')
    meta = {'user': user, 'added_group': False, 'dkms_added': False, 'source': str(src),
            'kernel': kernel, 'image': image, 'enabled': [], 'phase': 'preparing'}
    def save():
        atomic(STATE / 'state.json', (json.dumps(meta, indent=2) + '\n').encode())
    # Keep configuration backups private and baseline hashes independently of Git.
    from build import digest
    baseline = {str(p): digest(p) for p in (Path('/boot/vmlinuz-' + kernel),
                Path('/boot/initrd.img-' + kernel), Path('/boot/grub/grub.cfg'))}
    atomic(STATE / 'baseline-sha256.json', (json.dumps(baseline, indent=2) + '\n').encode())
    save()
    try:
        # A copy, never hardlinks: depmod cannot change the normal module tree.
        module_root = STATE / 'module-root'
        destination = module_root / 'lib/modules' / kernel
        shutil.copytree(Path('/lib/modules') / kernel, destination, symlinks=True)
        shutil.copytree(PREFIX / 'integration/kernel', src)
        # The source bundle's DKMS Makefile expects kernel/ beneath its root.
        kernel_tree = src / 'kernel'
        kernel_tree.mkdir()
        for path in list(src.iterdir()):
            if path.name not in ('kernel', 'dkms.conf'):
                path.rename(kernel_tree / path.name)
        meta['dkms_added'] = True
        save()
        run('dkms', 'add', '-m', 't1bridge-dkms', '-v', LOCK['t1bridge']['version'])
        run('dkms', 'build', '-m', 't1bridge-dkms', '-v', LOCK['t1bridge']['version'], '-k', kernel)
        built = Path('/var/lib/dkms/t1bridge-dkms') / LOCK['t1bridge']['version'] / kernel / 'x86_64/module'
        target = destination / 'updates/t1bridge-trial'
        target.mkdir(parents=True)
        for name in ('t1_cfgsel', 'appletbdrm', 'apple_t1_ncm', 'uvcvideo'):
            matches = list(built.glob(name + '.ko*'))
            if len(matches) != 1:
                raise RuntimeError('Missing trial module: ' + name)
            run('modinfo', '-F', 'vermagic', matches[0], stdout=subprocess.DEVNULL)
            shutil.copy2(matches[0], target / matches[0].name)
        run('depmod', '-b', module_root, kernel)
        install_configuration(tx)
        # This image is separate; /boot/initrd.img-<kernel> stays byte-identical.
        run('dracut', '--force', '--kmoddir', destination, '--force-drivers',
            't1_cfgsel appletbdrm apple_t1_ncm uvcvideo',
            '--include', '/etc/udev/rules.d/90-t1bridge-xart.rules', '/etc/udev/rules.d/90-t1bridge-xart.rules',
            '--include', '/etc/systemd/network/50-t1bridge-ncm.link', '/etc/systemd/network/50-t1bridge-ncm.link',
            Path('/boot') / image, kernel)
        listing = subprocess.check_output(['lsinitrd', str(Path('/boot') / image)], text=True)
        for name in ('t1_cfgsel.ko', 'appletbdrm.ko', 'apple_t1_ncm.ko', 'uvcvideo.ko'):
            if 'updates/t1bridge-trial/' + name not in listing:
                raise RuntimeError('Trial image does not contain the intended module: ' + name)
        groups = os.getgrouplist(user, account.pw_gid)
        run('systemd-sysusers', PREFIX / 'integration/systemd/t1bridge.sysusers')
        if grp.getgrnam('t1bridge').gr_gid not in groups:
            meta['added_group'] = True
            save()
            run('usermod', '-aG', 't1bridge', user)
        run('systemd-tmpfiles', '--create', PREFIX / 'integration/systemd/t1bridge.conf')
        run('systemctl', 'daemon-reload')
        units = [str(Path('/etc/systemd/system') / p.name) for p in (PREFIX / 'integration/systemd').glob('*.service')]
        units += [str(Path('/etc/systemd/system') / p.name) for p in (PREFIX / 'integration/systemd').glob('*.socket')]
        run('systemd-analyze', 'verify', '--man=no', *units)
        for unit in UNITS:
            meta['enabled'].append(unit)
            save()
            run('systemctl', 'enable', unit)
        meta['enabled'].append('user:t1-touchbar.service')
        save()
        run('systemctl', '--global', 'enable', 't1-touchbar.service')
        tx.put('boot/grub/custom.cfg', entry.encode(), 0o600)
        run('grub-script-check', '/boot/grub/custom.cfg')
        if any(digest(Path(p)) != expected for p, expected in baseline.items()):
            raise RuntimeError('A normal boot artifact changed; do not arm the trial')
        # Arm only after everything is staged. GRUB clears this one-time choice.
        run('grub-reboot', ENTRY)
        meta['phase'] = 'armed'
        save()
        print('One-boot T1Bridge trial armed. Reboot when ready. The following normal boot uses the original image.')
    except BaseException:
        rollback()
        raise


def install_configuration(tx):
    source = PREFIX / 'integration/systemd'
    for path in [*source.glob('*.service'), *source.glob('*.socket')]:
        content = path.read_text().replace('/usr/lib/t1bridge/', str(PREFIX / 'libexec') + '/')
        content = content.replace('/usr/bin/t1bridge', str(PREFIX / 'bin/t1bridge'))
        content = content.replace('/usr/bin/t1-touchid', str(PREFIX / 'bin/t1-touchid'))
        if path.name == 't1bridge-import.service':
            content = content.replace('[Unit]\n', '[Unit]\nAfter=t1-touchbar-hw.service\n')
            content += '\n[Install]\nWantedBy=multi-user.target\n'
        tx.put('etc/systemd/system/' + path.name, conditioned(content).encode())
    user_unit = (source / 'user/t1-touchbar.service').read_text().replace('/usr/lib/t1bridge/', str(PREFIX / 'libexec') + '/')
    user_unit = user_unit.replace('[Service]\n', '[Service]\nEnvironment=T1BRIDGE_DESKTOP_PROVIDER=/usr/local/libexec/macbook-t1-touchid-desktop\n')
    tx.put('etc/systemd/user/t1-touchbar.service', conditioned(user_unit).encode())
    tx.put('usr/local/libexec/macbook-t1-touchid-desktop', (HERE / 'desktop-provider.py').read_bytes(), 0o755)
    for path in source.glob('*.rules'):
        tx.put('etc/udev/rules.d/' + path.name, path.read_bytes())
    tx.put('etc/systemd/network/50-t1bridge-ncm.link', (source / '50-t1bridge-ncm.link').read_bytes())
    tx.put('etc/tmpfiles.d/macbook-t1-touchid-trial.conf', (source / 't1bridge.conf').read_bytes())
    tx.put('etc/systemd/system/macbook-t1-touchbar.service.d/90-t1bridge-trial.conf',
           ('[Unit]\nConditionKernelCommandLine=!' + FLAG + '\n').encode())
    launcher = ('#!/usr/bin/python3\nimport os\nfrom pathlib import Path\n'
                'trial = "t1bridge.trial=1" in Path("/proc/cmdline").read_text().split()\n'
                'binary = "' + str(PREFIX / 'libexec/fprintd') + '" if trial else "/usr/libexec/fprintd"\n'
                'os.execv(binary, [binary])\n')
    tx.put('usr/local/libexec/macbook-t1-fprintd-trial', launcher.encode(), 0o755)
    tx.put('etc/systemd/system/fprintd.service.d/90-t1bridge-trial.conf',
           b'[Service]\nExecStart=\nExecStart=/usr/local/libexec/macbook-t1-fprintd-trial\n')


def rollback():
    if not STATE.exists():
        return
    if booted():
        raise RuntimeError('Reboot into the normal entry before rollback; never hot-remove the live T1 stack')
    meta = json.loads((STATE / 'state.json').read_text())
    grubenv = subprocess.check_output(['grub-editenv', '/boot/grub/grubenv', 'list'], text=True)
    if 'next_entry=' + ENTRY in grubenv.splitlines():
        run('grub-editenv', '/boot/grub/grubenv', 'unset', 'next_entry')
    for unit in reversed(meta['enabled']):
        if unit.startswith('user:'):
            run('systemctl', '--global', 'disable', unit.split(':', 1)[1])
        else:
            run('systemctl', 'disable', unit)
    Transaction(STATE / 'files').rollback()
    run('systemctl', 'daemon-reload')
    if meta['added_group']:
        run('gpasswd', '-d', meta['user'], 't1bridge')
        meta['added_group'] = False
        atomic(STATE / 'state.json', (json.dumps(meta, indent=2) + '\n').encode())
    if meta['dkms_added']:
        result = subprocess.run(['dkms', 'remove', '-m', 't1bridge-dkms', '-v', LOCK['t1bridge']['version'], '--all'])
        if result.returncode and Path('/var/lib/dkms/t1bridge-dkms', LOCK['t1bridge']['version']).exists():
            raise RuntimeError('DKMS cleanup failed; private recovery state retained')
    src = safe(Path(meta['source']))
    if src.exists():
        shutil.rmtree(src)
    (Path('/boot') / meta['image']).unlink(missing_ok=True)
    meta['phase'] = 'rolled-back'
    atomic(STATE / 'state.json', (json.dumps(meta, indent=2) + '\n').encode())
    print('Trial configuration removed. Normal modules and initramfs were never replaced. Private state retained.')
