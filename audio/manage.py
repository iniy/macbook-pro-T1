#!/usr/bin/env python3
"""Install/remove the audio component without touching the iBridge stack."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from component_support import audio_codec, host, output, run, signatures_required, transaction
sys.path.insert(0, str(ROOT / 'audio'))
from prepare import source_version

NAME, VERSION = 'macbook-t1-audio', '1.0.0'
STATE = Path('/var/lib/macbook-t1-audio')
SOURCE = Path('/usr/src') / f'{NAME}-{VERSION}'
SIGNING = Path('/var/lib/macbook-t1-audio-signing')
FILES = {
    'audio/config/51-macbook-t1-audio.conf': '/etc/wireplumber/wireplumber.conf.d/51-macbook-t1-audio.conf',
    'audio/config/dkms-signing.conf': '/etc/dkms/framework.conf.d/zz-macbook-t1-audio.conf',
}


def dkms_installed(kernel):
    return ': installed' in output('dkms', 'status', '-m', NAME, '-v', VERSION, '-k', kernel)


def signing_key(required):
    if SIGNING.is_symlink():
        raise RuntimeError('Refusing symlink signing directory')
    SIGNING.mkdir(mode=0o700, exist_ok=True)
    key, cert = SIGNING / 'MOK.priv', SIGNING / 'MOK.der'
    if not key.exists() and not cert.exists():
        # Reuse an enrolled Ubuntu key if available; never request EFI enrollment.
        existing = [(Path('/var/lib/shim-signed/mok/MOK.priv'), Path('/var/lib/shim-signed/mok/MOK.der')),
                    (Path('/var/lib/dkms/mok.key'), Path('/var/lib/dkms/mok.pub'))]
        for private, public in existing:
            if private.is_file() and public.is_file():
                key.symlink_to(private)
                cert.symlink_to(public)
                break
        else:
            previous = os.umask(0o077)
            try:
                run('openssl', 'req', '-new', '-x509', '-nodes', '-days', '3650', '-newkey', 'rsa:2048',
                    '-subj', '/CN=MacBook T1 audio module signing/', '-addext', 'extendedKeyUsage=codeSigning',
                    '-keyout', key, '-outform', 'DER', '-out', cert, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
            finally:
                os.umask(previous)
    if not key.is_file() or not cert.is_file():
        raise RuntimeError('Incomplete audio signing key pair')
    if required:
        p = subprocess.run(['mokutil', '--ignore-keyring', '--test-key', str(cert)], capture_output=True, text=True)
        if p.returncode or 'is already enrolled' not in p.stdout + p.stderr:
            raise RuntimeError('Signature enforcement requires an already enrolled certificate; no enrollment attempted')
    return cert


def install(deps):
    host(root=True)
    audio_codec()
    kernel = os.uname().release
    if not re.fullmatch(r'7\.3\.0-\d+-generic', kernel):
        raise RuntimeError('Unsupported audio kernel family')
    if deps:
        packages = ['build-essential', 'dkms', 'openssl', 'mokutil', 'zstd', 'patch',
                    'linux-headers-' + kernel, 'pipewire', 'pipewire-pulse', 'wireplumber',
                    'pulseaudio-utils', 'alsa-utils']
        run('apt-get', 'install', '--no-remove', '-y', *packages)
    version = source_version(kernel)
    if deps and not (ROOT / 'audio/kernel-source' / version).is_dir():
        run('apt-get', 'install', '--no-remove', '-y', 'linux-source-7.3.0=' + version)
    required = signatures_required()
    if (STATE / 'complete').is_file():
        for name in ['SOURCE-SHA256.json', 'Makefile', 'dkms.conf', 'prepare.py']:
            if (SOURCE / name).read_bytes() != (ROOT / 'audio' / name).read_bytes():
                raise RuntimeError('Installed audio build inputs differ; uninstall audio before replacing its implementation')
        if not dkms_installed(kernel):
            run('dkms', 'install', '-m', NAME, '-v', VERSION, '-k', kernel)
        print('Audio component already installed; configuration and live modules preserved.')
        return
    if STATE.exists() or STATE.is_symlink() or SOURCE.exists() or SOURCE.is_symlink():
        raise RuntimeError('Existing audio transaction/source; run uninstall-audio.sh before retrying')
    selected = output('modinfo', '-F', 'filename', 'snd_hda_codec_cs8409')
    if '/updates/' in selected or '/extra/' in selected:
        raise RuntimeError('Competing CS8409 module installed; resolve its ownership first')
    if any(line.startswith(('snd_hda_macbookpro/', 'macbook-t1-audio/')) for line in output('dkms', 'status').splitlines()):
        raise RuntimeError('Competing audio DKMS registration')
    STATE.mkdir(mode=0o700)
    initrd = Path('/boot') / ('initrd.img-' + kernel)
    if initrd.is_file():
        saved = STATE / ('initrd-before-' + kernel)
        shutil.copy2(initrd, saved)
        (STATE / 'initrd-before.sha256').write_text(hashlib.sha256(saved.read_bytes()).hexdigest() + '\n')
    tx = transaction()
    tx.FILES = FILES
    added = False
    try:
        cert = signing_key(required)
        shutil.copytree(ROOT / 'audio', SOURCE, ignore=shutil.ignore_patterns('build', '__pycache__'))
        tx.deploy(ROOT, STATE, usbmux=False)
        run('dkms', 'add', '-m', NAME, '-v', VERSION)
        added = True
        run('dkms', 'build', '-m', NAME, '-v', VERSION, '-k', kernel)
        built = Path('/var/lib/dkms') / NAME / VERSION / kernel / os.uname().machine / 'module'
        modules = list(built.glob('snd-hda-codec-cs8409.ko*'))
        if len(modules) != 1:
            raise RuntimeError('Missing or ambiguous built audio module')
        run('python3', ROOT / 'lib/check-signature.py', modules[0], cert)
        if not output('modinfo', '-F', 'vermagic', modules[0]).startswith(kernel + ' '):
            raise RuntimeError('Audio module ABI mismatch')
        run('dkms', 'install', '-m', NAME, '-v', VERSION, '-k', kernel)
        run('depmod', '-a', kernel)
        run('update-initramfs', '-u', '-k', kernel)
        (STATE / 'complete').write_text(json.dumps({'kernel': kernel, 'source_version': version}) + '\n')
        print('Audio installed. Activate with a controlled audio-only reload or normal reboot; playback must use PipeWire.')
    except BaseException:
        if added:
            subprocess.run(['dkms', 'remove', '-m', NAME, '-v', VERSION, '--all'])
        restored = tx.restore(STATE)
        if SOURCE.is_dir() and not SOURCE.is_symlink():
            shutil.rmtree(SOURCE)
        subprocess.run(['depmod', '-a', kernel])
        subprocess.run(['update-initramfs', '-u', '-k', kernel])
        print('Audio install failed; owned-file rollback attempted. Restored:', restored, file=sys.stderr)
        raise


def uninstall():
    host(root=True)
    if not STATE.exists():
        print('No owned audio installation.')
        return
    if STATE.is_symlink():
        raise RuntimeError('Refusing symlink transaction')
    status = output('dkms', 'status', '-m', NAME, '-v', VERSION)
    if status:
        run('dkms', 'remove', '-m', NAME, '-v', VERSION, '--all')
    if not transaction().restore(STATE):
        raise RuntimeError('Later audio configuration edits preserved; review files.json before retrying')
    if SOURCE.is_dir() and not SOURCE.is_symlink():
        shutil.rmtree(SOURCE)
    run('depmod', '-a')
    run('update-initramfs', '-u', '-k', 'all')
    STATE.rename(STATE.with_name(STATE.name + '-removed-' + str(time.time_ns())))
    print('Audio component removed. Reboot to return to stock CS8409; Touch Bar and camera were preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('--install-deps', action='store_true')
    args = parser.parse_args()
    try:
        host(root=True)
        with open('/run/macbook-t1-audio.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            install(args.install_deps) if args.action == 'install' else uninstall()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
