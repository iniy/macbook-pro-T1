#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Guard normal systemd suspend and restore the built-in Thunderbolt branches."""
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import uuid

COMMON = Path(__file__).with_name('pm.py')
if not COMMON.exists():
    COMMON = Path(__file__).with_name('test-stages.py')
SPEC = importlib.util.spec_from_file_location('pm_helpers', COMMON)
PM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PM)
SPEC = importlib.util.spec_from_file_location('sleep_audio', Path(__file__).with_name('audio.py'))
AUDIO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIO)
KMSG = Path('/dev/kmsg')


def preflight():
    if os.geteuid() != 0:
        raise RuntimeError('Administrator privileges required.')
    if Path('/sys/class/dmi/id/product_name').read_text().strip() != 'MacBookPro13,2':
        raise RuntimeError('Unsupported model; refusing suspend.')
    PM.require_port_pm_off()
    if PM.selected((PM.POWER / 'pm_test').read_text()) != 'none':
        raise RuntimeError('A PM checkpoint test is active; refusing normal suspend.')
    if 's2idle' not in (PM.POWER / 'mem_sleep').read_text():
        raise RuntimeError('s2idle is not supported.')
    nvme = PM.PCI / '0000:01:00.0'
    expected = {'vendor': '0x106b', 'device': '0x2003', 'd3cold_allowed': '0'}
    if any((nvme / attr).read_text().strip() != value for attr, value in expected.items()):
        raise RuntimeError('Apple NVMe workaround is not active; refusing suspend.')
    if (nvme / 'driver').resolve().name != 'nvme':
        raise RuntimeError('Unexpected NVMe driver; refusing suspend.')
    PM.thunderbolt_attributes()
    PM.reject_thunderbolt_storage()


def suspend(record):
    preflight()
    marker = 'macbook-t1-normal-suspend ' + str(uuid.uuid4())
    KMSG.write_text(marker + '\n')
    before = PM.statistics()
    # This context refuses attached storage before the upstream sleep program
    # runs. Unlike a system-sleep hook, failure here cancels suspend itself.
    with PM.temporary_thunderbolt_removal(record):
        (PM.POWER / 'mem_sleep').write_text('s2idle\n')
        if PM.selected((PM.POWER / 'mem_sleep').read_text()) != 's2idle':
            raise RuntimeError('Could not select s2idle; refusing suspend.')
        try:
            subprocess.run(['/usr/lib/systemd/systemd-sleep', 'suspend'], check=True)
        finally:
            # The vendor sleep program has thawed user.slice at this point.
            AUDIO.reopen_playback(record)
    log = PM.kernel_log().partition(marker)[2]
    after = PM.statistics()
    if ('PM: suspend entry (s2idle)' not in log or 'PM: suspend exit' not in log
            or PM.kernel_faults(log)
            or int(after['success']) != int(before['success']) + 1
            or any(value != after.get(key) for key, value in before.items()
                   if key == 'fail' or key.startswith('failed_'))):
        raise RuntimeError('Suspend or controller recovery failed; inspect the kernel journal.')
    record('s2idle returned and all built-in Thunderbolt controller drivers were restored.')


def main():
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, PM.interrupted)
    try:
        suspend(lambda message: print('macbook-t1-sleep:', message, flush=True))
    except Exception as error:
        print('macbook-t1-sleep: FAILED:', error, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
