#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Explicit, temporary kernel PM tests; never enters platform sleep."""
import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
import uuid

POWER = Path('/sys/power')
STAGES = ('freezer', 'devices')
LATER_STAGES = ('platform', 'processors', 'core')
PCI = Path('/sys/bus/pci/devices')
TB_ROOTS = {'0000:00:1c.4': '0x9d14', '0000:00:1d.0': '0x9d18'}
TB_ENDPOINTS = {'0000:05:00.0': 'thunderbolt', '0000:06:00.0': 'xhci_hcd',
                '0000:7b:00.0': 'thunderbolt', '0000:7c:00.0': 'xhci_hcd'}
TB_BRIDGES = ('0000:03:00.0', '0000:79:00.0')
PCI_BUSES = Path('/sys/class/pci_bus')
BLOCK = Path('/sys/class/block')
CMDLINE = Path('/proc/cmdline')


def require_port_pm_off():
    options = [word for word in CMDLINE.read_text().split()
               if word.startswith('pcie_port_pm=')]
    if options != ['pcie_port_pm=off']:
        raise RuntimeError('Thunderbolt removal requires a boot with pcie_port_pm=off; '
                           'rediscovery failed with port power management enabled.')


def reject_thunderbolt_storage():
    roots = [(PCI / name).resolve() for name in TB_BRIDGES]
    for block in BLOCK.iterdir():
        real = block.resolve()
        if any(root in real.parents for root in roots):
            raise RuntimeError('Storage attached under Thunderbolt; refusing removal: ' + block.name)


@contextmanager
def temporary_thunderbolt_removal(record):
    # Validate everything while healthy and before removing the first branch.
    # This runs outside systemd-sleep, so refusal prevents the test itself.
    require_port_pm_off()
    thunderbolt_attributes()
    reject_thunderbolt_storage()
    rescans = [PCI_BUSES / name / 'rescan' for name in ('0000:03', '0000:79')]
    for path in rescans:
        if not path.exists():
            raise RuntimeError('Missing branch rescan attribute: ' + str(path))
    removed = False
    try:
        for name in TB_BRIDGES:
            reject_thunderbolt_storage()
            record('DETACH built-in Thunderbolt branch ' + name)
            # Include an attempted removal in cleanup even if write() fails.
            removed = True
            (PCI / name / 'remove').write_text('1\n')
            if (PCI / name).exists():
                raise RuntimeError('Thunderbolt branch did not detach: ' + name)
        record('Both Thunderbolt branches detached; beginning selected kernel test.')
        yield
    finally:
        if removed:
            # Rescan only the two Thunderbolt buses; Wi-Fi and NVMe are on
            # different root ports and are neither removed nor rebound.
            for attempt in range(10):
                if attempt < 2:
                    for path in rescans:
                        record('RESCAN ' + str(path))
                        path.write_text('1\n')
                time.sleep(1)
                if all((PCI / name / 'driver').resolve().name == driver
                       for name, driver in TB_ENDPOINTS.items()):
                    thunderbolt_attributes()
                    record('All four NHI/xHCI endpoints returned with expected drivers.')
                    break
            else:
                raise RuntimeError('Thunderbolt re-enumeration incomplete; reboot before another test.')


def thunderbolt_attributes():
    roots = [(PCI / name).resolve() for name in TB_ROOTS]
    for name, device_id in TB_ROOTS.items():
        if (PCI / name / 'device').read_text().strip() != device_id:
            raise RuntimeError('Unexpected Thunderbolt root port: ' + name)
    for name, driver in TB_ENDPOINTS.items():
        if (PCI / name / 'driver').resolve().name != driver:
            raise RuntimeError('Missing/rebound Thunderbolt endpoint; reboot first: ' + name)
    attributes = []
    for device in sorted(PCI.iterdir()):
        real = device.resolve()
        if not any(real == root or root in real.parents for root in roots):
            continue
        # Refuse attached/unknown PCIe hardware; only the built-in topology is tested.
        if ((device / 'vendor').read_text().strip() != '0x8086'
                or (device / 'device').read_text().strip() not in
                {'0x9d14', '0x9d18', '0x1578', '0x15d3', '0x15d2', '0x15d4'}):
            raise RuntimeError('Unexpected device in Thunderbolt branch: ' + device.name)
        attributes.append(device / 'd3cold_allowed')
    if len(attributes) != 16:
        raise RuntimeError(f'Expected 16 built-in Thunderbolt PCI functions, found {len(attributes)}')
    return attributes


