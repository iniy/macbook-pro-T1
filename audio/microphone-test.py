#!/usr/bin/env python3
"""Capture a short microphone signal in RAM and print only numerical levels."""
import argparse
import array
import json
import math
import os
import signal
import subprocess
import tempfile
import wave
from pathlib import Path

from check import check, endpoints


def levels(samples):
    scale = 2147483648
    peak = max((abs(value) for value in samples), default=0) / scale
    rms = math.sqrt(sum((value / scale) ** 2 for value in samples) / max(1, len(samples)))
    return {'peak_dbfs': round(20 * math.log10(max(peak, 1e-12)), 2),
            'rms_dbfs': round(20 * math.log10(max(rms, 1e-12)), 2),
            'clipped_samples': sum(abs(value) >= scale * 0.999 for value in samples)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=8, choices=range(3, 16))
    parser.add_argument('--listen', action='store_true', help='replay once through low-volume PipeWire, then erase')
    parser.add_argument('--listen-volume-percent', type=int, default=25, choices=range(1, 41))
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError('Run in the ordinary desktop session')
    sources = endpoints('sources')
    if len(sources) != 1 or sources[0].get('active_port') != 'analog-input-internal-mic':
        raise RuntimeError('The internal microphone must be the selected capture port')
    source = sources[0]['name']
    subprocess.run(['pactl', 'set-source-mute', source, '0'], check=True)
    print('Recording internal mic in RAM: remain quiet for two seconds, then count aloud.', flush=True)
    process = subprocess.Popen(['pw-record', '--target', source, '--rate', '44100', '--channels', '2',
                                '--format', 's32', '--raw', '-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        data, error = process.communicate(timeout=args.seconds)
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGINT)
        data, error = process.communicate(timeout=5)
    samples = array.array('i', data[:len(data) // 4 * 4])
    blocks = [samples[offset:offset + 44100 * 2] for offset in range(0, len(samples), 44100 * 2)]
    report = {'frames': len(samples) // 2, 'seconds': round(len(samples) / 88200, 2),
              'overall': levels(samples), 'per_second': [levels(block) for block in blocks],
              'retained_recording': False}
    print(json.dumps(report, indent=2))
    if not samples or max(abs(value) for value in samples) == 0:
        raise RuntimeError('No microphone signal captured: ' + error.decode(errors='replace'))
    if args.listen:
        if check():
            raise RuntimeError('Output safety checks failed; no replay')
        sinks = endpoints('sinks')
        if len(sinks) != 1:
            raise RuntimeError('Expected one internal analog sink')
        sink = sinks[0]['name']
        subprocess.run(['pactl', 'set-sink-mute', sink, '1'], check=True)
        subprocess.run(['pactl', 'set-sink-volume', sink, str(args.listen_volume_percent) + '%'], check=True)
        peak = max(abs(value) for value in samples)
        scaled = array.array('h', (int(value / peak * 1638) for value in samples))
        try:
            with tempfile.TemporaryDirectory(prefix='t1-mic-', dir=os.environ.get('XDG_RUNTIME_DIR', '/tmp')) as directory:
                path = Path(directory) / 'voice.wav'
                with wave.open(str(path), 'wb') as wav:
                    wav.setnchannels(2)
                    wav.setsampwidth(2)
                    wav.setframerate(44100)
                    wav.writeframes(scaled.tobytes())
                print(f'Replaying once at {args.listen_volume_percent}% sink volume, normalized signal peak <=5%.', flush=True)
                subprocess.run(['pactl', 'set-sink-mute', sink, '0'], check=True)
                subprocess.run(['pw-play', '--target', sink, str(path)], timeout=20, check=True)
        finally:
            subprocess.run(['pactl', 'set-sink-mute', sink, '1'])
            subprocess.run(['pactl', 'set-sink-volume', sink, '2%'])
        print('Replay complete; temporary recording deleted. Output muted at 2%.')
    print('Nonzero capture is not by itself proof of intelligible voice; correlate levels with the spoken test.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
