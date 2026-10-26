# SPDX-License-Identifier: MIT
"""Volume drag, restoration, mixer coalescing and existing layout protection."""
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'touchbar'))
from model import scene_for
from paint import draw, hit_test, regions, volume_fraction
from volume import HOLD_DELAY, SLIDER_TRAVEL, VolumePanel, VolumeWorker


class VolumePanelTests(unittest.TestCase):
    def setUp(self):
        self.worker = Mock()
        self.worker.read.return_value = {'level': .48, 'muted': False}
        self.panel = VolumePanel(self.worker)
        self.base = scene_for({'kind': 'desktop', 'token': 'focused', 'actions': []})

    def opened(self):
        self.panel.button_input([(0, 2079, 30)], lambda *_: 'audio:up', self.base, .5, 2170, 60, True)
        self.panel.scene(self.base, .9)
        self.panel.button_input([], lambda *_: None, self.base, .95, 2170, 60, False)
        return self.panel.scene(self.base, 1)

    def test_open_never_changes_volume_and_close_restores_exact_controls(self):
        expanded = self.opened()
        self.worker.set_level.assert_not_called()
        self.assertEqual(expanded.kind, 'volume')
        self.assertEqual(expanded.volume['level'], .48)
        self.panel.action('volume:close', self.base, 2)
        self.assertEqual(self.panel.scene(self.base, 2), self.base)
        self.worker.hide.assert_called_once()

    def test_drag_changes_volume_before_release_without_snapping_back(self):
        expanded = self.opened()
        boxes = regions(expanded, 2170, 60)
        hit = lambda x, y: hit_test(boxes, x, y)
        fraction = lambda x, y: volume_fraction(boxes, x, y)
        left, _, width, _, _ = boxes[0]
        point = lambda value: left + width*(113+276*value)/502
        self.panel.input([(0, point(.5), 30)], hit, fraction, 1.5)
        self.assertEqual(self.worker.set_level.call_args.args, (.5,))
        self.panel.input([(0, point(.8), 30)], hit, fraction, 1.6)
        self.assertAlmostEqual(self.worker.set_level.call_args.args[0], .8)
        self.panel.input([], hit, fraction, 1.7)
        self.assertAlmostEqual(self.panel.scene(self.base, 1.71).volume['level'], .8)
        self.assertEqual(self.panel.scene(self.base, 1.71).signature, expanded.signature)
        self.assertEqual(self.panel.scene(self.base, 6.8).kind, 'volume')
        self.panel.action('volume:close', self.base, 7)
        self.assertEqual(self.panel.scene(self.base, 7), self.base)

    def test_interruption_and_multitouch_cannot_apply_a_later_drag(self):
        for cause in ('focus', 'fingerprint', 'function', 'dialog'):
            with self.subTest(cause=cause):
                self.setUp()
                self.opened()
                interrupted = {
                    'focus': scene_for({'kind': 'desktop', 'token': 'different'}),
                    'fingerprint': scene_for({}, {'state': 'authenticate', 'pid': 42}),
                    'function': scene_for({}, fn=True),
                    'dialog': scene_for({'kind': 'shell-dialog', 'token': 'focused', 'actions': []}),
                }[cause]
                self.assertEqual(self.panel.scene(interrupted, 2), interrupted)
                self.panel.input([(0, 1000, 30)], lambda *_: 'volume:level', lambda *_: 1, 3)
                self.worker.set_level.assert_not_called()
        self.setUp()
        self.opened()
        hit, fraction = lambda *_: 'volume:level', lambda x, y: x/100
        self.panel.input([(0, 20, 30)], hit, fraction, 1.5)
        self.panel.input([(0, 20, 30), (1, 90, 30)], hit, fraction, 1.6)
        self.panel.input([(0, 90, 30)], hit, fraction, 1.7)
        self.panel.input([], hit, fraction, 1.8)
        self.worker.set_level.assert_called_once_with(.2)

    def test_scaled_compact_apple_layout_and_slider_limits(self):
        expanded = self.opened()
        for width, height in ((2170, 60), (1085, 30)):
            boxes = regions(expanded, width, height)
            self.assertEqual([b[4].action for b in boxes], ['volume:level', 'volume:close'])
            x, y, w, h, _ = next(b for b in boxes if b[4].action == 'volume:level')
            self.assertEqual(volume_fraction(boxes, x, h/2), 0)
            self.assertEqual(volume_fraction(boxes, x+w-1, h/2), 1)
            self.assertAlmostEqual(volume_fraction(boxes, x+w/2, h/2), .5)
            self.assertGreater(x/width, .77)
            self.assertEqual(w, 480*width/2170)
            for left, top, bw, bh, button in boxes:
                self.assertEqual(hit_test(boxes, left+bw/2, top+bh/2), button.action)

    def test_renderer_tap_hold_drag_and_mute_use_the_mixer_without_duplicate_commands(self):
        import bridge, protocol
        now, frames = [0.0], []
        class Hardware:
            width, height, features, minor, busy = 2170, 60, 0x3f, 1, False
            def __init__(self): self.memory = bytearray(2170*60*4)
            def submit(self): frames.append(bytes(self.memory))
            def close(self): pass
            def event(self, timeout=.04):
                now[0] = round(now[0]+.04, 2)
                if now[0] >= 2.4:
                    raise KeyboardInterrupt
                events = {.4: [(0, 2050, 30)], .52: [], .92: [(0, 2050, 30)],
                          1.32: [(0, 2050-.2*SLIDER_TRAVEL, 30)], 1.44: [],
                          1.84: [(0, 1699, 30)], 1.96: []}
                if now[0] in events:
                    return int(now[0]*1_000_000), False, events[now[0]]
        desktop = SimpleNamespace(read=lambda: {'kind': 'desktop', 'token': 'focused'}, dispatch=Mock())
        with patch.object(protocol, 'Hardware', Hardware), patch.object(bridge, 'VolumePanel', return_value=self.panel), \
                patch.object(bridge, 'read_overlay', return_value=None), \
                patch.object(bridge.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(KeyboardInterrupt):
                bridge.render_session(desktop)
        levels = [c.args[0] for c in self.worker.set_level.call_args_list]
        self.assertEqual(len(levels), 1)
        self.assertAlmostEqual(levels[-1], .28, delta=.002)
        self.worker.step.assert_called_once_with(1)
        self.worker.toggle_mute.assert_called_once_with()
        desktop.dispatch.assert_not_called()
        self.assertEqual(frames[0], frames[-1])

    def test_speaker_press_slide_release_is_relative_and_returns_to_controls(self):
        hit = lambda *_: 'audio:up'
        self.assertTrue(self.panel.button_input([(0, 2050, 30)], hit, self.base, 1, 2170, 60, True))
        self.worker.set_level.assert_not_called()
        # Expansion never sets volume to 100% just because the speaker button
        # sits at the right edge. Moving left changes the existing level.
        self.assertEqual(self.panel.scene(self.base, 1.01), self.base)
        self.panel.button_input([(0, 2050, 30)], hit, self.base, 1.1, 2170, 60, False)
        self.worker.set_level.assert_not_called()
        self.assertEqual(self.panel.scene(self.base, 1.36).kind, 'volume')
        self.panel.button_input([(0, 2050-.2*SLIDER_TRAVEL, 30)], hit, self.base, 1.4, 2170, 60, False)
        self.assertAlmostEqual(self.worker.set_level.call_args.args[0], .28)
        self.panel.button_input([], hit, self.base, 1.5, 2170, 60, False)
        self.assertEqual(self.panel.scene(self.base, 1.5), self.base)
        self.worker.step.assert_not_called()

    def test_short_taps_step_once_and_do_not_open_slider(self):
        for action, direction in (('audio:up', 1), ('audio:down', -1)):
            with self.subTest(action=action):
                self.setUp()
                hit = lambda *_: action
                self.panel.button_input([(0, 2050, 30)], hit, self.base, 1, 2170, 60, True)
                self.worker.step.assert_not_called()
                self.assertEqual(self.panel.scene(self.base, 1.1), self.base)
                self.panel.button_input([], hit, self.base, 1.15, 2170, 60, False)
                self.panel.button_input([], hit, self.base, 1.2, 2170, 60, True)
                self.worker.step.assert_called_once_with(direction)
                self.worker.open.assert_not_called()
                self.assertEqual(self.panel.scene(self.base, 2), self.base)

    def test_stationary_hold_opens_without_new_input_and_release_keeps_slider(self):
        for action, x in (('audio:up', 2079), ('audio:down', 1889)):
            for width, height in ((2170, 60), (1085, 30)):
                self.setUp()
                hit = lambda *_: action
                scaled_x = x*width/2170
                self.panel.button_input([(0, scaled_x, height/2)], hit, self.base, 1, width, height, True)
                self.assertEqual(self.panel.scene(self.base, 1+HOLD_DELAY-.01), self.base)
                expanded = self.panel.scene(self.base, 1+HOLD_DELAY+.01)
                self.assertEqual(expanded.kind, 'volume')
                box = regions(expanded, width, height)[0]
                self.assertTrue(box[0] <= scaled_x < box[0]+box[2])
                thumb = box[0] + box[2]*(113+276*.48)/502
                self.assertLess(abs(thumb-scaled_x), width*.08)
                self.panel.button_input([], hit, self.base, 1.4, width, height, False)
                self.assertEqual(self.panel.scene(self.base, 10).kind, 'volume')
                self.worker.open.assert_called_once()
                self.worker.step.assert_not_called()
                self.worker.set_level.assert_not_called()

    def test_cancelled_short_press_cannot_step_or_open(self):
        for cause in ('multitouch', 'focus', 'stale', 'slide', 'brief'):
            self.setUp()
            hit = lambda *_: 'audio:up'
            self.panel.button_input([(0, 2050, 30)], hit, self.base, 1, 2170, 60, True)
            if cause == 'multitouch':
                self.panel.button_input([(0, 2050, 30), (1, 1900, 30)], hit, self.base, 1.1, 2170, 60, False)
            elif cause == 'focus':
                self.panel.scene(scene_for({'kind': 'desktop', 'token': 'other'}), 1.1)
            elif cause == 'stale':
                self.panel.cancel_touch()
            elif cause == 'slide':
                self.panel.button_input([(0, 1900, 30)], hit, self.base, 1.1, 2170, 60, False)
            self.panel.button_input([], hit, self.base, 1.02 if cause == 'brief' else 1.2, 2170, 60, False)
            self.assertEqual(self.panel.scene(self.base, 2), self.base)
            self.worker.step.assert_not_called()
            self.worker.open.assert_not_called()
            self.worker.set_level.assert_not_called()

    def test_mute_color_tracks_system_state_and_only_changes_mute_button(self):
        import cairo
        def pixels(scene):
            surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 2170, 60)
            draw(surface, scene, 2170, 60)
            return list(memoryview(surface.get_data()).cast('I'))
        normal = pixels(self.base)
        self.assertEqual(pixels(self.panel.scene(self.base, 1)), normal)
        self.panel.action('audio:mute', self.base, 1)
        self.worker.toggle_mute.assert_called_once()
        self.assertEqual(pixels(self.panel.scene(self.base, 1.1)), normal)
        # Only a confirmed mixer state makes the button red, including external changes.
        self.worker.read.return_value = {'level': .48, 'muted': True}
        muted_scene = self.panel.scene(self.base, 2)
        self.assertEqual(muted_scene.signature, self.base.signature)
        muted = pixels(muted_scene)
        self.assertNotEqual(muted, normal)
        for i, (before, after) in enumerate(zip(normal, muted)):
            if not 1608 <= i % 2170 < 1790:
                self.assertEqual(before, after)
        pixel = muted[30*2170+1620]
        self.assertGreater((pixel >> 16) & 255, 240)
        self.assertLess((pixel >> 8) & 255, 80)
        self.worker.read.return_value = {'level': .48, 'muted': False}
        self.assertEqual(pixels(self.panel.scene(self.base, 3)), normal)


