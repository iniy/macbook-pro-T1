# SPDX-License-Identifier: MIT
"""Playback progress must never turn a scrub into a stale or unrelated action."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'touchbar'))
from media import MediaClient, PLAYER, PATH, position_at, video_token
from model import Scrub, scene_for


def video(**changes):
    return {**dict(owner=':1.42', track='/track/one', status='Playing',
                   position=30_000_000, length=120_000_000, rate=1.0, sampled_at=100,
                   can_seek=True, can_play=True, can_pause=True), **changes}


def state(**changes):
    return {**dict(kind='desktop', app='firefox.desktop', pid=42, token='fixture', video=video()), **changes}


class PlaybackTests(unittest.TestCase):
    def test_progress_changes_do_not_cancel_a_touch_but_track_changes_do(self):
        original = scene_for(state())
        moving = scene_for(state(video=video(position=31_000_000, sampled_at=101)))
        self.assertEqual(original.signature, moving.signature)
        self.assertNotEqual(original.signature, scene_for(state(video=video(track='/track/two'))).signature)
        self.assertNotEqual(original.signature, scene_for(state(video=video(owner=':1.99'))).signature)
        self.assertEqual(scene_for(state(display=False)).kind, 'blank')
        self.assertEqual(scene_for(state(), {'state': 'authenticate', 'pid': 42}).kind, 'fingerprint')
        self.assertEqual(scene_for(state(), fn=True).kind, 'function')
        self.assertEqual(scene_for(state(kind='shell-dialog', actions=[])).kind, 'shell-dialog')

    def test_time_tracks_playback_rate_and_stays_still_when_paused(self):
        self.assertEqual(position_at(video(rate=2), 105), 40_000_000)
        self.assertEqual(position_at(video(status='Paused'), 105), 30_000_000)
        self.assertEqual(position_at(video(), 1000), 120_000_000)

    def test_unknown_duration_and_unseekable_streams_have_no_scrub_target(self):
        from paint import regions, hit_test
        for sample in (video(length=0), video(can_seek=False)):
            scene = scene_for(state(video=sample))
            for width, height in ((2170, 60), (1085, 30)):
                boxes = regions(scene, width, height)
                self.assertIsNone(hit_test(boxes, width/2, height/2))
                self.assertEqual(hit_test(boxes, width*370/2170, height/2), 'video:toggle')

    def test_seek_clamps_to_the_track_and_revalidates_track_and_focus(self):
        client = MediaClient.__new__(MediaClient)
        client.properties, client.call = Mock(return_value=video()), Mock(return_value=())
        client.seek_points = {}
        self.assertTrue(client.activate('video:seek:1', video(), lambda: True))
        self.assertEqual(client.call.call_args.args[-1], ('/track/one', 119_999_999))
        client.call.reset_mock()
        self.assertFalse(client.activate('video:seek:0.5', video(), lambda: False))
        client.properties.return_value = video(track='/track/replaced')
        self.assertFalse(client.activate('video:toggle', video(), lambda: True))
        client.properties.return_value = video(can_seek=False)
        self.assertFalse(client.activate('video:seek:0.5', video(), lambda: True))
        client.properties.return_value = video()
        self.assertFalse(client.activate('video:seek:nan', video(), lambda: True))
        client.call.assert_not_called()

    def test_browser_player_and_typed_seek_over_a_private_dbus(self):
        for options in ([], ['--chrome'], ['--vlc']):
            result = subprocess.run(['dbus-run-session', '--', sys.executable,
                str(ROOT / 'tests/touchbar/media-integration.py'), *options], capture_output=True, text=True, timeout=12)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS browser MPRIS', result.stdout)


class FirefoxClockTests(unittest.TestCase):
    """A playing browser reporting zero must not loop the rendered timeline."""
    def setUp(self):
        from gi.repository import GLib
        self.GLib, self.now = GLib, 100.0
        self.client = MediaClient.__new__(MediaClient)
        self.client.GLib = GLib
        self.client.samples, self.client.seek_points, self.client.last_tracks = {}, {}, {}
        self.props = dict(Position=0, PlaybackStatus='Playing', Rate=1.0,
            CanControl=True, CanPlay=True, CanPause=True, CanSeek=True,
            Metadata={'mpris:trackid': '/track/one', 'xesam:title': 'Fixture',
                      'mpris:length': 120_000_000})
        self.client.call = Mock(side_effect=lambda *args: (self.props,))
        self.client.drain = Mock()
        clock = patch('media.time.monotonic', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def read(self, seconds=0, firefox=True):
        self.now += seconds
        return self.client.properties(':1.42', firefox=firefox)

    def test_startup_without_seek_signal_keeps_timeline_advancing(self):
        from motion import TimelineMotion
        motion, positions = TimelineMotion(), []
        first = self.read()
        context = video_token(state(video=first))
        for tick in range(120):
            sample = self.read(.15)
            self.props['Metadata'].pop('mpris:length', None)
            self.assertEqual(sample['length'], 120_000_000)
            self.assertEqual(video_token(state(video=sample)), context)
            positions.append(motion.update(context, sample, None, self.now))
        self.assertTrue(all(b > a for a, b in zip(positions, positions[1:])))
        self.assertAlmostEqual(positions[-1], 18_000_000, delta=200)
        # Recovery uses the existing property reads; no extra browser calls.
        self.assertTrue(all(call.args[3] == 'GetAll' for call in self.client.call.call_args_list))

    def test_zero_after_valid_sample_pause_resume_rate_and_recovery(self):
        self.props['Position'] = 25_000_000
        self.read()
        self.props['Position'] = 0
        self.assertAlmostEqual(self.read(2)['position'], 27_000_000, delta=2)
        self.props.update(Position=28_000_000, PlaybackStatus='Paused')
        self.read(1)
        self.assertEqual(self.read(10)['position'], 28_000_000)
        self.props.update(Position=0, PlaybackStatus='Playing', Rate=2.0)
        self.assertEqual(self.read(10)['position'], 28_000_000)
        self.assertAlmostEqual(self.read(2)['position'], 32_000_000, delta=2)
        self.props['Position'] = 37_000_000
        self.assertEqual(self.read()['position'], 37_000_000)
        self.props.update(Position=0, PlaybackStatus='Paused')
        self.assertEqual(self.read()['position'], 0)

    def test_explicit_seek_to_zero_and_backwards_overrides_fallback(self):
        self.read()
        self.read(10)
        for target in (4_000_000, 0):
            self.client.seeked(None, ':1.42', PATH, PLAYER, 'Seeked',
                               self.GLib.Variant('(x)', (target,)))
            self.assertEqual(self.read()['position'], target)
            self.assertAlmostEqual(self.read(2)['position'], target+2_000_000, delta=2)

    def test_video_change_replay_and_stop_do_not_inherit_old_clock(self):
        original = dict(self.props['Metadata'])
        first = self.read()
        self.read(10)
        self.props['Metadata'] = {**original, 'xesam:title': 'Another fixture'}
        self.assertEqual(self.read()['position'], 0)
        self.read(5)
        self.props['Metadata'] = original
        replay = self.read()
        self.assertEqual(replay['identity'], first['identity'])
        self.assertEqual(replay['position'], 0)
        self.read(10)
        self.props['PlaybackStatus'] = 'Stopped'
        self.assertIsNone(self.read())
        self.props['PlaybackStatus'] = 'Playing'
        self.assertEqual(self.read()['position'], 0)

    def test_chrome_and_other_players_keep_authoritative_zero(self):
        self.props['Position'] = 25_000_000
        self.read(firefox=False)
        self.props['Position'] = 0
        self.assertEqual(self.read(2, firefox=False)['position'], 0)


class ScrubTests(unittest.TestCase):
    def setUp(self):
        self.scrub = Scrub()
        self.scrub.update_scene('track-one', 0)
        self.hit = lambda x, y: 'video:seek' if 0 <= x <= 100 and 0 <= y < 60 else None
        self.fraction = lambda x, y: x / 100

    def touch(self, contacts, when):
        return self.scrub.input(contacts, self.hit, self.fraction, when)

    def test_drag_commits_only_the_last_position_on_release(self):
        self.assertIsNone(self.touch([(0, 20, 30)], 1))
        self.assertIsNone(self.touch([(0, 80, 30)], 1.2))
        self.assertEqual(self.touch([], 1.3), .8)
        self.assertIsNone(self.touch([], 1.4))

    def test_multitouch_context_changes_and_sliding_into_the_bar_cancel(self):
        for interrupt in ('multitouch', 'track-change', 'outside'):
            self.setUp()
            self.touch([(0, 20, 30)], 1)
            if interrupt == 'multitouch':
                self.touch([(0, 20, 30), (1, 80, 30)], 1.1)
            elif interrupt == 'track-change':
                self.scrub.update_scene('track-two', 1.1)
            else:
                self.touch([(0, 120, 30)], 1.1)
            self.assertIsNone(self.touch([], 1.2))
        self.setUp()
        self.touch([(0, 120, 30)], 1)
        self.touch([(0, 50, 30)], 1.1)
        self.assertIsNone(self.touch([], 1.2))

    def test_renderer_can_scrub_while_playback_progress_is_updating(self):
        import bridge
        import protocol
        from types import SimpleNamespace
        now, actions = [0.0], []
        case = self

        class Hardware:
            width, height, features, minor = 2170, 60, 0x3f, 1
            def __init__(self):
                self.memory, self.busy = bytearray(2170*60*4), False
            def submit(self):
                case.assertFalse(self.busy)
                self.frame, self.busy, self.release_at = bytes(self.memory), True, now[0] + .08
            def event(self, timeout=.04):
                if self.busy:
                    case.assertEqual(bytes(self.memory), self.frame)
                now[0] = round(now[0] + .04, 2)
                if self.busy and now[0] >= self.release_at:
                    self.busy = False
                if now[0] >= 1:
                    raise KeyboardInterrupt
                contacts = {.4: [(0, 850, 30)], .48: [(0, 1100, 30)], .6: []}
                if now[0] in contacts:
                    return int(now[0]*1_000_000), False, contacts[now[0]]
            def close(self):
                pass

        worker = SimpleNamespace(read=lambda: state(video=video(
            position=30_000_000 + int(now[0]*1_000_000), sampled_at=now[0])),
            dispatch=lambda action, token: actions.append((action, token)))
        with patch.object(protocol, 'Hardware', Hardware), patch.object(bridge, 'read_overlay', return_value=None), \
                patch('volume.VolumeWorker.observe'), \
                patch.object(bridge.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(KeyboardInterrupt):
                bridge.render_session(worker)
        self.assertEqual(actions, [('video:seek:0.545000', video_token(state()))])


if __name__ == '__main__':
    unittest.main()
