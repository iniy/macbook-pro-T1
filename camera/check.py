#!/usr/bin/env python3
"""Discover T1 UVC capture nodes; optionally decode short streams in memory."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys


def t1_ancestor(device):
    for parent in [device.resolve(), *device.resolve().parents]:
        vendor, product = parent / 'idVendor', parent / 'idProduct'
        if vendor.is_file() and product.is_file():
            return vendor.read_text().strip() == '05ac' and product.read_text().strip() == '8600'
    return False


def capture_nodes():
    nodes = []
    for entry in sorted(Path('/sys/class/video4linux').glob('video*')):
        if not t1_ancestor(entry / 'device'):
            continue
        node = '/dev/' + entry.name
        formats = subprocess.check_output(['v4l2-ctl', '-d', node, '--list-formats-ext'], text=True)
        if "'MJPG'" in formats:
            nodes.append((node, formats))
    return nodes


def capture(node, resolution):
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'v4l2',
               '-input_format', 'mjpeg', '-video_size', resolution, '-framerate', '30',
               '-i', node, '-frames:v', '30', '-vf', 'scale=32:24,format=gray', '-f', 'rawvideo', 'pipe:1']
    p = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    frames = [p.stdout[i:i + 768] for i in range(0, len(p.stdout), 768)]
    result = {'resolution': resolution, 'decoded_frames': len(frames),
              'distinct_frames': len(set(frames)), 'decoder_exit': p.returncode,
              'pixel_stdev': round(statistics.pstdev(p.stdout), 2) if p.stdout else 0}
    print(json.dumps(result))
    if p.returncode or len(frames) != 30 or any(len(frame) != 768 for frame in frames):
        raise RuntimeError('T1 frame capture/decode failed: ' + p.stderr.decode(errors='replace'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', help='briefly activate the camera; retain no frames')
    args = parser.parse_args()
    nodes = capture_nodes()
    if not nodes:
        raise RuntimeError('No T1 MJPEG capture node; check shared Touch Bar/iBridge initialization')
    for node, formats in nodes:
        print('PASS standard T1 UVC capture node:', node)
        print(formats)
        if args.capture:
            for resolution in ['640x480', '1280x720']:
                capture(node, resolution)
    print('PASS camera ' + ('frame capture/decode; no recording retained' if args.capture else 'enumeration; capture not requested'))
    print('Browser preview and reboot/suspend must be tested separately.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