class VolumeWorkerTests(unittest.TestCase):
    def wait_for(self, predicate):
        deadline = time.monotonic()+2
        while not predicate():
            self.assertLess(time.monotonic(), deadline, 'Volume worker did not finish')
            time.sleep(.005)

    def test_slow_mixer_coalesces_drags_and_delivers_final_value_on_close(self):
        worker, entered, release = VolumeWorker(monitor=False), threading.Event(), threading.Event()
        writes = []
        def command(*args):
            if args[0] == 'get-volume': return 'Volume: 0.48'
            if args[0] == 'set-volume':
                writes.append(float(args[-1]))
                if len(writes) == 1:
                    entered.set()
                    release.wait(1)
            return ''
        worker.command = command
        self.addCleanup(worker.close)
        worker.open()
        self.wait_for(lambda: worker.read() is not None)
        worker.set_level(.2)
        self.assertTrue(entered.wait(1))
        for level in (.3, .5, .7, .9): worker.set_level(level)
        worker.hide()
        release.set()
        self.wait_for(lambda: worker.read()['level'] == .9)
        self.assertEqual(writes, [.2, .9])

    def test_worker_is_idle_until_open_and_validates_values_and_unmutes_drag(self):
        worker = VolumeWorker(monitor=False)
        worker.command = Mock(return_value='Volume: 0.48 [MUTED]')
        self.addCleanup(worker.close)
        self.assertIsNone(worker.thread)
        worker.open()
        self.wait_for(lambda: worker.read() is not None)
        self.assertTrue(worker.read()['muted'])
        before = worker.command.call_count
        for level in (-1, 2, float('nan'), float('inf'), '0.5'): worker.set_level(level)
        self.assertEqual(worker.command.call_count, before)
        worker.set_level(.6)
        self.wait_for(lambda: worker.read()['level'] == .6)
        self.assertFalse(worker.read()['muted'])
        worker.command.assert_any_call('set-volume', '-l', '1.0', '@DEFAULT_AUDIO_SINK@', '0.600')
        worker.command.assert_any_call('set-mute', '@DEFAULT_AUDIO_SINK@', '0')
        worker.hide()
        before = worker.command.call_count
        time.sleep(.1)
        self.assertEqual(worker.command.call_count, before)

    def test_unavailable_mixer_does_not_change_volume_or_block_input(self):
        worker = VolumeWorker(monitor=False)
        worker.command = Mock(side_effect=subprocess.TimeoutExpired('wpctl', .4))
        self.addCleanup(worker.close)
        worker.open()
        self.wait_for(lambda: worker.command.call_count == 1)
        self.assertIsNone(worker.read())
        worker.set_level(.5)
        self.assertFalse(worker.commands)

    def test_steps_and_mute_preserve_order_and_read_actual_result(self):
        worker = VolumeWorker(monitor=False)
        commands, state = [], {'level': .48, 'muted': False}
        def command(*args):
            commands.append(args)
            if args[0] == 'set-volume':
                state['level'] += .05 if args[-1] == '5%+' else -.05
            if args[0] == 'set-mute':
                state['muted'] = not state['muted']
            return f"Volume: {state['level']:.2f}" + (' [MUTED]' if state['muted'] else '')
        worker.command = command
        self.addCleanup(worker.close)
        worker.step(1)
        worker.step(-1)
        worker.toggle_mute()
        self.wait_for(lambda: worker.read() and worker.read()['muted'])
        self.assertEqual(worker.read(), {'level': .48, 'muted': True})
        writes = [c for c in commands if c[0] != 'get-volume']
        self.assertEqual(writes, [('set-volume', '-l', '1.0', '@DEFAULT_AUDIO_SINK@', '5%+'),
                                 ('set-volume', '@DEFAULT_AUDIO_SINK@', '5%-'),
                                 ('set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle')])
        worker.toggle_mute()
        self.wait_for(lambda: not worker.read()['muted'])

    def test_external_mute_events_refresh_visible_controls_without_idle_polling(self):
        worker = VolumeWorker(monitor=False)
        worker.subscribed = True  # Simulate a healthy event subscription.
        worker.command = Mock(return_value='Volume: 0.48')
        self.addCleanup(worker.close)
        worker.observe(True)
        self.wait_for(lambda: worker.read() is not None)
        before = worker.command.call_count
        with worker.condition:
            worker.next_read = 0
            worker.condition.notify()
        time.sleep(.15)
        self.assertEqual(worker.command.call_count, before)
        worker.command.return_value = 'Volume: 0.48 [MUTED]'
        worker.source_changed()
        self.wait_for(lambda: worker.read()['muted'])
        worker.observe(False)
        before = worker.command.call_count
        worker.source_changed()
        time.sleep(.15)
        self.assertEqual(worker.command.call_count, before)
        worker.observe(True)
        self.wait_for(lambda: worker.command.call_count > before)

    def test_failed_mute_toggle_retains_last_confirmed_state(self):
        worker = VolumeWorker(monitor=False)
        worker.command = Mock(return_value='Volume: 0.48 [MUTED]')
        self.addCleanup(worker.close)
        worker.observe(True)
        self.wait_for(lambda: worker.read() is not None)
        worker.command.side_effect = RuntimeError('Mixer unavailable')
        worker.toggle_mute()
        self.wait_for(lambda: worker.last_write > 0)
        self.assertTrue(worker.read()['muted'])
        self.assertTrue(worker.dirty)


if __name__ == '__main__':
    unittest.main()
