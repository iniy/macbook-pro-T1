#!/usr/bin/python3
# SPDX-License-Identifier: MIT
"""Wake the T1 display parked by appletbdrm 0.1.12 after guarded s2idle."""
import errno
import fcntl
import os
from pathlib import Path
import signal
import stat
import sys

# HID feature-report contract documented in T1Bridge PR #47 and issue #18.
# This changes only display power; it never opens the SEP or resets USB.
REPORT = 3
LENGTH = 15
AWAKE = bytes((REPORT, 2, 0xf4, 1)) + bytes(11)
GET_FEATURE = 0xc0000000 | (LENGTH << 16) | (ord('H') << 8) | 0x07
SET_FEATURE = 0xc0000000 | (LENGTH << 16) | (ord('H') << 8) | 0x06
HOOK = 'usr/lib/systemd/system-sleep/90-macbook-t1-touchid-resume'


def enabled(root=Path('/')):
    if 't1bridge.trial=1' not in (root / 'proc/cmdline').read_text().split():
        return False
    return ((root / 'sys/class/dmi/id/product_name').read_text().strip() == 'MacBookPro13,2'
            and '[s2idle]' in (root / 'sys/power/mem_sleep').read_text().split())


def device(root=Path('/')):
    matches = []
    for node in (root / 'sys/class/hidraw').glob('hidraw*'):
        try:
            hid = (node / 'device').resolve(strict=True)
            interface = next(p for p in hid.parents if (p / 'bInterfaceNumber').is_file())
            usb = interface.parent
            values = tuple((path / name).read_text().strip() for path, name in (
                (usb, 'idVendor'), (usb, 'idProduct'), (usb, 'bConfigurationValue'),
                (interface, 'bInterfaceNumber')))
            if values != ('05ac', '8600', '2', '06'):
                continue
            major, minor = map(int, (node / 'dev').read_text().strip().split(':'))
            matches.append((root / 'dev' / node.name, os.makedev(major, minor)))
        except (FileNotFoundError, StopIteration):
            continue  # A device can disappear while sysfs is being enumerated.
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one T1 display HID interface; no power command sent')
    return matches[0]


def power(fd):
    report = bytearray(LENGTH)
    report[0] = REPORT
    length = fcntl.ioctl(fd, GET_FEATURE, report, True)
    if length != LENGTH or report[0] != REPORT or report[1] not in (1, 2):
        raise RuntimeError('Unexpected T1 display power report; no further commands sent')
    return report[1]


def recover(record=print, root=Path('/'), read_only=False):
    if not enabled(root):
        record('T1 display wake skipped outside the supported T1Bridge s2idle boot.')
        return
    if os.geteuid() != 0:
        raise PermissionError('T1 display wake requires administrator authentication')
    path, expected = device(root)
    fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISCHR(info.st_mode) or info.st_rdev != expected:
            raise RuntimeError('T1 HID device changed during discovery; no command sent')
        before = power(fd)
        record('T1 display power: ' + ('awake' if before == 2 else 'parked'))
        if before == 2 or read_only:
            return
        if fcntl.ioctl(fd, SET_FEATURE, bytearray(AWAKE), True) != LENGTH:
            raise OSError(errno.EIO, 'Incomplete T1 display wake write')
        if power(fd) != 2:
            raise RuntimeError('T1 display did not acknowledge awake state')
        record('T1 display acknowledged awake state; physical visibility still needs confirmation.')
    finally:
        os.close(fd)


def install(tx):
    tx.put(HOOK, Path(__file__).read_bytes(), 0o755)


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if args not in (['recover'], ['check']):
        # systemd-sleep calls hooks with pre/post and the requested sleep action.
        action = os.environ.get('SYSTEMD_SLEEP_ACTION', args[1] if len(args) == 2 else '')
        if len(args) != 2 or args[0] != 'post' or args[1] != 'suspend' or action != 'suspend':
            return 0
    def timed_out(*_):
        raise TimeoutError('T1 display wake exceeded 15 seconds')
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(15)
    try:
        recover(lambda message: print('macbook-t1-resume:', message, flush=True),
                read_only=args == ['check'])
    except (OSError, RuntimeError) as error:
        print('macbook-t1-resume: FAILED:', error, file=sys.stderr, flush=True)
        return 1
    finally:
        signal.alarm(0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
