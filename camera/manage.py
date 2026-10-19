#!/usr/bin/env python3
"""Register camera diagnostics using the existing standard UVC/iBridge stack."""
import argparse
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from component_support import host, run

STATE = Path('/var/lib/macbook-t1-camera')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('--install-deps', action='store_true')
    args = parser.parse_args()
    host(root=True)
    if STATE.is_symlink():
        raise RuntimeError('Refusing symlink camera state')
    if args.action == 'uninstall':
        if STATE.exists():
            (STATE / 'complete').unlink(missing_ok=True)
            STATE.rmdir()
        print('Camera component registration removed; shared iBridge and stock UVC preserved.')
        return
    if not Path('/var/lib/macbook-t1-ubuntu/complete').is_file():
        raise RuntimeError('Camera uses the existing guarded T1 initialization. Install --touchbar first or use --all.')
    if args.install_deps:
        run('apt-get', 'install', '--no-remove', '-y', 'v4l-utils', 'ffmpeg')
    # No USB configuration writes, camera-specific DKMS or additional boot service.
    STATE.mkdir(mode=0o700, exist_ok=True)
    (STATE / 'complete').write_text('stock-uvcvideo; shared guarded T1 configuration 1\n')
    print('Camera component ready; stock uvcvideo and existing T1 initialization provide persistence.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
