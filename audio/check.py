#!/usr/bin/env python3
"""Verify audio bindings and the software-volume path, without playing audio."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from component_support import audio_codec, host, output, session_command


def pulse(kind):
    return json.loads(subprocess.check_output(session_command('pactl', '-f', 'json', 'list', kind), text=True))


def endpoints(kind):
    return [item for item in pulse(kind)
            if 'HDA:10138409,106b3600,' in item.get('properties', {}).get('alsa.components', '')
            and (kind != 'sources' or item.get('properties', {}).get('media.class') == 'Audio/Source')]


def check():
    host()
    audio_codec()
    failures = []
    def result(condition, text):
        print(('PASS ' if condition else 'FAIL ') + text)
        if not condition:
            failures.append(text)
    kernel = os.uname().release
    result(': installed' in output('dkms', 'status', '-m', 'macbook-t1-audio', '-v', '1.0.0', '-k', kernel),
           'Audio DKMS installed for running kernel')
    module = 'snd_hda_codec_cs8409'
    result('/updates/dkms/' in output('modinfo', '-F', 'filename', module), 'Custom CS8409 selected')
    result(output('modinfo', '-F', 'vermagic', module).startswith(kernel + ' '), 'Audio module ABI matches')
    loaded = Path('/sys/module') / module / 'srcversion'
    result(loaded.exists() and loaded.read_text().strip() == output('modinfo', '-F', 'srcversion', module),
           'Installed custom CS8409 is actually loaded')
    objects = json.loads(subprocess.check_output(session_command('pw-dump'), text=True))
    cards = [o.get('info', {}).get('props', {}) for o in objects
             if o.get('type') == 'PipeWire:Interface:Device'
             and 'HDA:10138409,106b3600,' in o.get('info', {}).get('props', {}).get('alsa.components', '')]
    result(bool(cards) and all(c.get('api.alsa.soft-mixer') in (True, 'true') for c in cards),
           'ALSA card opened with forced software mixer')
    for kind in ['sinks', 'sources']:
        items = endpoints(kind)
        result(bool(items), 'PipeWire internal audio ' + kind)
        for item in items:
            print('  format:', item.get('sample_specification'), 'port:', item.get('active_port'))
            if kind == 'sinks':
                # pipewire-pulse can advertise HW_VOLUME_CTRL for a server-side
                # software control. Check the actual ALSA card/node properties.
                result(item.get('properties', {}).get('api.alsa.soft-mixer') == 'true',
                       'PipeWire sink software-mixer policy')
                print('  muted:', item.get('mute'), 'volume:',
                      [v.get('value_percent') for v in item.get('volume', {}).values()])
    print('Physical listening, jack switching and voice capture are separate tests; enumeration is not proof of sound.')
    return int(bool(failures))


if __name__ == '__main__':
    try:
        raise SystemExit(check())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
