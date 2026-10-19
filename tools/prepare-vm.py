#!/usr/bin/env python3
"""Prepare an isolated Ubuntu 26.10 cloud VM. No host block/USB passthrough."""
import hashlib
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / 'build-env'
for relative in ['vm.qcow2', 'seed.iso', 'seed/user-data', 'seed/meta-data']:
    if (ENV / relative).exists():
        raise SystemExit('Refusing to overwrite existing VM state: ' + relative)
base = 'https://cloud-images.ubuntu.com/releases/stonking/release/'
checksums = urllib.request.urlopen(base + 'SHA256SUMS').read().decode()
(ENV / 'ubuntu-26.10-SHA256SUMS').write_text(checksums)
expected = next(line.split()[0] for line in checksums.splitlines()
                if line.endswith('ubuntu-26.10-server-cloudimg-amd64.img'))
with (ENV / 'ubuntu-26.10.img').open('rb') as f:
    actual = hashlib.file_digest(f, 'sha256').hexdigest()
assert actual == expected, 'Image checksum failed'
print('Ubuntu 26.10 image SHA256 verified:', actual)
key = ENV / 'vm-key'
if not key.exists():
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C',
                    'isolated-t1-build', '-f', str(key)], check=True)
seed = ENV / 'seed'
seed.mkdir(exist_ok=True)
(seed / 'meta-data').write_text('instance-id: t1-build-2610\nlocal-hostname: t1-build\n')
(seed / 'user-data').write_text('''#cloud-config
users:
  - name: builder
    groups: [sudo]
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - ''' + key.with_suffix('.pub').read_text().strip() + '''
ssh_pwauth: false
disable_root: true
package_update: true
packages:
  - build-essential
  - dkms
  - linux-headers-generic
  - gcc-16
  - python3
  - shellcheck
  - sparse
  - mokutil
  - openssl
  - usbutils
  - initramfs-tools
''')
subprocess.run(['hdiutil', 'makehybrid', '-iso', '-joliet', '-default-volume-name',
                'cidata', '-o', str(ENV / 'seed.iso'), str(seed)], check=True)
env = dict(os.environ, QEMU_FRAMEWORK=str(ENV / 'UTM.app/Contents/Frameworks/qemu-img.framework/qemu-img'))
subprocess.run([str(ENV / 'qemu-launch'), 'create', '-f', 'qcow2', '-F', 'qcow2',
                '-b', str(ENV / 'ubuntu-26.10.img'), str(ENV / 'vm.qcow2'), '16G'], env=env, check=True)
