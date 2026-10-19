#!/usr/bin/env python3
"""Run feasible native tests; never invokes Ubuntu installation actions."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if sys.platform != 'darwin':
    raise SystemExit('Use this runner on Monterey.')
scripts = list(ROOT.glob('*.sh'))
for directory in ['lib', 'tools', 'tests']:
    scripts.extend((ROOT / directory).glob('*.sh'))
scripts.extend([ROOT / 'driver/dkms.conf', ROOT / 'config/dkms-signing.conf'])
for path in scripts:
    subprocess.run(['/bin/bash', '-n', str(path)], check=True)
print(f'PASS bash syntax: {len(scripts)} scripts/configs', flush=True)
for script in ['install-ubuntu.sh', 'verify-ubuntu.sh', 'uninstall-ubuntu.sh']:
    p = subprocess.run(['/bin/bash', str(ROOT / script)], capture_output=True, text=True)
    assert p.returncode != 0 and 'on Ubuntu, not macOS' in p.stderr, (script, p.stderr)
print('PASS all Ubuntu entrypoints reject macOS before changes', flush=True)
for path in [*ROOT.glob('lib/*.py'), *ROOT.glob('tools/*.py'), *ROOT.glob('tests/*.py')]:
    compile(path.read_text(), str(path.relative_to(ROOT)), 'exec')
print('PASS Python syntax', flush=True)
for name in ['test_transactions.py', 'test_hid_slots.py', 'test_acpi_guard.py', 'test_source_package.py']:
    subprocess.run([sys.executable, str(ROOT / 'tests' / name)], check=True)
p = subprocess.run(['/bin/bash', '-c', '''source lib/common.sh
supported_kernel 7.3.0-9-generic || exit 1
supported_kernel 7.3.0-99-generic || exit 1
for k in 6.8.0-1-generic 7.4.0-1-generic 7.3.0-9-lowlatency 7.3.0-9-generic-unsigned Darwin; do
    if supported_kernel "$k"; then exit 1; fi
done
module=unrelated; mok_signing_key=other; mok_certificate=other
source config/dkms-signing.conf
[[ $mok_signing_key == other && $mok_certificate == other ]] || exit 1
module=macbook-t1-touchbar
source config/dkms-signing.conf
[[ $mok_signing_key == /var/lib/macbook-t1-signing/MOK.priv ]] || exit 1
module=unrelated
source config/dkms-signing.conf
[[ -z $mok_signing_key && -z $mok_certificate ]] || exit 1
'''], cwd=ROOT)
assert p.returncode == 0
print('PASS kernel family/flavor boundary checks', flush=True)
print('PASS DKMS signing selection is scoped and cleared for the next module', flush=True)
