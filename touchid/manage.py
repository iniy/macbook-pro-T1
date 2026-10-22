#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Touch ID installation and separate build/physical acceptance reporting."""
import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys

import adapters
import build
import deploy
from probe import inspect, assessment
from transaction import atomic


def report(args):
    result = assessment(inspect())
    import setup
    import persistent
    result['default_install_enabled'] = setup.supported(result['host'])
    result['persistent_configured'] = persistent.configured()
    result['installed_private_bundle'] = build.PREFIX.is_dir()
    import trial
    result['trial_boot'] = trial.booted()
    if result['eligible']:
        result['eligible'] = False
        result['status'] = 'blocked'
        result['reasons'].append('Live migration has not been accepted by this integration')
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print('Touch ID persistent boot: ' + ('configured' if result['persistent_configured'] else 'not configured'))
        print('Full physical acceptance remains incomplete; this report does not change configuration.')
        for reason in result['reasons']:
            print('  - ' + reason)
        print('Existing drivers and password authentication are preserved.')
        print('Recovery and remaining tests: TOUCHID-RECOVERY.md and TOUCHID-TEST-RESULTS.md')
    output = args.output
    if output is None and args.action == 'auto' and os.geteuid() == 0:
        from transaction import safe
        folder = safe(Path('/var/lib/macbook-t1-touchid-reports'))
        folder.mkdir(mode=0o700, exist_ok=True)
        if folder.stat().st_mode & 0o077:
            raise RuntimeError('Report directory must be private (0700)')
        output = folder / 'latest.json'
    if output:
        atomic(output.absolute(), (json.dumps(result, indent=2) + '\n').encode())
    # The legacy report-only action succeeds; an incomplete explicit check does not.
    return 0 if args.action == 'auto' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['auto', 'check', 'preflight', 'install', 'install-resume', 'dependencies', 'build', 'install-bundle', 'verify-bundle', 'remove-bundle', 'package-deb', 'trial', 'rollback-trial'])
    parser.add_argument('--work', type=Path, default=Path(__file__).resolve().parents[1] / 'sources/touchid-build')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--install-deps', action='store_true')
    parser.add_argument('--no-desktop', action='store_true', help='Skip the optional GNOME OSD extension')
    parser.add_argument('--userspace-only', action='store_true', help='CI build without kernel headers; cannot stage a hardware trial')
    parser.add_argument('--user', default=os.environ.get('SUDO_USER'), help='Local desktop account for Touch ID installation or trial')
    args = parser.parse_args()
    try:
        if args.action in ('auto', 'check'):
            return report(args)
        if args.action in ('preflight', 'install', 'install-resume', 'trial', 'rollback-trial'):
            if os.geteuid() != 0:
                raise RuntimeError('Touch ID installation and staging require root')
            import fcntl
            import trial
            fd = os.open('/run/macbook-t1-touchid.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if args.action in ('preflight', 'install', 'install-resume'):
                    import setup
                    if args.action == 'preflight':
                        setup.preflight(args.user, args.install_deps)
                    elif args.action == 'install-resume':
                        setup.install_resume(args.user)
                    else:
                        setup.install(args.user, args.install_deps, desktop=not args.no_desktop)
                elif args.action == 'trial':
                    if not args.user:
                        raise RuntimeError('A local graphical --user is required')
                    trial.prepare(args.user)
                else:
                    trial.rollback()
            finally:
                os.close(fd)
            return 0
        if args.action == 'dependencies':
            host = inspect()
            command = adapters.dependency_command(host['distro'], None if args.userspace_only else host['kernel'])
            if args.install_deps:
                if os.geteuid() != 0:
                    raise RuntimeError('Dependency installation requires root')
                subprocess.run(command, check=True)
            else:
                print(shlex.join(command))
        elif args.action == 'build':
            build.build(args.work, None if args.userspace_only else platform.release())
        elif args.action == 'remove-bundle':
            if os.geteuid() != 0:
                raise RuntimeError('Removal requires root')
            deploy.uninstall()
            print('Private bundle removed; existing drivers, PAM and protected state preserved.')
        else:
            bundle = args.bundle or args.work / 'stage' / build.PREFIX.relative_to('/')
            if args.action == 'verify-bundle':
                deploy.verify(bundle)
                print('Bundle content and pinned revisions verified; no hardware acceptance implied.')
            elif args.action == 'install-bundle':
                if inspect()['distro'] != 'ubuntu' or inspect()['version'] != '26.10':
                    raise RuntimeError('Private bundle install is currently build-tested only on Ubuntu 26.10')
                print('Installed inert bundle:', deploy.install(bundle))
                print('Drivers, services and PAM were not activated.')
            elif args.action == 'package-deb':
                if args.output is None:
                    raise RuntimeError('--output is required')
                deploy.package_deb(bundle, args.output)
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Touch ID: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
