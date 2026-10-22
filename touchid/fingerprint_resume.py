#!/usr/bin/python3
# SPDX-License-Identifier: MIT
"""Restore the T1 keybag relay before systemd-sleep thaws fingerprint clients."""
import os
from pathlib import Path
import signal
import subprocess
import sys

HOOK = 'usr/lib/systemd/system-sleep/80-macbook-t1-fingerprint-resume'
DAEMON = 'fprintd.service'
BROKER = 't1-touchid-auth.service'
RELAY = 't1bridge-keybag.service'
KEYBAG = Path('/var/lib/t1bridge/touch-id/keybag.state')


def enabled(root=Path('/')):
    return ('t1bridge.trial=1' in (root / 'proc/cmdline').read_text().split()
            and (root / 'sys/class/dmi/id/product_name').read_text().strip() == 'MacBookPro13,2'
            and '[s2idle]' in (root / 'sys/power/mem_sleep').read_text().split())


def state(unit):
    return subprocess.check_output(
        ['systemctl', 'show', '--value', '--property=ActiveState', unit],
        text=True, timeout=3).strip()


def control(action, unit, timeout=6):
    subprocess.run(['systemctl', action, unit], check=True, timeout=timeout)


def recover(record=print):
    if not enabled():
        return
    if os.geteuid() != 0:
        raise PermissionError('Fingerprint resume recovery requires administrator authentication')
    # Check existence only. Never read, replace, delete or recreate keybags.
    if not KEYBAG.is_file():
        record('No existing keybag; fingerprint resume recovery skipped.')
        return
    daemon_state = state(DAEMON)
    if daemon_state not in ('active', 'activating', 'inactive', 'failed'):
        raise RuntimeError('Fingerprint daemon is already changing state; preserving it')
    restart_daemon = daemon_state in ('active', 'activating')
    try:
        # User sessions are still frozen in a system-sleep post hook. Stop the
        # client first so its existing operation releases the broker cleanly.
        control('stop', DAEMON)
        control('stop', BROKER)
        # Restart also handles a relay that has not yet noticed device loss.
        # Type=notify makes this wait for actual startup readiness, not a PID.
        control('restart', RELAY, timeout=12)
        if state(RELAY) != 'active':
            raise RuntimeError('Keybag relay did not reach readiness')
        record('Keybag relay is ready before fingerprint clients resume.')
    finally:
        # Restore the prior on-demand daemon state, including on failure. The
        # broker sockets remain enabled; ordinary requests start a fresh broker.
        if restart_daemon:
            control('start', DAEMON)


def install(tx):
    tx.put(HOOK, Path(__file__).read_bytes(), 0o755)


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if args != ['recover']:
        action = os.environ.get('SYSTEMD_SLEEP_ACTION', args[1] if len(args) == 2 else '')
        if args != ['post', 'suspend'] or action != 'suspend':
            return 0
    def timed_out(*_):
        raise TimeoutError('Fingerprint resume recovery exceeded 35 seconds')
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(35)
    try:
        recover(lambda message: print('macbook-t1-fingerprint-resume:', message, flush=True))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('macbook-t1-fingerprint-resume: FAILED:', error, file=sys.stderr, flush=True)
        return 1
    finally:
        signal.alarm(0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
