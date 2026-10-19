#!/usr/bin/env python3
"""Unified component selection; legacy no-argument entrypoints stay Touch Bar-only."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def commands(action, components, deps=False):
    order = ['camera', 'audio', 'touchbar'] if action == 'uninstall' else ['touchbar', 'audio', 'camera']
    for component in order:
        if component not in components:
            continue
        name = 'ubuntu' if component == 'touchbar' else component
        command = ['bash', str(ROOT / f'{action}-{name}.sh')]
        if deps:
            command.append('--install-deps')
        yield component, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'verify', 'uninstall'])
    for component in ['touchbar', 'audio', 'camera', 'all']:
        parser.add_argument('--' + component, action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--verify', action='store_true')
    mode.add_argument('--uninstall', action='store_true')
    parser.add_argument('--install-deps', action='store_true')
    args = parser.parse_args()
    action = 'verify' if args.verify else 'uninstall' if args.uninstall else args.action
    if args.install_deps and action != 'install':
        parser.error('--install-deps applies only to installation')
    selected = {c for c in ['touchbar', 'audio', 'camera'] if getattr(args, c)}
    if args.all or not selected:
        selected = {'touchbar', 'audio', 'camera'}
    complete_suite = selected == {'touchbar', 'audio', 'camera'}
    if complete_suite and action == 'uninstall':
        subprocess.run([sys.executable, str(ROOT / 'lib/suite.py'), 'uninstall'], check=True)
    failed = False
    for component, command in commands(action, selected, args.install_deps):
        print(f'=== {action}: {component} ===', flush=True)
        rc = subprocess.run(command).returncode
        print(f'{component}: exit {rc}', flush=True)
        failed |= rc != 0
    if complete_suite and action == 'install' and not failed:
        subprocess.run([sys.executable, str(ROOT / 'lib/suite.py'), 'install'], check=True)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
