#!/usr/bin/env python3
"""Read-only unified verification after login; no playback or camera capture."""
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'macbook-t1'
state.mkdir(parents=True, exist_ok=True, mode=0o700)
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
with (state / f'verify-{boot}.log').open('w') as log:
    for attempt in range(45):
        status = subprocess.run(['systemctl', 'show', '-p', 'ActiveState', '--value', 'macbook-t1-touchbar.service'],
                                capture_output=True, text=True).stdout.strip()
        if status in ('active', 'failed'):
            break
        time.sleep(1)
    p = subprocess.run(['bash', str(ROOT / 'verify-ubuntu.sh'), '--all'], stdout=log, stderr=subprocess.STDOUT)
    log.write(f'\nVERIFY_EXIT={p.returncode}\nPhysical listening, voice, preview and sleep tests remain separate.\n')
print('Unified verification saved under the current user state directory: macbook-t1/verify-<boot-id>.log')
raise SystemExit(p.returncode)
