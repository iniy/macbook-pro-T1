#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Apply only an explicitly selected physical country on the supported board."""
from pathlib import Path
import argparse
import re
import subprocess

from check import hardware, interface

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('country')
    parser.add_argument('--interface', help='Dispatcher interface; ignore other adapters')
    args = parser.parse_args()
    if not re.fullmatch('[A-Z]{2}', args.country):
        raise SystemExit('Expected an explicitly configured ISO country')
    if Path('/sys/class/dmi/id/product_name').read_text().strip() != 'MacBookPro13,2':
        raise SystemExit('Unsupported model')
    dev = hardware()
    if args.interface and args.interface != interface(dev):
        return
    subprocess.run(['/usr/sbin/iw', 'reg', 'set', args.country], check=True)


if __name__ == '__main__':
    main()