@contextmanager
def temporary_attributes(attributes, record):
    previous = [(path, path.read_text().strip()) for path in attributes]
    if any(value not in ('0', '1') for _, value in previous):
        raise RuntimeError('Unexpected D3cold attribute value; aborting before changes.')
    changed = []
    try:
        for path, old in previous:
            record(f'TEMPORARY {path}: {old} -> 0')
            changed.append((path, old))
            path.write_text('0\n')
            if path.read_text().strip() != '0':
                raise RuntimeError('D3cold write did not stick: ' + str(path))
        yield
    finally:
        failures = []
        for path, old in reversed(changed):
            try:
                path.write_text(old + '\n')
                record(f'RESTORED {path}: {old}')
            except OSError as error:
                failures.append(f'{path}: {error}')
        if failures:
            raise RuntimeError('D3cold restore failed; reboot to restore defaults: ' + '; '.join(failures))


def selected(value):
    match = re.search(r'\[([^]]+)\]', value)
    if not match:
        raise RuntimeError(f'No selected value in {value!r}')
    return match.group(1)


@contextmanager
def temporary_settings(settings):
    saved = []
    try:
        for name, value in settings.items():
            path = POWER / name
            old = path.read_text().strip()
            if name in ('pm_test', 'mem_sleep'):
                old = selected(old)
            saved.append((path, old))
            path.write_text(value + '\n')
        yield
    finally:
        failures = []
        for path, old in reversed(saved):
            try:
                path.write_text(old + '\n')
            except OSError as error:
                failures.append(f'{path}: {error}')
        if failures:
            raise RuntimeError('Could not restore settings: ' + '; '.join(failures))


def kernel_log():
    return subprocess.check_output(
        ['dmesg', '--raw'], text=True, errors='replace')


def statistics():
    return {p.name: p.read_text().strip()
            for p in sorted((POWER / 'suspend_stats').iterdir()) if p.is_file()}


def kernel_faults(log):
    return bool(re.search(r'WARNING:|BUG:|Oops:|Call Trace:|not ready .* after resume|'
                       r'Unable to change power state|device inaccessible|'
                       r'host controller not responding|HC died|timed out', log))


def completed(log, before, after):
    # An early wake can return success without ever reaching the selected test.
    # Drivers may also log failures but return 0, leaving PM counters unchanged.
    reached = re.search(r'suspend debug: Waiting for \d+ second', log)
    return (bool(reached) and not kernel_faults(log) and 'PM: suspend exit' in log
            and int(after['success']) == int(before['success']) + 1
            and all(value == after.get(key) for key, value in before.items()
                    if key == 'fail' or key.startswith('failed_')))


def preflight(stages):
    if Path('/sys/class/dmi/id/product_name').read_text().strip() != 'MacBookPro13,2':
        raise RuntimeError('This diagnostic is restricted to MacBookPro13,2.')
    if selected((POWER / 'mem_sleep').read_text()) != 'deep':
        raise RuntimeError('Expected the existing deep sleep selection; no settings changed.')
    if selected((POWER / 'pm_test').read_text()) != 'none':
        raise RuntimeError('Another PM test is already selected; no settings changed.')
    if (POWER / 'pm_trace').read_text().strip() != '0':
        raise RuntimeError('PM_TRACE is active; stop and review that diagnostic first.')
    supported = (POWER / 'pm_test').read_text().replace('[', '').replace(']', '').split()
    if not all(stage in supported for stage in stages):
        raise RuntimeError('The kernel does not offer all requested PM test stages.')
    subprocess.run([str(Path(__file__).with_name('manage.sh')), 'verify'], check=True)


def interrupted(signum, _frame):
    raise RuntimeError(f'Interrupted by signal {signum}')


