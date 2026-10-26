# SPDX-License-Identifier: MIT
"""Thumbnail loading must not change media targets or stall input."""
import io
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'touchbar'))
from thumbnails import CELLS, Filmstrip, ThumbnailWorker, load_filmstrip, parse_storyboard, youtube_id, tile_bounds

SOURCE, OTHER = 'abcdefghijk', '0123456789_'


def page(source=SOURCE, duration=100, count=100):
    data = {'videoDetails': {'videoId': source, 'lengthSeconds': str(duration)},
            'storyboards': {'playerStoryboardSpecRenderer': {'spec':
                f'https://i.ytimg.com/sb/{source}/L$L/$N.jpg?test=1|80#45#{count}#10#10#1000#M$M#signature'}}}
    return ('var ytInitialPlayerResponse = ' + json.dumps(data) + ';').encode()


def sprite(count=100):
    from PIL import Image
    image = Image.new('RGB', (800, ((count+9)//10)*45))
    for i in range(count):
        frame = Image.new('RGB', (80, 45), (i*2, 255-i*2, 20))
        image.paste(frame, ((i%10)*80, (i//10)*45))
    result = io.BytesIO()
    image.save(result, format='PNG')
    return result.getvalue()


def strip(source=SOURCE):
    return load_filmstrip(source, fetch=lambda url: page(source) if '/watch?' in url else sprite())


class StoryboardTests(unittest.TestCase):
    def test_only_supported_public_video_urls_are_used(self):
        for url in (f'https://www.youtube.com/watch?v={SOURCE}&private=discarded',
                    f'https://youtu.be/{SOURCE}', f'https://m.youtube.com/shorts/{SOURCE}'):
            self.assertEqual(youtube_id(url), SOURCE)
        for url in (f'https://youtube.com.evil.test/watch?v={SOURCE}',
                    f'file:///tmp/{SOURCE}', 'https://www.youtube.com/watch?v=short', None):
            self.assertIsNone(youtube_id(url))

    def test_real_sample_positions_and_reuse_of_sprite_sheets(self):
        from PIL import Image
        requests = []
        def fetch(url):
            requests.append(url)
            return page() if '/watch?' in url else sprite()
        result = load_filmstrip(SOURCE, fetch=fetch)
        image = Image.open(io.BytesIO(result.png))
        self.assertEqual(image.size, (800, 42))
        self.assertEqual(len(requests), 2, 'each shared sprite should be fetched once')
        self.assertEqual(len(result.positions), 100, 'lens uses dense frames without additional downloads')
        atlas = Image.open(io.BytesIO(result.previews))
        self.assertEqual(atlas.size, (1480, 260))
        self.assertEqual(result.frame_at(.501), 50)
        self.assertEqual(result.frame_at(1), 99)
        self.assertEqual(atlas.getpixel((10*74+37, 2*52+26)), (100, 155, 20))
        for i in range(CELLS):
            index = int((i+.5)/CELLS*100)
            left, right = tile_bounds(i)
            self.assertEqual(image.getpixel(((left+right)//2, 20)), (index*2, 255-index*2, 20))

    def test_short_last_sprite_and_rejection_of_wrong_video(self):
        # YouTube's final sprite can omit unused rows.
        def fetch(url):
            if '/watch?' in url:
                return page(duration=121, count=121)
            return sprite(21) if '/M1.jpg' in url else sprite()
        self.assertTrue(load_filmstrip(SOURCE, fetch=fetch).png)
        with self.assertRaises(ValueError):
            parse_storyboard(page(OTHER).decode(), SOURCE)
        with self.assertRaises(TimeoutError):
            load_filmstrip(SOURCE, fetch=lambda url: page(), cancelled=lambda: True)

    def test_live_or_missing_storyboards_fall_back(self):
        for data in ({'videoDetails': {'videoId': SOURCE, 'lengthSeconds': '100', 'isLiveContent': True}},
                     {'videoDetails': {'videoId': SOURCE, 'lengthSeconds': '100'}}):
            with self.assertRaises(ValueError):
                parse_storyboard('ytInitialPlayerResponse = ' + json.dumps(data), SOURCE)


class ThumbnailWorkerTests(unittest.TestCase):
    def test_slow_or_superseded_download_does_not_block_or_show_the_wrong_video(self):
        started, release = threading.Event(), threading.Event()
        ready = strip(OTHER)
        def loader(source, cancelled):
            if source == SOURCE:
                started.set()
                release.wait(2)
                if cancelled():
                    raise TimeoutError
            return ready
        worker = ThumbnailWorker(loader)
        first = {'thumbnail_source': SOURCE, 'length': 100_000_000, 'can_seek': True}
        second = {**first, 'thumbnail_source': OTHER}
        try:
            before = time.monotonic()
            self.assertIsNone(worker.read(first))
            self.assertLess(time.monotonic()-before, .05)
            self.assertTrue(started.wait(1))
            self.assertIsNone(worker.read(second))
            release.set()
            deadline = time.monotonic()+2
            result = worker.read(second)
            while result is None and time.monotonic() < deadline:
                time.sleep(.01)
                result = worker.read(second)
            self.assertIs(result, ready)
            self.assertIsNone(worker.read({**second, 'length': 10_000_000}), 'ad duration must not match')
            self.assertIsNone(worker.read({'length': 0, 'can_seek': False}))
        finally:
            release.set()
            worker.close()
            worker.thread.join(2)


class FilmstripRendererTests(unittest.TestCase):
    def test_lens_dissolve_blends_pixels_without_darkening(self):
        import cairo
        from paint import glass_lens
        from PIL import Image
        art = strip()
        renders = []
        for weights in (((0, 1),), ((99, 1),), ((0, .5), (99, .5))):
            surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 998, 60)
            glass_lens(cairo.Context(surface), art, .5, False, weights)
            surface.flush()
            output = io.BytesIO()
            surface.write_to_png(output)
            renders.append(Image.open(io.BytesIO(output.getvalue())).getpixel((490, 30)))
        for first, last, blended in zip(*renders):
            self.assertAlmostEqual(blended, (first+last)/2, delta=2)

    def test_filmstrip_keeps_the_same_gesture_identity_and_seek_mapping(self):
        from model import scene_for
        from paint import draw, regions, seek_fraction
        from test_touchbar_media import video, state
        import cairo
        original = scene_for(state())
        decorated = scene_for(state(video=video(filmstrip=strip())))
        self.assertEqual(original.signature, decorated.signature)
        for width, height in ((2170, 60), (1085, 30)):
            boxes = regions(original, width, height)
            self.assertEqual(boxes, regions(decorated, width, height))
            self.assertEqual(seek_fraction(boxes, width*1100/2170, height/2), .545)
            frames = []
            for scene in (original, decorated):
                surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
                draw(surface, scene, width, height)
                frames.append(bytes(surface.get_data()))
            self.assertNotEqual(frames[0], frames[1])

    def test_a_paused_timeline_redraws_when_thumbnails_arrive(self):
        import bridge
        import protocol
        from types import SimpleNamespace
        from test_touchbar_media import state, video
        now, frames, art = [0.0], [], strip()
        class Hardware:
            width, height, features, minor, busy = 2170, 60, 0x3f, 1, False
            def __init__(self):
                self.memory = bytearray(2170*60*4)
            def submit(self):
                frames.append(bytes(self.memory))
            def event(self, timeout=.04):
                now[0] = round(now[0]+.04, 2)
                if now[0] >= .8:
                    raise KeyboardInterrupt
            def close(self):
                pass
        def snapshot():
            sample = video(status='Paused')
            if now[0] >= .4:
                sample['filmstrip'] = art
            return state(video=sample)
        with patch.object(protocol, 'Hardware', Hardware), patch.object(bridge, 'read_overlay', return_value=None), \
                patch.object(bridge.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(KeyboardInterrupt):
                bridge.render_session(SimpleNamespace(read=snapshot))
        self.assertEqual(len(frames), 2)
        self.assertNotEqual(frames[0], frames[1])


if __name__ == '__main__':
    unittest.main()
