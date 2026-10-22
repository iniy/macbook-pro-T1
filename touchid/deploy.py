# SPDX-License-Identifier: MIT
"""Install an inert private bundle. Live hardware migration is separately gated."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from build import LOCK, PREFIX, digest
from transaction import safe, atomic


def verify(bundle):
    bundle = bundle.resolve()
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest.get('lock') != LOCK or manifest.get('schema') != 1:
        raise RuntimeError('Bundle source/version lock does not match this integration')
    actual = {str(p.relative_to(bundle)) for p in bundle.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(manifest['files']) | {'manifest.json'}:
        raise RuntimeError('Bundle has missing or unexpected files')
    for name, item in manifest['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('Unsafe bundle path')
        path = bundle / name
        if 'symlink' in item:
            if not path.is_symlink() or os.readlink(path) != item['symlink'] or not path.resolve().is_relative_to(bundle):
                raise RuntimeError('Unsafe bundle link: ' + name)
        elif path.is_symlink() or digest(path) != item['sha256'] or path.stat().st_mode & 0o777 != item['mode']:
            raise RuntimeError('Bundle checksum/mode mismatch: ' + name)
    return manifest


def install(bundle, root=Path('/')):
    """Does not install systemd units, modprobe configuration, DKMS or PAM."""
    if root == Path('/') and os.geteuid() != 0:
        raise RuntimeError('Private bundle installation requires root')
    manifest = verify(bundle)
    target = safe(root / PREFIX.relative_to('/'))
    if target.exists():
        if verify(target) != manifest:
            raise RuntimeError('Installed bundle differs; preserving it')
        return target
    safe(target.parent)
    parent_existed = target.parent.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not parent_existed:
        target.parent.chmod(0o755)
    staging = Path(tempfile.mkdtemp(prefix='.install-', dir=target.parent))
    try:
        shutil.copytree(bundle, staging, dirs_exist_ok=True, symlinks=True)
        verify(staging)
        for path in staging.rglob('*'):
            if not path.is_symlink() and path.is_dir():
                path.chmod(0o755)
        staging.chmod(0o755)
        # Publication occurs only after a complete verified copy.
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def uninstall(root=Path('/')):
    target = safe(root / PREFIX.relative_to('/'))
    if not target.exists():
        return
    verify(target)
    # Refuse removal if any active configuration refers to this private prefix.
    for base in ('etc/systemd/system', 'etc/dbus-1', 'etc/pam.d'):
        for path in (root / base).rglob('*'):
            if path.is_file() and not path.is_symlink() and str(PREFIX).encode() in path.read_bytes():
                raise RuntimeError('Restore active configuration before removing bundle: ' + str(path))
    shutil.rmtree(target)
    # Never remove /var/lib/t1bridge, EFI, fingerprints or unrelated dependencies.


def package_deb(bundle, output):
    import subprocess
    manifest = verify(bundle)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        shutil.copytree(bundle, root / PREFIX.relative_to('/'), symlinks=True)
        control = root / 'DEBIAN/control'
        control.parent.mkdir()
        # Let dpkg calculate ABI/version dependencies on this build host. The
        # private libfprint travels in this package, not in libfprint-2-2.
        debian = root / 'debian'
        debian.mkdir()
        (debian / 'control').write_text(
            'Source: macbook-t1-touchid-bundle\nSection: admin\nPriority: optional\n'
            'Maintainer: macbook-pro-T1 contributors\nStandards-Version: 4.6.2\n\n'
            'Package: macbook-t1-touchid-bundle\nArchitecture: amd64\nDescription: Private evaluation bundle\n')
        elf = [p for p in bundle.rglob('*') if p.is_file() and not p.is_symlink()
               and p.open('rb').read(4) == b'\x7fELF']
        result = subprocess.check_output(['dpkg-shlibdeps', '--ignore-missing-info', '-O',
                  '-l' + str(bundle.resolve() / 'lib'), '-xlibfprint-2-2',
                  *['-e' + str(p.resolve()) for p in elf]], cwd=root, text=True)
        dependencies = next(line.split('=', 1)[1] for line in result.splitlines() if line.startswith('shlibs:Depends='))
        shutil.rmtree(debian)
        control.write_text(
            'Package: macbook-t1-touchid-bundle\nVersion: 0.1.0\nArchitecture: amd64\n'
            'Maintainer: macbook-pro-T1 contributors\nSection: admin\nPriority: optional\n'
            'Depends: ' + dependencies + '\n'
            'Description: Inert private T1Bridge evaluation bundle\n'
            ' Does not activate drivers, services, or authentication.\n')
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', root, output], check=True)
    return manifest
