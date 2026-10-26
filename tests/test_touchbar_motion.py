# SPDX-License-Identifier: MIT
"""Animation stays continuous without changing the browser's seek target."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'touchbar'))
from motion import FrameBlend, TimelineMotion
from test_touchbar_media import video, state


class MotionTests(unittest.TestCase):
    def test_coarse_browser_samples_do_not_step_backwards(self):
        motion, positions = TimelineMotion(), []
        for tick in range(600):
            now = tick/60
            # Some players repeat a position for several property polls.
            sample = video(position=30_000_000+int(now)*1_000_000, sampled_at=now)
            positions.append(motion.update('same-video', sample, None, now))
        steps = [b-a for a, b in zip(positions, positions[1:])]
        self.assertGreater(min(steps), 0)
        self.assertLess(max(steps), 26_000)
        self.assertLess(abs(positions[-1] - 40_000_000), 1_000_000)

    def test_drag_eases_and_release_does_not_flash_the_old_position(self):
        motion = TimelineMotion()
        sample = video(status='Paused', sampled_at=0)
        motion.update('same-video', sample, None, 0)
        motion.update('same-video', sample, .25, 1)
        middle = motion.update('same-video', sample, .8, 1+1/60)
        self.assertGreater(middle, 30_000_000)
        self.assertLess(middle, 96_000_000)
        motion.released(.8, sample, 1.02)
        held = [motion.update('same-video', sample, None, 1.02+i/60) for i in range(30)]
        self.assertTrue(all(b >= a for a, b in zip(held, held[1:])))
        self.assertLess(abs(held[-1]-96_000_000), 100)
        confirmed = video(status='Paused', position=96_000_000, sampled_at=1.6)
        self.assertEqual(motion.update('same-video', confirmed, None, 1.6), 96_000_000)
        self.assertIsNone(motion.pending)
        self.assertEqual(motion.update('new-video', sample, None, 1.7), 30_000_000)

    def test_rejected_seek_returns_to_browser_clock_and_pause_settles(self):
        motion = TimelineMotion()
        sample = video(status='Paused', sampled_at=0)
        motion.update('same-video', sample, .9, 0)
        motion.released(.9, sample, .1)
        for tick in range(1, 181):
            result = motion.update('same-video', sample, None, tick/60)
        self.assertEqual(result, 30_000_000)
        self.assertEqual(motion.update('same-video', sample, None, 4), result)
        self.assertIsNone(motion.pending)

    def test_frame_changes_dissolve_and_fast_reversals_remain_continuous(self):
        blend = FrameBlend()
        self.assertEqual(blend.update('one', 0, 0), ((0, 1),))
        self.assertEqual(blend.update('one', 1, 1), ((0, 1),))
        middle = dict(blend.update('one', 1, 1.05))
        self.assertAlmostEqual(middle[0], .5)
        self.assertAlmostEqual(middle[1], .5)
        self.assertEqual(dict(blend.update('one', 2, 1.05)), middle)
        self.assertEqual(blend.update('one', 2, 1.16), ((2, 1),))
        self.assertEqual(blend.update('another-video', 3, 1.17), ((3, 1),))

    def test_renderer_keeps_smooth_drag_and_skips_redundant_playback_frames(self):
        import bridge
        import protocol
        now, frames, actions, events = [0.0], [], [], set()
        class Hardware:
            width, height, features, minor, busy = 2170, 60, 0x3f, 1, False
            def __init__(self):
                self.memory = bytearray(2170*60*4)
            def submit(self):
                frames.append(now[0])
            def event(self, timeout=.04):
                now[0] += timeout
                for at, contacts in ((.4, [(0, 850, 30)]), (.5, [(0, 1100, 30)]), (.65, [])):
                    if now[0] >= at and at not in events:
                        events.add(at)
                        return int(now[0]*1_000_000), False, contacts
                if now[0] > .9:
                    raise KeyboardInterrupt
            def close(self):
                pass
        worker = SimpleNamespace(read=lambda: state(video=video(position=30_000_000,
            sampled_at=0)), dispatch=lambda *args: actions.append(args))
        with patch.object(protocol, 'Hardware', Hardware), patch.object(bridge, 'read_overlay', return_value=None), \
                patch('spectrum.SpectrumWorker.read', return_value=(0,)*16), \
                patch('volume.VolumeWorker.observe'), \
                patch.object(bridge.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(KeyboardInterrupt):
                bridge.render_session(worker)
        moving=[tick for tick in frames if .5 <= tick <= .65]
        self.assertGreaterEqual(len(moving),8)
        self.assertLess(max(b-a for a,b in zip(moving,moving[1:])),.035)
        self.assertLess(len(frames),40)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0][0], 'video:seek:0.545000')

    def test_missing_duration_cannot_create_a_one_millisecond_busy_loop(self):
        import bridge,protocol
        now,calls=[0.0],[]
        class Hardware:
            width,height,features,minor,busy=2170,60,0x3f,1,False
            def __init__(self):self.memory=bytearray(2170*60*4)
            def submit(self):pass
            def event(self,timeout=.04):
                calls.append(timeout);now[0]+=timeout
                if now[0]>1:raise KeyboardInterrupt
            def close(self):pass
        worker=SimpleNamespace(read=lambda:state(video=video(length=0,position=0,sampled_at=1000)),dispatch=lambda *args:None)
        with patch.object(protocol,'Hardware',Hardware),patch.object(bridge,'read_overlay',return_value=None), \
                patch('spectrum.SpectrumWorker.read', return_value=(0,)*16), \
                patch('volume.VolumeWorker.observe'), \
                patch.object(bridge.time,'monotonic',side_effect=lambda:now[0]):
            with self.assertRaises(KeyboardInterrupt):bridge.render_session(worker)
        self.assertLessEqual(len(calls),62)


if __name__ == '__main__':
    unittest.main()
