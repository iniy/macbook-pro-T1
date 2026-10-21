#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One explicitly requested real s2idle trial; plan-only unless --run is given.

This isolates the kernel path using /sys/power/state. It does not exercise
logind's desktop notifications or install a systemd sleep hook.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import signal
import tempfile
import time
import uuid

SPEC = importlib.util.spec_from_file_location('pm_tests', Path(__file__).with_name('test-stages.py'))
PM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PM)
RTC = Path('/sys/class/rtc/rtc0/wakealarm')
RTC_WAKEUP = Path('/sys/class/rtc/rtc0/device/power/wakeup')


def check_alarm():
    if RTC.read_text().strip() not in ('', '0'):
        raise RuntimeError('An RTC alarm is already armed; refusing to replace it.')
    if RTC_WAKEUP.read_text().strip() != 'enabled':
        raise RuntimeError('RTC wakeup is not enabled; refusing an unattended wake trial.')


@contextmanager
def wake_alarm():
    check_alarm()
    try:
        RTC.write_text('+20\n')
        if int(RTC.read_text().strip()) <= 0:
            raise RuntimeError('RTC wake alarm did not arm.')
        yield
    finally:
        RTC.write_text('0\n')


def completed(log, before, after, slept):
    return ('PM: suspend entry (s2idle)' in log and 'PM: suspend exit' in log
            and not PM.kernel_faults(log) and slept >= 10
            and int(after['success']) == int(before['success']) + 1
            and all(value == after.get(key) for key, value in before.items()
                    if key == 'fail' or key.startswith('failed_')))


def run():
    if os.geteuid() != 0:
        raise RuntimeError('Administrator authentication is required.')
    PM.preflight(())
    PM.require_port_pm_off()
    PM.thunderbolt_attributes()
    PM.reject_thunderbolt_storage()
    check_alarm()
    if 's2idle' not in (PM.POWER / 'mem_sleep').read_text():
        raise RuntimeError('s2idle is unavailable.')
    directory = Path(tempfile.mkdtemp(prefix='macbook-t1-s2idle-', dir='/var/tmp'))
    print('Diagnostic directory:', directory, flush=True)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, PM.interrupted)
    with (directory / 'progress.log').open('w', buffering=1) as progress:
        def record(message):
            line = f'{datetime.now(timezone.utc).isoformat()} {message}'
            print(line, flush=True)
            progress.write(line + '\n')
            os.fsync(progress.fileno())

        (directory / 'kernel-before.log').write_text(PM.kernel_log())
        marker = f'macbook-t1-real-s2idle {uuid.uuid4()}'
        Path('/dev/kmsg').write_text(marker + '\n')
        try:
            with PM.temporary_thunderbolt_removal(record), PM.temporary_settings({
                    'mem_sleep': 's2idle', 'pm_debug_messages': '1', 'pm_print_times': '1'}):
                if PM.selected((PM.POWER / 'mem_sleep').read_text()) != 's2idle':
                    raise RuntimeError('s2idle selection did not stick; aborting.')
                if PM.selected((PM.POWER / 'pm_test').read_text()) != 'none':
                    raise RuntimeError('A kernel checkpoint test is active; aborting.')
                before = PM.statistics()
                os.sync()
                with wake_alarm():
                    record('START real s2idle; RTC wake armed for about 20 seconds; lid stays open.')
                    boot_start = time.clock_gettime(time.CLOCK_BOOTTIME)
                    monotonic_start = time.monotonic()
                    (PM.POWER / 'state').write_text('mem\n')
                    slept = ((time.clock_gettime(time.CLOCK_BOOTTIME) - boot_start)
                             - (time.monotonic() - monotonic_start))
                after = PM.statistics()
                record(f'RETURN: time suspended={slept:.2f}s; before={before}; after={after}')
            # Include rediscovery errors after the kernel returns, too.
            log = PM.kernel_log().partition(marker)[2]
            (directory / 'trial.log').write_text(log)
            if not completed(log, before, after, slept):
                raise RuntimeError('Failed or early wake; inspect trial.log. No repeat was started.')
            record('Kernel s2idle and controller rediscovery completed; physical checks still required.')
        except BaseException as error:
            record(f'FAILED: {error}')
            raise
        finally:
            (directory / 'kernel-after.log').write_text(PM.kernel_log())
            record('Restored sleep selection: ' + (PM.POWER / 'mem_sleep').read_text().strip())
            record('Current pm_test: ' + (PM.POWER / 'pm_test').read_text().strip())
        record('Desktop-menu, lid-close and idle-timeout suspend remain untested by this diagnostic.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Perform ONE real sleep cycle after saving work.')
    args = parser.parse_args()
    if not args.run:
        print('PLAN ONLY: one real s2idle cycle, with an RTC wake about 20 seconds after arming.')
        print('Requires pcie_port_pm=off, healthy controllers, no attached storage, and an unused RTC alarm.')
        print('Temporarily detach Thunderbolt; rediscover it and restore deep mode/debug flags afterward.')
        print('Keep the lid open. If automatic wake fails, try the power button and allow up to a minute.')
        print('This uses the kernel sleep path; it does not install a persistent sleep hook.')
        print('Run only after explicit approval for real sleep: sudo systemd-inhibit '
              '--what=sleep:shutdown --mode=block --why="Controlled s2idle trial" '
              'python3 sleep/test-s2idle.py --run')
        return 0
    try:
        run()
    except Exception as error:
        print('ERROR:', error, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
