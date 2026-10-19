#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One-variable live power-save trial with independent timed rollback. Always reverts."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import benchmark
import check


def run(*args):
    subprocess.run(args, check=True, timeout=30, stdout=subprocess.DEVNULL)


def compare(before, after):
    a, b = before['summary'], after['summary']
    rssi = b['rssi_dbm']['median'] - a['rssi_dbm']['median'] if a['rssi_dbm'] and b['rssi_dbm'] else None
    return {'rssi_median_change_db': rssi,
            'same_single_ap_and_channel_required': True,
            'possible_roaming_confound': (a['distinct_access_points'] != 1 or b['distinct_access_points'] != 1 or
                                         not before.get('boot_scoped_ap_tokens') or
                                         before.get('boot_scoped_ap_tokens') != after.get('boot_scoped_ap_tokens') or
                                         a['frequencies_mhz'] != b['frequencies_mhz']),
            'possible_address_confound': (a.get('ipv4_source_changed_or_missing', True) or
                                         b.get('ipv4_source_changed_or_missing', True)),
            'decision': 'reverted; compare repeat runs before opting into a persistent per-profile change',
            'rf_repair_proven': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--powersave', choices=['on', 'off'], required=True)
    parser.add_argument('--seconds', type=int, default=125)
    parser.add_argument('--iperf-server', help='Explicit LAN endpoint; throughput is unavailable if omitted')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run with sudo; required to arm the independent systemd rollback timer')
    if not 125 <= args.seconds <= 1800:
        parser.error('Use 125–1800 seconds per measurement')
    if Path('/sys/class/dmi/id/product_name').read_text().strip() != 'MacBookPro13,2':
        parser.error('Unsupported model')
    iface = check.interface(check.hardware())
    os.umask(0o077)
    with Path('/run/macbook-t1-wifi.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        parent = Path('/var/lib/macbook-t1-wifi-experiments')
        if parent.is_symlink():
            raise RuntimeError('Refusing symlink state')
        parent.mkdir(mode=0o700, exist_ok=True)
        if parent.stat().st_uid != 0 or parent.stat().st_mode & 0o077:
            raise RuntimeError('State directory must be root-owned, mode 0700')
        state = Path(tempfile.mkdtemp(prefix='power-', dir=parent))
        before = benchmark.measure(args.seconds, server=args.iperf_server, repeats=2)
        (state / 'before.json').write_text(json.dumps(before, indent=2))
        old = before['after']['power_save']
        if old not in ('on', 'off') or old == args.powersave:
            raise RuntimeError('Unknown power state, or requested value is already active')
        unit = 'macbook-t1-wifi-trial-' + str(time.time_ns())
        record = {'interface': iface, 'original_power_save': old, 'trial_power_save': args.powersave,
                  'rollback_unit': unit, 'profile_modified': False}
        (state / 'state.json').write_text(json.dumps(record, indent=2))
        # The recovery command has no dependency on this terminal, repository or
        # Python process. Reboot also restores the untouched NM profile policy.
        run('systemd-run', '--unit=' + unit, '--on-active=' + str(args.seconds + 180) + 's',
            '/usr/sbin/iw', 'dev', iface, 'set', 'power_save', old)
        try:
            run('iw', 'dev', iface, 'set', 'power_save', args.powersave)
            if check.snapshot()['power_save'] != args.powersave:
                raise RuntimeError('Requested runtime state did not load')
            after = benchmark.measure(args.seconds, server=args.iperf_server, repeats=2)
            (state / 'after.json').write_text(json.dumps(after, indent=2))
            (state / 'comparison.json').write_text(json.dumps(compare(before, after), indent=2))
        finally:
            # If immediate restore fails, leave the independent timer armed.
            run('iw', 'dev', iface, 'set', 'power_save', old)
            if check.snapshot()['power_save'] != old:
                raise RuntimeError('Immediate restore not verified; timed recovery remains armed')
            run('systemctl', 'stop', unit + '.timer')
            (state / 'restored').touch()
        print('Trial reverted. Private measurements: ' + str(state))


if __name__ == '__main__':
    main()