def run_tests(stages, thunderbolt_d3cold_off=False, thunderbolt_remove=False):
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo or pkexec after saving work in every session.')
    preflight(stages)
    attributes = thunderbolt_attributes() if thunderbolt_d3cold_off else []
    if thunderbolt_remove:
        require_port_pm_off()
        thunderbolt_attributes()
        reject_thunderbolt_storage()
    # mkdtemp creates a private, unique directory, avoiding root writes through
    # caller-controlled log paths. It remains available after a forced reboot.
    directory = Path(tempfile.mkdtemp(prefix='macbook-t1-pm-test-', dir='/var/tmp'))
    print(f'Diagnostic directory: {directory}', flush=True)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupted)
    with (directory / 'progress.log').open('w', buffering=1) as progress:
        def record(message):
            line = f'{datetime.now(timezone.utc).isoformat()} {message}'
            print(line, flush=True)
            progress.write(line + '\n')
            progress.flush()
            os.fsync(progress.fileno())

        record(f'kernel={os.uname().release}; tests={stages}; keep the lid open')
        (directory / 'kernel-before.log').write_text(kernel_log())
        try:
            trial = (temporary_thunderbolt_removal(record) if thunderbolt_remove else
                     temporary_attributes(attributes, record) if attributes else nullcontext())
            with trial, temporary_settings({'pm_debug_messages': '1', 'pm_print_times': '1',
                                     'pm_test': stages[0]}):
                for stage in stages:
                    (POWER / 'pm_test').write_text(stage + '\n')
                    if selected((POWER / 'pm_test').read_text()) != stage:
                        raise RuntimeError('Kernel did not select the requested test; aborting.')
                    before = statistics()
                    marker = f'macbook-t1-pm-test {stage} {uuid.uuid4()}'
                    Path('/dev/kmsg').write_text(marker + '\n')
                    record(f'START {stage}; before={before}')
                    os.sync()
                    # Kernel PM test stops before entering real sleep and
                    # returns automatically after its configured test delay.
                    (POWER / 'state').write_text('mem\n')
                    after = statistics()
                    log = kernel_log().partition(marker)[2]
                    (directory / f'{stage}.log').write_text(log)
                    record(f'RETURN {stage}; after={after}')
                    if not completed(log, before, after):
                        record(f'FAILED {stage}: kernel fault or incomplete checkpoint; see {stage}.log')
                        raise RuntimeError(f'{stage}: failed or did not reach the test checkpoint; '
                                           'see the kernel log. No later test was started.')
                    record(f'KERNEL CHECKPOINT RETURNED {stage}; physical device checks still required')
            # Driver rebinding during cleanup can fail after the checkpoint.
            # Include those faults even if every expected endpoint is present.
            if kernel_faults(kernel_log().partition(marker)[2]):
                raise RuntimeError('Kernel faults during test or controller rediscovery; '
                                   'see kernel-after.log. No further test was started.')
        except BaseException as error:
            record(f'FAILED: {error}')
            raise
        finally:
            (directory / 'kernel-after.log').write_text(kernel_log())
            record('Current pm_test=' + (POWER / 'pm_test').read_text().strip())
        record('Requested stages returned. Actual deep sleep/wake remains UNVERIFIED.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true',
                        help='Pause all sessions and run the selected PM test stages.')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--later-stages', action='store_true',
                        help='After freezer/devices pass: test platform, processors, then core.')
    selection.add_argument('--stage', choices=STAGES + LATER_STAGES,
                           help='Run only this stage, permitting physical checks before proceeding.')
    trial_selection = parser.add_mutually_exclusive_group()
    trial_selection.add_argument('--thunderbolt-d3cold-off', action='store_true',
                        help='Temporarily disallow D3cold only on the two built-in Thunderbolt branches.')
    trial_selection.add_argument('--thunderbolt-remove', action='store_true',
                        help='Detach healthy Thunderbolt branches before testing and rescan afterward; '
                             'refuses attached storage or unknown PCIe devices.')
    args = parser.parse_args()
    stages = (args.stage,) if args.stage else (LATER_STAGES if args.later_stages else STAGES)
    if not args.run:
        print(f'PLAN ONLY: run {", then ".join(stages)}; stop on error or an incomplete test.')
        print('Save work in every session and keep the lid open. A faulty driver can hang.')
        print('Temporary PM flags are restored on exit, or reset by reboot after a hard hang.')
        print('No GRUB, RTC/PM_TRACE, driver, sleep mode or persistent configuration edits.')
        if args.thunderbolt_d3cold_off:
            print('Temporary D3cold=0 on these verified Thunderbolt functions:')
            for path in thunderbolt_attributes():
                print(path)
        if args.thunderbolt_remove:
            print('Requires pcie_port_pm=off in /proc/cmdline; default port PM failed rediscovery.')
            print('Detach only 0000:03:00.0 and 0000:79:00.0, then rescan their buses afterward.')
            print('Requires a fresh, healthy boot. Thunderbolt/USB peripherals temporarily disconnect.')
            print('Run-time guards refuse missing endpoints, external PCIe devices or attached storage.')
        print('Run: sudo systemd-inhibit --what=sleep:shutdown --mode=block '
              '--why="Staged PM diagnosis" python3 sleep/test-stages.py --run'
              + (' --later-stages' if args.later_stages else '')
              + (f' --stage {args.stage}' if args.stage else '')
              + (' --thunderbolt-d3cold-off' if args.thunderbolt_d3cold_off else '')
              + (' --thunderbolt-remove' if args.thunderbolt_remove else ''))
        return 0
    try:
        run_tests(stages, args.thunderbolt_d3cold_off, args.thunderbolt_remove)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'ERROR: {error}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
