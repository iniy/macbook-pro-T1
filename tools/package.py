#!/usr/bin/env python3
"""Deterministic source package, explicit allowlist, no VM keys or personal setup logs."""
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.0'
FILES = ['install.sh', 'install-ubuntu.sh', 'verify-ubuntu.sh', 'uninstall-ubuntu.sh', 'CREDITS.md',
          'README.md', 'LICENSE']
FILES += ['WIFI-5GHZ-IMPLEMENTATION.md', 'WIFI-5GHZ-BENCHMARKS.md', 'WIFI-5GHZ-RECOVERY.md']
FILES += ['THIRD_PARTY_NOTICES.md', 'TOUCHID-UPSTREAM-ATTRIBUTION.md',
          'TOUCHID-PORTABILITY.md', 'TOUCHID-IMPLEMENTATION.md', 'TOUCHID-CHANGELOG.md',
          'TOUCHID-TEST-RESULTS.md', 'TOUCHID-RECOVERY.md']
FILES += ['install-audio.sh', 'verify-audio.sh', 'uninstall-audio.sh',
          'install-camera.sh', 'verify-camera.sh', 'uninstall-camera.sh',
          'install-wifi.sh', 'verify-wifi.sh', 'uninstall-wifi.sh']
DIRS = ['driver', 'patches', 'lib', 'config', 'tests', 'audio', 'camera', 'wifi', 'desktop', 'sleep', 'touchid', 'touchbar']
TOOLS = ['tools/package.py', 'tools/capture-macos.py', 'tools/validate-linux.sh',
         'tools/test-macos.py', 'tools/prepare-vm.py', 'tools/run-vm.sh',
         'tools/vm-ssh.sh', 'tools/qemu-launch.c', 'tools/hypervisor.entitlements']
REPORTS = ['reports/macos-hardware.json', 'reports/linux-build-7.3.0-9-generic.log',
           'reports/wifi-final.json',
           'reports/linux-static-analysis.log', 'reports/linux-integration.log',
           'reports/macos-tests.log', 'reports/linux-final-checks.log',
           'reports/package-validation.log',
           'reports/research/ubuntu-26.10-desktop.manifest']


def main():
    names = list(FILES) + TOOLS + REPORTS
    for directory in DIRS:
        names.extend(str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and 'build' not in p.parts)
    for name in names:
        if not (ROOT / name).is_file() or (ROOT / name).is_symlink():
            raise SystemExit('Missing/unsafe package file: ' + name)
    names = sorted(set(names))
    payload = {name: (ROOT / name).read_bytes() for name in names}
    sums = ''.join(f'{hashlib.sha256(payload[n]).hexdigest()}  {n}\n' for n in names)
    (ROOT / 'SHA256SUMS').write_text(sums)
    payload['SHA256SUMS'] = sums.encode()
    dest = ROOT / 'dist' / f'macbook-t1-ubuntu-{VERSION}.tar.gz'
    dest.parent.mkdir(exist_ok=True)
    with dest.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tar:
            for name, data in sorted(payload.items()):
                entry = tarfile.TarInfo('macbook-t1-ubuntu/' + name)
                entry.size = len(data)
                entry.mode = 0o755 if name.endswith(('.sh', '.py')) else 0o644
                entry.uid = entry.gid = entry.mtime = 0
                entry.uname = entry.gname = ''
                tar.addfile(entry, io.BytesIO(data))
    checksum = hashlib.sha256(dest.read_bytes()).hexdigest()
    dest.with_suffix(dest.suffix + '.sha256').write_text(f'{checksum}  {dest.name}\n')
    print(f'{dest.name}: {dest.stat().st_size} bytes; SHA256 {checksum}')


if __name__ == '__main__':
    main()
