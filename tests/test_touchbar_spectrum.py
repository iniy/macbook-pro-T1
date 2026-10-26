# SPDX-License-Identifier: MIT
"""Real frequency response, capture lifetime and stable Touch Bar controls."""
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'touchbar'))
from spectrum import Envelope, SILENT, SpectrumWorker, magnitudes
from test_touchbar_media import state, video


def wait_for(check):
    deadline = time.monotonic()+2
    while not check():
        if time.monotonic() >= deadline:
            raise AssertionError('Worker did not reach expected state')
        time.sleep(.005)


class SpectrumTests(unittest.TestCase):
    def test_native_analyzer_distinguishes_frequencies_and_silence(self):
        import gi
        try:
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst
        except (ImportError, ValueError):
            self.skipTest('Optional GStreamer runtime unavailable')
        Gst.init(None)
        if not Gst.ElementFactory.find('spectrum'):
            self.skipTest('Optional GStreamer spectrum plugin unavailable')
        peaks = []
        for frequency in (1000, 4000, 0):
            # No sound card, microphone, or audible test tone is used.
            pipeline = Gst.parse_launch(f'audiotestsrc freq={frequency} volume={.8 if frequency else 0} '
                'num-buffers=8 ! audio/x-raw,rate=16000,channels=1 ! '
                'spectrum bands=64 interval=40000000 threshold=-60 ! fakesink sync=false')
            try:
                pipeline.set_state(Gst.State.PLAYING)
                message = pipeline.get_bus().timed_pop_filtered(Gst.SECOND, Gst.MessageType.ELEMENT)
                self.assertIsNotNone(message)
                values = magnitudes(message.get_structure())
                self.assertIsNotNone(values)
                levels = Envelope().update(values)
                if frequency:
                    peaks.append(max(range(16), key=levels.__getitem__))
                    self.assertGreater(max(levels), 20)
                else:
                    self.assertEqual(levels, SILENT)
            finally:
                pipeline.set_state(Gst.State.NULL)
        self.assertGreater(peaks[1], peaks[0])
        envelope = Envelope()
        envelope.update((0,)*64)
        for _ in range(30):
            levels = envelope.update((-60,)*64)
        self.assertEqual(levels, SILENT)

    def test_worker_stops_hidden_restarts_on_output_change_and_idles_without_polling(self):
        streams = []
        def factory(monitor):
            stream = Mock(monitor=monitor, ended=threading.Event())
            stream.sample.side_effect = lambda: (time.sleep(.005), (-20,)*64)[1]
            stream.close.side_effect = stream.ended.set
            streams.append(stream)
            return stream
        monitor = Mock(return_value='speakers.monitor')
        worker = SpectrumWorker(factory, monitor)
        try:
            self.assertEqual(worker.read(None), SILENT)
            self.assertIsNone(worker.thread)
            worker.read('video-one')
            wait_for(lambda: max(worker.read('video-one')) > 0)
            self.assertEqual(len(streams), 1)
            worker.output_changed()  # A volume event must not reopen the stream.
            wait_for(lambda: monitor.call_count == 2)
            self.assertEqual(len(streams), 1)
            monitor.return_value = 'headphones.monitor'
            worker.output_changed()
            wait_for(lambda: len(streams) == 2)
            self.assertTrue(streams[0].ended.is_set())
            self.assertEqual(streams[-1].monitor, 'headphones.monitor')
            worker.read(None)
            self.assertTrue(streams[-1].ended.wait(1))
            count = monitor.call_count
            worker.output_changed()
            time.sleep(.04)
            self.assertEqual(monitor.call_count, count, 'hidden analyzer must not poll devices')
            worker.read('video-two')
            wait_for(lambda: len(streams) == 3)
        finally:
            worker.close()
        self.assertFalse(worker.thread.is_alive())
        self.assertTrue(all(s.ended.is_set() for s in streams))

    def test_backend_failure_is_quiet_and_backs_off(self):
        factory = Mock(side_effect=RuntimeError('Unavailable'))
        worker = SpectrumWorker(factory, lambda: 'output.monitor')
        try:
            worker.read('video')
            wait_for(lambda: factory.call_count == 1)
            time.sleep(.05)
            self.assertEqual(worker.read('video'), SILENT)
            self.assertEqual(factory.call_count, 1)
            worker.read(None)
        finally:
            worker.close()
        self.assertFalse(worker.thread.is_alive())

    def test_layout_preserves_timeline_and_volume_and_spectrum_is_not_a_button(self):
        import cairo
        from model import scene_for
        from paint import draw, draw_visualizer, regions, hit_test
        for width, height in ((2170, 60), (1085, 30), (1500, 41)):
            for status in ('Playing', 'Paused'):
                scene = scene_for(state(video=video(status=status)))
                boxes = regions(scene, width, height)
                self.assertNotIn('video:backward', [b.action for b in scene.buttons])
                self.assertNotIn('video:forward', [b.action for b in scene.buttons])
                self.assertEqual(hit_test(boxes, 490*width/2170, height/2), 'video:toggle')
                self.assertIsNone(hit_test(boxes, 300*width/2170, height/2))
                timeline = next(b for b in boxes if b[-1].action == 'video:seek')
                self.assertEqual(timeline[0], round(574*width/2170))
                self.assertEqual(timeline[0]+timeline[2], round(1572*width/2170))
                surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
                draw(surface, scene, width, height)
                before = bytes(surface.get_data())
                draw_visualizer(surface, (30,)*16, width, height)
                after = bytes(surface.get_data())
                self.assertNotEqual(before, after)
                draw_visualizer(surface, (30,)*16, width, height)
                self.assertEqual(after, bytes(surface.get_data()), 'partial repaint must not accumulate pixels')
                draw(surface, scene, width, height, spectrum=(30,)*16)
                self.assertEqual(after, bytes(surface.get_data()), 'partial repaint must match a full frame')
                stride = surface.get_stride()
                for row in range(height):
                    offset = row*stride
                    left, right = int(193*width/2170)*4, int(427*width/2170+1)*4
                    self.assertEqual(before[offset:offset+left], after[offset:offset+left])
                    self.assertEqual(before[offset+right:offset+stride], after[offset+right:offset+stride])

    def test_renderer_stops_audio_on_pause_other_apps_mute_and_overlays(self):
        import bridge, protocol, paint
        now, contexts = [0.], []
        class Hardware:
            width, height, features, minor, busy = 2170, 60, 0x3f, 1, False
            def __init__(self): self.memory = bytearray(2170*60*4)
            def submit(self): pass
            def close(self): pass
            def event(self, timeout=.04):
                now[0] += .04
                if now[0] > 1: raise KeyboardInterrupt
        def snapshot():
            if .6 <= now[0] < .8:
                return state(video=None)
            return state(video=video(length=0, sampled_at=1000,
                                     status='Paused' if .4 <= now[0] < .6 else 'Playing'))
        def read(context):
            contexts.append((now[0], context))
            return (int(now[0]*25)%10,)*16 if context else SILENT
        analyzer = Mock(read=Mock(side_effect=read))
        overlay = lambda: {'state': 'authenticate', 'pid': 42} if now[0] >= .8 else None
        with patch.object(protocol, 'Hardware', Hardware), patch.object(bridge, 'SpectrumWorker', return_value=analyzer), \
                patch.object(bridge, 'read_overlay', side_effect=overlay), patch('volume.VolumeWorker.observe'), \
                patch('volume.VolumeWorker.read', side_effect=lambda: {'level': .5, 'muted': .2 <= now[0] < .4}), \
                patch.object(bridge.time, 'monotonic', side_effect=lambda: now[0]), \
                patch.object(paint, 'draw_visualizer', wraps=paint.draw_visualizer) as partial, \
                patch.object(paint, 'draw', wraps=paint.draw) as full:
            with self.assertRaises(KeyboardInterrupt):
                bridge.render_session(SimpleNamespace(read=snapshot))
        self.assertTrue(all(context for stamp, context in contexts if stamp < .2))
        self.assertTrue(all(context is None for stamp, context in contexts if stamp >= .2))
        video_draws = sum(call.args[1].kind == 'video' for call in full.call_args_list)
        self.assertGreater(partial.call_count, video_draws,
                           'audio-only frames should skip the full timeline redraw')
        analyzer.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
