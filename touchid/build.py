# SPDX-License-Identifier: MIT
"""Pinned, unprivileged source builds. No host driver, service or PAM writes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / 'sources.lock.json').read_text())
PREFIX = Path(LOCK['prefix'])
RUST_TARGETS = [
    ('t1-touchbar-hw', 't1-touchbar-hw', 'service'),
    ('t1-touchbar', 't1-touchbar', None),
    ('t1-daemons', 't1-xart-storage', None),
    ('t1-daemons', 't1-ncm-ready', None),
    ('t1-daemons', 't1-keybag-relay', 'keybag-relay-service'),
    ('t1-daemons', 't1-touchid-auth', 'auth-broker-service'),
    ('t1-daemons', 't1-touchid', None),
    ('t1-import', 't1bridge', None),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*command, cwd=None, env=None):
    print('+', ' '.join(map(str, command)), flush=True)
    # Host umask 0002 creates group-writable test fixtures rejected by upstream's
    # protected-storage checks. Do not weaken those checks for a build account.
    subprocess.run(list(map(str, command)), cwd=cwd, env=env, check=True, umask=0o022)


def download(name, cache):
    item = LOCK[name]
    dest = cache / (name + '.tar.gz')
    if not dest.exists():
        partial = dest.with_suffix('.partial')
        try:
            with urllib.request.urlopen(item['url'], timeout=90) as response, partial.open('wb') as out:
                shutil.copyfileobj(response, out)
            if digest(partial) != item['sha256']:
                raise RuntimeError('Source checksum mismatch: ' + name)
            partial.replace(dest)
        finally:
            partial.unlink(missing_ok=True)
    if digest(dest) != item['sha256']:
        raise RuntimeError('Cached source checksum mismatch: ' + name)
    return dest


def fetch(work):
    work.mkdir(parents=True, exist_ok=True)
    upstream = work / 't1bridge'
    pin = LOCK['t1bridge']
    if not upstream.exists():
        run('git', 'clone', '--no-checkout', pin['url'], upstream)
        run('git', 'checkout', '--detach', pin['commit'], cwd=upstream)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upstream, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=upstream, text=True)
    if actual != pin['commit'] or dirty:
        raise RuntimeError('Upstream checkout differs from locked revision; refusing reuse')
    patches = sorted((HERE / 'patches').glob('*.patch'))
    if {p.name: digest(p) for p in patches} != LOCK.get('integration_patches', {}):
        raise RuntimeError('Integration patches differ from the source lock')
    for patch in patches:
        run('git', 'apply', '--check', patch, cwd=upstream)
        run('git', 'apply', patch, cwd=upstream)
    cache = work / 'downloads'
    cache.mkdir(exist_ok=True)
    for name in ('libfprint', 'fprintd'):
        archive = download(name, cache)
        dest = work / (name + '-' + LOCK[name]['commit'])
        if dest.exists():
            raise RuntimeError('Use a fresh work directory; existing patched source is not trusted: ' + name)
        with tarfile.open(archive) as tar:
            # Python >=3.12 safe extraction blocks path traversal and external links.
            tar.extractall(work, filter='data')
        for patch in sorted((upstream / 'packaging/arch' / (name + '-t1bridge')).glob('*.patch')):
            run('patch', '--batch', '--forward', '-p1', '-i', patch.resolve(), cwd=dest)
        local = sorted((HERE / (name + '-patches')).glob('*.patch'))
        if {p.name: digest(p) for p in local} != LOCK.get(name + '_patches', {}):
            raise RuntimeError('Fingerprint packaging patches differ from the source lock')
        for patch in local:
            run('patch', '--batch', '--forward', '-p1', '-i', patch.resolve(), cwd=dest)
    return upstream


def meson(source, build, options, env=None):
    run('meson', 'setup', build, source, '--prefix=' + str(PREFIX), '--libdir=lib',
        '--buildtype=release', *options, env=env)
    run('meson', 'compile', '-C', build, '-j2', env=env)


def build(work, kernel, tests=True):
    if os.geteuid() == 0:
        raise RuntimeError('Build as an unprivileged user; only deployment needs root')
    work = work.resolve()
    fetch(work)
    return compile_sources(work, kernel, tests)


def compile_sources(work, kernel, tests=True):
    """Called only after locked source retrieval and patch application."""
    upstream = work / 't1bridge'
    # Same runtime features/binaries as the upstream recipe, in one invocation
    # to avoid repeatedly rebuilding shared crates with different feature sets.
    cmd = ['cargo', 'build', '--locked', '--release', '-j2']
    for package in sorted({p for p, _, _ in RUST_TARGETS}):
        cmd += ['-p', package]
    for _, binary, _ in RUST_TARGETS:
        cmd += ['--bin', binary]
    cmd += ['--features', ','.join(p + '/' + f for p, _, f in RUST_TARGETS if f)]
    run(*cmd, cwd=upstream)
    if tests:
        # The unpublished Arch repository release tool needs vercmp/repo-add;
        # it is neither installed nor linked into runtime services.
        run('cargo', 'test', '-j2', '--locked', '--workspace', '--exclude', 't1-release',
            '--all-targets', '--all-features', cwd=upstream)
        # The legacy direct PAM adapter is not shipped (we use pam_fprintd).
        # Its Arch-specific test assumes /usr/bin/true is a regular file;
        # Ubuntu's coreutils multicall symlink correctly fails its trust check.
        run('make', 'SHELL=/bin/bash', 'platform-c', 'touchbar-hw-c', 'sep-probe',
            'uvc-parser', 'uvc-upstream', 'appletbdrm-resume', 'packaging', cwd=upstream)
    if kernel:
        run('make', '-C', upstream / 'kernel/dkms', 'KDIR=/lib/modules/' + kernel + '/build')
    stage = work / 'stage'
    stage.mkdir()
    private = stage / PREFIX.relative_to('/')
    common = ['-Ddoc=false', '-Dinstalled-tests=false', '-Dudev_rules=disabled', '-Dudev_hwdb=disabled']
    libsource = work / ('libfprint-' + LOCK['libfprint']['commit'])
    # Production contains no virtual/testing driver. Separate test build below.
    libbuild = work / 'libfprint-build'
    meson(libsource, libbuild, ['-Ddrivers=t1bridge', *common])
    run('meson', 'install', '-C', libbuild, '--destdir', stage)
    env = os.environ.copy()
    env['PKG_CONFIG_PATH'] = str(private / 'lib/pkgconfig')
    env['PKG_CONFIG_SYSROOT_DIR'] = str(stage)
    # Only the private libfprint .pc should be relocated, not system dependencies.
    pc = private / 'lib/pkgconfig/libfprint-2.pc'
    pc.write_text(pc.read_text().replace('prefix=' + str(PREFIX), 'prefix=' + str(private)))
    env.pop('PKG_CONFIG_SYSROOT_DIR')
    # RUNPATH binds the daemon to its sibling library after relocation to /opt.
    env['LDFLAGS'] = '-Wl,-rpath,' + str(PREFIX / 'lib')
    env['GI_TYPELIB_PATH'] = str(private / 'lib/girepository-1.0')
    env['LD_LIBRARY_PATH'] = str(private / 'lib')
    fpbuild = work / 'fprintd-build'
    meson(work / ('fprintd-' + LOCK['fprintd']['commit']), fpbuild,
          ['--localstatedir=/var', '-Dgtk_doc=false', '-Dman=false', '-Dpam=true',
           '-Dpam_modules_dir=' + str(PREFIX / 'lib/security'),
           '-Dsystemd_system_unit_dir=' + str(PREFIX / 'share/systemd'),
           '-Ddbus_service_dir=' + str(PREFIX / 'share/dbus-1/system-services')], env)
    run('meson', 'install', '-C', fpbuild, '--destdir', stage, env=env)
    pc.write_text(pc.read_text().replace('prefix=' + str(private), 'prefix=' + str(PREFIX)))
    if tests:
        testbuild = work / 'libfprint-test'
        meson(libsource, testbuild, ['-Ddrivers=t1bridge,virtual_image,virtual_device,virtual_device_storage', *common])
        run('meson', 'test', '-C', testbuild, '--print-errorlogs')
        testenv = env.copy()
        testenv['LD_LIBRARY_PATH'] = str(testbuild / 'libfprint')
        testenv['GI_TYPELIB_PATH'] = str(testbuild / 'libfprint')
        run('meson', 'test', '-C', fpbuild, '--print-errorlogs', env=testenv)
    bundle(upstream, private, kernel)
    files = {}
    for path in sorted(private.rglob('*')):
        if path.is_symlink():
            target = path.resolve()
            if not target.is_relative_to(private):
                raise RuntimeError('External bundle symlink: ' + str(path))
            files[str(path.relative_to(private))] = {'symlink': os.readlink(path)}
        elif path.is_file():
            files[str(path.relative_to(private))] = {'sha256': digest(path), 'mode': path.stat().st_mode & 0o777}
    manifest = {'schema': 1, 'lock': LOCK, 'kernel': kernel, 'tests_requested': tests, 'files': files}
    (private / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    # Bundle must be wholly private; Meson defaults must not escape to /usr or /etc.
    for path in stage.rglob('*'):
        if path.is_file() and not path.is_relative_to(private):
            raise RuntimeError('Meson installed outside private prefix: ' + str(path))
    print('Prepared inert bundle:', private)
    return private


def bundle(upstream, private, kernel):
    for _, binary, _ in RUST_TARGETS:
        target = private / ('bin' if binary in ('t1bridge', 't1-touchid') else 'libexec') / binary
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(upstream / 'target/release' / binary, target)
    shutil.copytree(upstream / 'systemd', private / 'integration/systemd')
    kernel_dest = private / 'integration/kernel'
    # Keep source only for DKMS, including all original license identifiers.
    shutil.copytree(upstream / 'kernel', kernel_dest, ignore=shutil.ignore_patterns(
        '*.o', '*.ko', '*.mod', '*.mod.c', '*.d', '.*.cmd', 'Module.symvers', 'modules.order', '.tmp_versions'))
    dkms = (kernel_dest / 'dkms/dkms.conf').read_text()
    dkms = dkms.replace('PACKAGE_VERSION="0.1.11"', 'PACKAGE_VERSION="' + LOCK['t1bridge']['version'] + '"')
    # A build on one ABI does not authorize automatic builds for arbitrary kernels.
    import re
    if kernel is not None and not re.fullmatch(r'[A-Za-z0-9._+-]+', kernel):
        raise RuntimeError('Invalid kernel release')
    # Single quotes preserve the ERE through DKMS shell parsing.
    dkms += "\nBUILD_EXCLUSIVE_KERNEL='^" + re.escape(kernel or '') + "$'\n"
    (kernel_dest / 'dkms.conf').write_text(dkms)
    licenses = private / 'share/licenses/t1bridge'
    licenses.mkdir(parents=True, exist_ok=True)
    for source, name in ((upstream / 'LICENSE', 'MIT.txt'),
                         (upstream / 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md'),
                         (upstream / 'kernel/LICENSE.md', 'KERNEL-LICENSES.md'),
                         (upstream / 'LICENSES/GPL-2.0-only.txt', 'GPL-2.0.txt')):
        shutil.copy2(source, licenses / name)
    for name in ('libfprint', 'fprintd'):
        source = upstream.parent / (name + '-' + LOCK[name]['commit'])
        shutil.copy2(source / 'COPYING', licenses / (name + '-COPYING'))
    shutil.copy2(HERE / 'sources.lock.json', licenses / 'sources.lock.json')
