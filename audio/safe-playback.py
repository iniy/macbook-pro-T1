#!/usr/bin/env python3
"""Bounded stereo speech test through PipeWire, with verified software attenuation."""
import argparse
import array
import os
from pathlib import Path
import subprocess
import tempfile
import wave

from check import check, endpoints


def stereo_speech():
    samples = array.array('h')
    for channel, name in enumerate(['Front_Left.wav', 'Front_Right.wav']):
        original = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i',
                                          '/usr/share/sounds/alsa/' + name, '-ac', '1', '-ar', '44100',
                                          '-f', 's16le', 'pipe:1'])
        mono = array.array('h', original)
        peak = max(abs(value) for value in mono) or 1
        scale = min(1.0, 0.05 * 32767 / peak)
        for sample in mono:
            pair = [0, 0]
            pair[channel] = int(sample * scale)
            samples.extend(pair)
        samples.extend([0] * (44100 // 3 * 2))
    assert max(abs(value) for value in samples) <= 1639
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--volume-percent', type=int, default=10, choices=range(1, 26))
    parser.add_argument('--output', choices=['speaker', 'headphones'], default='speaker')
    parser.add_argument('--muted', action='store_true')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError('Run playback in the ordinary desktop session, not as root')
    if check():
        raise RuntimeError('Audio verification must pass before playback')
    sinks = endpoints('sinks')
    if len(sinks) != 1:
        raise RuntimeError('Expected exactly one internal analog sink')
    sink = sinks[0]
    if sink.get('active_port') != 'analog-output-' + args.output:
        raise RuntimeError('Requested output is not the active port; refusing playback')
    name = sink['name']
    subprocess.run(['pactl', 'set-sink-mute', name, '1'], check=True)
    subprocess.run(['pactl', 'set-sink-volume', name, str(args.volume_percent) + '%'], check=True)
    try:
        current = endpoints('sinks')[0]
        values = [value['value'] / 65536 for value in current['volume'].values()]
        if not current['mute'] or not values or max(values) > args.volume_percent / 100 + 0.001:
            raise RuntimeError('Could not verify initial mute/low-volume state')
        with tempfile.TemporaryDirectory(prefix='t1-audio-', dir=os.environ.get('XDG_RUNTIME_DIR', '/tmp')) as directory:
            path = Path(directory) / 'stereo.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(44100)
                wav.writeframes(stereo_speech().tobytes())
            print(f'Playing brief left/right speech at {args.volume_percent}% with signal peak <=5%; muted={args.muted}', flush=True)
            if not args.muted:
                subprocess.run(['pactl', 'set-sink-mute', name, '0'], check=True)
            subprocess.run(['pw-play', '--target', name, str(path)], timeout=20, check=True)
    finally:
        subprocess.run(['pactl', 'set-sink-mute', name, '1'])
        subprocess.run(['pactl', 'set-sink-volume', name, '2%'])
    print('Playback transport completed. Listening/channel/distortion confirmation is required; left muted at 2%.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
