#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Apply only an explicitly selected physical country on the supported board."""
from pathlib import Path
import re
import subprocess
import sys

from check import hardware

if __name__ == '__main__':
    if len(sys.argv) != 2 or not re.fullmatch('[A-Z]{2}', sys.argv[1]):
        raise SystemExit('Expected an explicitly configured ISO country')
    if Path('/sys/class/dmi/id/product_name').read_text().strip() != 'MacBookPro13,2':
        raise SystemExit('Unsupported model')
    hardware()
    subprocess.run(['/usr/sbin/iw', 'reg', 'set', sys.argv[1]], check=True)
