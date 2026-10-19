#!/usr/bin/env python3
"""Exercise installer decisions with mock tools and isolated EFI/kernel state."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'install-ubuntu.sh').read_text()
policy = source.split('SIGN_REQUIRED=0\n', 1)[1].split('\nexec 9>', 1)[0]
dependencies = source.split('if [[ $deps == 1 ]]; then\n', 1)[1].split('\nfi\n', 1)[0]

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    efi = root / 'sys/firmware/efi/efivars'
    efi.mkdir(parents=True)
    enforce = root / 'sys/module/module/parameters/sig_enforce'
    enforce.parent.mkdir(parents=True)
    lockdown = root / 'sys/kernel/security/lockdown'
    lockdown.parent.mkdir(parents=True)
    variable = efi / 'SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c'
    script = '''set -euo pipefail
die() { echo "$*" >&2; exit 1; }
mokutil() { printf '%s\\n' "$MOCK_SB"; return "$MOCK_RC"; }
findmnt() { printf '%s\\n' "$MOCK_FS"; }
SIGN_REQUIRED=0
''' + policy.replace('/sys/', str(root / 'sys') + '/') + '\necho "REQUIRED=$SIGN_REQUIRED"\n'
    cases = [
        ('enabled', 'SecureBoot enabled', 0, 'efivarfs', True, 'N', '[none] integrity confidentiality', 1),
        ('disabled', 'SecureBoot disabled', 0, 'efivarfs', True, 'N', '[none] integrity confidentiality', 0),
        ('old Apple message', 'Failed to read "SecureBoot" variable: No such file or directory', 1, 'efivarfs', False, 'N', '[none] integrity confidentiality', 0),
        ('new Apple message', "This system doesn't support Secure Boot", 255, 'efivarfs', False, 'N', '[none] integrity confidentiality', 0),
        ('unmounted variables', "This system doesn't support Secure Boot", 255, 'sysfs', False, 'N', '[none] integrity confidentiality', None),
        ('contradictory variable', "This system doesn't support Secure Boot", 255, 'efivarfs', True, 'N', '[none] integrity confidentiality', None),
        ('unknown error', 'Permission denied', 1, 'efivarfs', False, 'N', '[none] integrity confidentiality', None),
        ('failed enabled query', 'SecureBoot enabled', 1, 'efivarfs', True, 'N', '[none] integrity confidentiality', None),
        ('forced signatures', "This system doesn't support Secure Boot", 255, 'efivarfs', False, 'Y', '[none] integrity confidentiality', 1),
        ('lockdown', "This system doesn't support Secure Boot", 255, 'efivarfs', False, 'N', 'none [integrity] confidentiality', 1),
    ]
    for name, sb, rc, fs, exists, sig, lock, expected in cases:
        variable.unlink(missing_ok=True)
        if exists:
            variable.write_bytes(b'present')
        enforce.write_text(sig + '\n')
        lockdown.write_text(lock + '\n')
        result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                                env=dict(os.environ, MOCK_SB=sb, MOCK_RC=str(rc), MOCK_FS=fs))
        if expected is None:
            assert result.returncode != 0, name
        else:
            assert result.returncode == 0 and f'REQUIRED={expected}' in result.stdout, (name, result)
        print('PASS', name)

for installed, expected in [('installed', 'dracut'), ('not-installed', 'initramfs-tools')]:
    script = '''set -euo pipefail
KERNEL=7.3.0-9-generic
dpkg-query() { printf '%s' "$MOCK_STATUS"; }
apt-get() { printf '%s\\n' "$*"; }
''' + dependencies
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                            env=dict(os.environ, MOCK_STATUS=installed))
    assert result.returncode == 0, result
    assert f'{expected} zstd' in result.stdout and 'install --no-remove -y' in result.stdout, result
    print('PASS dependency provider', expected)
