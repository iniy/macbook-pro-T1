#!/usr/bin/env python3
"""Report competing boot configuration without changing it or dumping its contents."""
from pathlib import Path
import re
import subprocess
import sys

pattern = re.compile(r'apple[-_](?:ibridge|touchbar|ib[-_](?:tb|als))|t1bar|tiny-dfr|touchbar-attach')
own = {'macbook-t1-touchbar.conf', '90-macbook-t1-touchbar.rules', 'macbook-t1-touchbar.service'}
problems = []
for path in [Path('/etc/dkms/framework.conf'), *Path('/etc/dkms/framework.conf.d').glob('*.conf')]:
    if not path.is_file() or path.name == 'zz-macbook-t1-touchbar.conf':
        continue
    audio_signing = Path(__file__).resolve().parents[1] / 'audio/config/dkms-signing.conf'
    if path.name == 'zz-macbook-t1-audio.conf' and audio_signing.is_file() and path.read_bytes() == audio_signing.read_bytes():
        continue
    text = '\n'.join(line for line in path.read_text(errors='replace').splitlines()
                     if not line.lstrip().startswith('#'))
    if re.search(r'\b(mok_signing_key|mok_certificate|sign_file)\s*=', text):
        problems.append(str(path) + ' (existing DKMS signing policy needs review)')
for directory, glob in [('/etc/modprobe.d', '*.conf'), ('/usr/lib/modprobe.d', '*.conf'),
                         ('/etc/modules-load.d', '*.conf'), ('/usr/lib/modules-load.d', '*.conf'),
                         ('/etc/udev/rules.d', '*.rules'), ('/etc/initramfs-tools', 'modules'),
                         ('/etc/initramfs-tools/scripts', '**/*'), ('/etc/systemd/system-sleep', '*'),
                         ('/usr/lib/systemd/system-sleep', '*')]:
    for path in Path(directory).glob(glob):
        if path.name in own or not path.is_file():
            continue
        text = '\n'.join(line for line in path.read_text(errors='replace').splitlines()
                         if not line.lstrip().startswith('#'))
        if pattern.search(text):
            problems.append(str(path))
for name in ['apple-touchbar', 'apple-touchbar-resume', 'touchbar', 'tiny-dfr',
             't1bar', 't1bar-scenes', 't1-touchbar']:
    for check in ['is-active', 'is-enabled']:
        p = subprocess.run(['systemctl', check, '--quiet', name + '.service'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if p.returncode == 0:
            problems.append(name + '.service (' + check + ')')
            break
cmdline = Path('/proc/cmdline').read_text()
if re.search(r'apple[-_]ibridge[.]skip_acpi_power=(?!1(?:\s|$))\S+', cmdline):
    problems.append('kernel command line overrides skip_acpi_power')
if problems:
    print('Resolve existing Touch Bar configuration with its original uninstaller first:', file=sys.stderr)
    for problem in sorted(set(problems)):
        print('  ' + problem, file=sys.stderr)
    raise SystemExit(1)
