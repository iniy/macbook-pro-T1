#!/usr/bin/env python3
"""Check session isolation and recovery on aborted sleep without hardware PM."""
from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('sleep_audio', Path(__file__).resolve().parents[1] / 'sleep/audio.py')
AUDIO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIO)
SINK = {
    'name': 'alsa_output.pci-0000_00_1f.3.analog-stereo', 'state': 'RUNNING',
    'mute': False, 'volume': {'left': 19000, 'right': 18000},
    'properties': {'media.class': 'Audio/Sink', 'device.bus_path': 'pci-0000:00:1f.3',
                   'alsa.components': 'HDA:10138409,106b3600,00100100',
                   'alsa.name': 'CS8409/CS42L83 Analog'},
}


@contextmanager
def server(items=None, fail_suspend=False, connected=True):
    items = deepcopy(items if items is not None else [SINK])
    session = (SimpleNamespace(pw_uid=1000, pw_name='testuser', pw_dir='/home/testuser'),
               Path('/run/user/1000'), (1, 2))
    mutations = []

    def pactl(_session, *args):
        if args == ('-f', 'json', 'list', 'sinks'):
            return json.dumps(items)
        verb, name, state = args
        mutations.append(args)
        assert verb == 'suspend-sink'
        for sink in items:
            if sink['name'] == name:
                sink['state'] = 'SUSPENDED' if state == '1' else 'IDLE'
        if fail_suspend and state == '1':
            raise subprocess.TimeoutExpired('pactl', 10)
        return ''

    with patch.object(AUDIO, 'sessions', return_value=[session]), \
         patch.object(AUDIO, 'pactl', side_effect=pactl), \
         patch.object(AUDIO, 'connected', return_value=connected):
        yield items, mutations, session


class PlaybackRecovery(unittest.TestCase):
    def test_reopens_pcm_and_preserves_volume_mute_and_identity(self):
        with server() as (items, mutations, _):
            AUDIO.reopen_playback(lambda _: None)
            self.assertEqual([call[-1] for call in mutations], ['1', '0'])
            for key in ('name', 'mute', 'volume', 'properties'):
                self.assertEqual(items[0][key], SINK[key])

    def test_timed_out_suspend_is_undone_before_reporting_failure(self):
        with server(fail_suspend=True) as (_, mutations, _):
            with self.assertRaisesRegex(RuntimeError, 'recover internal playback'):
                AUDIO.reopen_playback(lambda _: None)
            self.assertEqual([call[-1] for call in mutations], ['1', '0'])

    def test_already_suspended_sink_stays_suspended(self):
        with server([dict(SINK, state='SUSPENDED')]) as (_, mutations, _):
            AUDIO.reopen_playback(lambda _: None)
            self.assertEqual(mutations, [])

    def test_other_audio_devices_and_monitors_are_untouched(self):
        unrelated = []
        for key, value in [('media.class', 'Audio/Source'), ('alsa.components', 'HDA:80862809'),
                           ('device.bus_path', 'pci-0000:06:00.0'), ('alsa.name', 'HDMI')]:
            item = deepcopy(SINK)
            item['properties'][key] = value
            unrelated.append(item)
        with server(unrelated) as (_, mutations, _):
            AUDIO.reopen_playback(lambda _: None)
            self.assertEqual(mutations, [])

    def test_restarted_session_is_not_resumed(self):
        with server(connected=False) as (_, mutations, _):
            AUDIO.reopen_playback(lambda _: None)
            self.assertEqual([call[-1] for call in mutations], ['1'])

    def test_no_desktop_session_is_a_noop(self):
        with patch.object(AUDIO, 'sessions', return_value=[]), patch.object(AUDIO, 'pactl') as pactl:
            AUDIO.reopen_playback(lambda _: None)
            pactl.assert_not_called()

    def test_one_failed_session_does_not_prevent_other_users_recovering(self):
        sessions = [(SimpleNamespace(pw_uid=uid), Path('/run/user') / str(uid), (1, uid))
                    for uid in (1000, 1001)]
        calls = []

        def pactl(session, *args):
            calls.append((session[0].pw_uid, args))
            if session[0].pw_uid == 1000:
                raise RuntimeError('First server failed')
            return ''

        with patch.object(AUDIO, 'sessions', return_value=sessions), \
             patch.object(AUDIO, 'sinks', return_value=[SINK]), \
             patch.object(AUDIO, 'connected', return_value=True), \
             patch.object(AUDIO, 'pactl', side_effect=pactl):
            with self.assertRaisesRegex(RuntimeError, 'First server failed'):
                AUDIO.reopen_playback(lambda _: None)
        self.assertEqual([(uid, args[-1]) for uid, args in calls],
                         [(1000, '1'), (1000, '0'), (1001, '1'), (1001, '0')])

    def test_session_commands_drop_root_and_have_a_timeout(self):
        session = (SimpleNamespace(pw_uid=1000, pw_name='testuser', pw_dir='/home/testuser'),
                   Path('/run/user/1000'), (1, 2))
        with patch.object(AUDIO.subprocess, 'check_output', return_value='[]') as command:
            AUDIO.pactl(session, '-f', 'json', 'list', 'sinks')
        argv = command.call_args.args[0]
        self.assertEqual(argv[:7], ['/usr/sbin/runuser', '-u', 'testuser', '--', '/usr/bin/env', '-i',
                                   'PATH=/usr/bin:/bin'])
        self.assertIn('PULSE_SERVER=unix:/run/user/1000/pulse/native', argv)
        self.assertEqual(command.call_args.kwargs['timeout'], 10)


if __name__ == '__main__':
    unittest.main()
