#!/usr/bin/env python3
"""Select only the Apple T1 H.264 camera and run its on-demand browser adapter."""
import os
from pathlib import Path
import subprocess
import sys
from check import capture_nodes


def main():
    available = capture_nodes()
    nodes = [node for node, formats in available if "'H264'" in formats]
    if not nodes and any("'MJPG'" in formats for _, formats in available):
        print('T1 MJPEG mode already supports browsers; adapter not needed.')
        return
    if len(nodes) != 1:
        raise RuntimeError('Expected one Apple T1 H.264 camera; no USB settings changed')
    output = Path('/sys/class/video4linux/video10/name')
    if not output.exists() or output.read_text().strip() != 'FaceTime HD (Browser)':
        raise RuntimeError('Browser camera module is missing; run camera/browser-setup.py --system as root')
    executable = Path(__file__).resolve().with_name('browser-bridge')
    os.execv(str(executable), [str(executable), nodes[0], '/dev/video10'])


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
