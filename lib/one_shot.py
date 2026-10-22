#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One entry point for the MacBookPro13,2 hardware, sleep, Wi-Fi and desktop setup."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess

from component_support import host

ROOT = Path(__file__).resolve().parents[1]


def commands(args):
    touchid = not getattr(args, 'no_touchid', False)
    touchid_options = [] if args.no_install_deps else ['--install-deps']
    if getattr(args, 'touchid_user', None):
        touchid_options += ['--user', args.touchid_user]
    if touchid and not getattr(args, 'touchid_trial', False):
        yield 'Touch ID installation preflight', [
            'python3', str(ROOT / 'touchid/manage.py'), 'preflight', *touchid_options]
    hardware = ['bash', str(ROOT / 'install-ubuntu.sh'), '--touchbar', '--audio', '--camera']
    if not args.no_install_deps:
        hardware.append('--install-deps')
    yield 'Touch Bar, audio and camera', hardware
    if not args.no_sleep:
        yield 'Apple NVMe suspend workaround', ['bash', str(ROOT / 'sleep/manage.sh'), 'install']
        yield 'Guarded s2idle and PCIe boot configuration', [
            'systemd-inhibit', '--what=sleep:shutdown', '--mode=block',
            '--why=Configure MacBook suspend support',
            'python3', str(ROOT / 'sleep/manage-resume.py'), 'install']
    if not args.no_wifi:
        wifi = ['bash', str(ROOT / 'wifi/install-5ghz.sh')]
        if not args.no_install_deps:
            wifi.append('--install-deps')
        if args.wifi_profile:
            wifi += ['--profile', args.wifi_profile]
        if args.activate_wifi:
            wifi.append('--activate')
        yield '5 GHz Wi-Fi', wifi
    if not args.no_desktop:
        yield 'GNOME user settings', ['bash', str(ROOT / 'desktop/configure.sh')]
    if getattr(args, 'touchid_trial', False):
        yield 'Attended one-boot Touch ID trial', [
            'python3', str(ROOT / 'touchid/manage.py'), 'trial',
            *(['--user', args.touchid_user] if getattr(args, 'touchid_user', None) else [])]
    elif touchid:
        yield 'Persistent Touch ID and fingerprint enrollment support', [
            'systemd-inhibit', '--what=sleep:shutdown', '--mode=block',
            '--why=Configure persistent MacBook Touch ID',
            'python3', str(ROOT / 'touchid/manage.py'), 'install', *touchid_options,
            *(['--no-desktop'] if args.no_desktop else [])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='Show commands without changing the system')
    parser.add_argument('--no-install-deps', action='store_true', help='Use already-installed build/runtime dependencies')
    parser.add_argument('--no-wifi', action='store_true')
    parser.add_argument('--no-sleep', action='store_true',
                        help='Skip NVMe, guarded s2idle and PCIe boot configuration')
    parser.add_argument('--no-desktop', action='store_true', help='Skip GNOME settings, e.g. on a headless system')
    parser.add_argument('--wifi-profile', help='Existing trusted WPA2 profile UUID; otherwise discover the active/only saved profile')
    parser.add_argument('--activate-wifi', action='store_true', help='Activate a new Wi-Fi installation with timed rollback; requires Ethernet')
    touchid_mode = parser.add_mutually_exclusive_group()
    touchid_mode.add_argument('--no-touchid', action='store_true', help='Skip Touch ID installation; preserve any existing setup')
    touchid_mode.add_argument('--touchid-trial', action='store_true',
                        help='Development only: stage a one-boot T1Bridge trial from the verified private bundle')
    parser.add_argument('--touchid-user', help='Desktop account for Touch ID; defaults to the sudo/pkexec account')
    args = parser.parse_args()
    if args.no_wifi and (args.wifi_profile or args.activate_wifi):
        parser.error('--no-wifi cannot be combined with Wi-Fi installation options')
    if args.plan:
        for label, command in commands(args):
            print(label + ': ' + shlex.join(command))
        return 0
    host(root=True)
    if not args.no_desktop and not (os.environ.get('SUDO_UID') or os.environ.get('PKEXEC_UID')):
        parser.error('Run sudo from the desktop user account, or select --no-desktop')
    for label, command in commands(args):
        print(label, flush=True)
        result = subprocess.run(command)
        if result.returncode:
            print('Stopped at: ' + label + '. Completed components are preserved; fix the reported issue and rerun.', flush=True)
            return result.returncode
    print('Selected components are installed/configured. Existing fingerprints and password authentication are preserved.')
    print('No automatic reboot was requested. Newly staged kernel drivers take effect on reboot.')
    if not args.no_sleep:
        print('Sleep configuration is installed; restart if the sleep installer reported a pending boot setting.')
        print('Normal suspend is guarded against attached storage. Physical sleep/wake and battery drain need validation.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
