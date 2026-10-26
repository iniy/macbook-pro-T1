# SPDX-License-Identifier: MIT
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'touchbar'))
from model import Button, Gesture, Scene, scene_for
from protocol import Hardware, ProtocolError, decode, input_frame, packet
from desktop import validate_state
from overlay import read_overlay


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.g = Gesture()
        self.g.update_scene('dialog-a', 0)
        self.hit = lambda x, y: 'cancel' if x < 100 else 'power'

    def press(self, when=1, x=10):
        return self.g.input([(0, x, 20)], self.hit, when)

    def release(self, when=1.1):
        return self.g.input([], self.hit, when)

    def test_only_release_activates(self):
        self.assertIsNone(self.press())
        self.assertEqual(self.release(), 'cancel')
        self.assertIsNone(self.release(1.2))

    def test_dialog_replacement_cancels_held_touch(self):
        self.press()
        self.g.update_scene('dialog-b', 1.01)
        self.assertIsNone(self.release())
        self.press(2)
        self.assertEqual(self.release(2.1), 'cancel')

    def test_drag_between_buttons_cancels(self):
        self.press()
        self.press(1.05, 150)
        self.assertIsNone(self.release())

    def test_multitouch_cancels(self):
        self.press()
        self.g.input([(0, 10, 20), (1, 150, 20)], self.hit, 1.05)
        self.assertIsNone(self.release())

    def test_finger_already_down_at_scene_change_cannot_confirm(self):
        self.assertIsNone(self.press(0.1))
        self.press(1)
        self.assertIsNone(self.release())

    def test_short_bounce_and_long_hold_do_not_activate(self):
        self.press()
        self.assertIsNone(self.release(1.01))
        self.press(2)
        self.assertIsNone(self.release(8))

    def test_touch_outside_buttons_cannot_slide_into_confirm(self):
        self.g.input([(0, 10, 20)], lambda *_: None, 1)
        self.press(1.05)
        self.assertIsNone(self.release())


class SceneTests(unittest.TestCase):
    def test_confirmation_has_only_its_own_two_buttons(self):
        state = {'kind': 'shell-dialog', 'title': 'Restart', 'token': 'fixture',
                 'actions': [{'id': 'cancel', 'label': 'Cancel'}, {'id': 'restart', 'label': 'Restart'}]}
        result = scene_for(state, features=0x3f)
        self.assertEqual([b.action for b in result.buttons], ['context:cancel', 'context:restart'])
        self.assertEqual(scene_for({**state, 'actions': []}).buttons, ())

    def test_fingerprint_preempts_context_and_fn(self):
        result = scene_for({'actions': [{'id': 'power', 'label': 'Power Off'}]},
                           {'state': 'authenticate', 'pid': 42}, True)
        self.assertEqual(result.kind, 'fingerprint')
        self.assertEqual([b.action for b in result.buttons], ['hardware:cancel'])

    def test_blank_display_preempts_fingerprint(self):
        self.assertEqual(scene_for({'display': False}, {'state': 'authenticate'}).kind, 'blank')

    def test_fn_keys_correct_codes(self):
        self.assertEqual([b.action for b in scene_for({}, fn=True).buttons],
                         ['key:1'] + [f'key:{i}' for i in (*range(59, 69), 87, 88)])

    def test_locked_has_no_app_or_media_actions(self):
        self.assertTrue(all(b.action.startswith(('key:', 'audio:'))
                            for b in scene_for({'kind': 'locked'}).buttons))

    def test_button_pagination_keeps_all_actions_reachable(self):
        state = {'token': 'fixture', 'actions': [{'id': str(i), 'label': str(i)} for i in range(12)]}
        found = {b.action for page in range(3) for b in scene_for(state, page=page).buttons
                 if b.action.startswith('context:')}
        self.assertEqual(found, {f'context:{i}' for i in range(12)})

    def test_disabled_and_suggested_preserved(self):
        result = scene_for({'actions': [{'id': 'ok', 'label': 'OK', 'enabled': False, 'suggested': True}]})
        self.assertFalse(result.buttons[1].enabled)
        self.assertTrue(result.buttons[1].suggested)

    def test_unknown_brightness_not_offered(self):
        self.assertFalse(any(b.action.startswith(('light:', 'backlight:')) for b in scene_for({}).buttons))


class ProtocolTests(unittest.TestCase):
    def test_frame_encoding(self):
        payload = struct.pack('<IQI', 1, 3, 0)
        self.assertEqual(decode(packet(3, 7, payload)), (3, 7, payload))

    def test_malformed_headers_rejected(self):
        for data in (b'', b'T1HW', packet(4, 2, b'a')[:-1], b'XXXX' + packet(4, 2)[4:]):
            with self.assertRaises(ProtocolError):
                decode(data)

    def test_contact_range_and_unique_ids_enforced(self):
        contact = struct.pack('<BBBBII', 0, 1, 1, 0, 20, 20)
        self.assertEqual(input_frame(struct.pack('<QBBH', 1, 0, 1, 0) + contact, 100, 60),
                         (1, False, [(0, 20, 20)]))
        for raw in (struct.pack('<QBBH', 1, 2, 1, 0) + contact,
                    struct.pack('<QBBH', 1, 0, 2, 0) + contact * 2,
                    struct.pack('<QBBH', 1, 0, 1, 0) + struct.pack('<BBBBII', 0, 1, 1, 0, 100, 20)):
            with self.assertRaises(ProtocolError):
                input_frame(raw, 100, 60)

    def test_buffer_not_reused_until_release(self):
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        hw = Hardware.__new__(Hardware)
        hw.sock, hw.memory, hw.fd = left, None, None
        hw.sequence, hw.frame_id, hw.busy, hw.pending = 1, 0, False, {}
        try:
            self.assertTrue(hw.submit())
            _, request, _ = decode(right.recv(1024))
            self.assertFalse(hw.submit())
            right.send(packet(0x8002, request))
            hw.event()
            self.assertTrue(hw.busy)
            right.send(packet(0x9001, 0, struct.pack('<IQ', 1, 1)))
            hw.event()
            self.assertFalse(hw.busy)
            self.assertTrue(hw.submit())
        finally:
            hw.close()
            right.close()

    def test_wrong_release_rejected(self):
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        hw = Hardware.__new__(Hardware)
        hw.sock, hw.memory, hw.fd, hw.pending, hw.busy, hw.frame_id = left, None, None, {}, True, 1
        try:
            right.send(packet(0x9001, 0, struct.pack('<IQ', 1, 2)))
            with self.assertRaises(ProtocolError):
                hw.event()
        finally:
            hw.close()
            right.close()


class DesktopContractTests(unittest.TestCase):
    def test_invalid_or_duplicate_actions_fail(self):
        valid = {'version': 1, 'kind': 'shell-dialog', 'token': 'test',
                 'actions': [{'id': 'a', 'label': 'Cancel'}]}
        self.assertEqual(validate_state(valid), valid)
        for change in ({'version': 2}, {'kind': 'unknown'}, {'actions': valid['actions'] * 2},
                       {'actions': [{'id': 'a', 'label': 'OK', 'enabled': 'false'}]}):
            with self.assertRaises(ValueError):
                validate_state({**valid, **change})

    def test_dead_or_malformed_overlay_does_not_affect_auth(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'overlay'
            for value in ({'version': 1, 'pid': 999999999, 'state': 'authenticate'},
                          {'version': 1, 'pid': 1, 'state': 'invented'},
                          {'version': 2, 'pid': 1, 'state': 'enrollment', 'progress': 101}):
                path.write_text(json.dumps(value) + '\n')
                self.assertIsNone(read_overlay(path))
            link = Path(folder) / 'link'
            link.symlink_to(path)
            self.assertIsNone(read_overlay(link))


class InstallerTests(unittest.TestCase):
    def setUp(self):
        from gi.repository import Gio
        import gi
        spec = importlib.util.spec_from_file_location('t1_bridge_installer', ROOT / 'touchbar/install.py')
        self.installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.installer)
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        class Settings:
            values = {'enabled-extensions': [], 'disabled-extensions': []}
            def get_strv(self, key): return self.values[key]
            def set_strv(self, key, value): self.values[key] = value; return True
            def get_boolean(self, key): return False
        self.settings = Settings()
        self.patches = [patch.object(Path, 'home', return_value=self.home),
                        patch.dict(os.environ, {f'XDG_{k}_HOME': str(self.home / k.lower())
                            for k in ('CONFIG', 'DATA', 'STATE')}),
                        patch.object(Gio.Settings, 'new', return_value=self.settings),
                        patch.object(Gio.Settings, 'sync'), patch.object(gi, 'require_foreign'),
                        patch.object(self.installer, 'run', side_effect=self.run_fake)]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.tmp.cleanup()

    def run_fake(self, *args):
        from types import SimpleNamespace
        return SimpleNamespace(stdout='GNOME Shell 51.0\n' if args[0] == 'gnome-shell' else '',
                               returncode=0 if args[0] == 'gnome-shell' else 1)

    def command(self, action):
        with patch.object(sys, 'argv', ['install.py', action]):
            self.installer.main()

    def test_install_enable_disable_restores_existing_renderer(self):
        selection = self.home / 'config/t1bridge/renderer'
        selection.parent.mkdir(parents=True)
        selection.write_text('#!/bin/false\n')
        selection.chmod(0o751)
        self.command('install')
        assets = self.home / '.local/lib/macbook-t1-gnome-touchbar/assets'
        self.assertEqual((assets / 'Inter-Medium.otf').read_bytes(),
                         (ROOT / 'touchbar/assets/Inter-Medium.otf').read_bytes())
        self.command('enable')
        self.assertNotEqual(selection.read_text(), '#!/bin/false\n')
        self.command('disable')
        self.assertEqual(selection.read_text(), '#!/bin/false\n')
        self.assertEqual(selection.stat().st_mode & 0o777, 0o751)
        self.assertEqual(self.settings.values['enabled-extensions'], [])
        self.command('uninstall')
        self.assertFalse((self.home / '.local/lib/macbook-t1-gnome-touchbar/bridge.py').exists())
        self.assertFalse((assets / 'Inter-Medium.otf').exists())

    def test_restore_previous_renderer_symlink(self):
        selection = self.home / 'config/t1bridge/renderer'
        selection.parent.mkdir(parents=True)
        selection.symlink_to('/synthetic/previous-renderer')
        self.command('install')
        self.command('enable')
        self.command('disable')
        self.assertTrue(selection.is_symlink())
        self.assertEqual(os.readlink(selection), '/synthetic/previous-renderer')

    def test_modified_installed_file_is_preserved(self):
        self.command('install')
        target = self.home / '.local/lib/macbook-t1-gnome-touchbar/bridge.py'
        target.write_text('user modification')
        for action in ('install', 'uninstall'):
            with self.assertRaises(RuntimeError): self.command(action)
        self.assertEqual(target.read_text(), 'user modification')

    def test_later_renderer_choice_is_preserved(self):
        self.command('install')
        self.command('enable')
        selection = self.home / 'config/t1bridge/renderer'
        selection.write_text('new renderer')
        with self.assertRaises(RuntimeError): self.command('disable')
        self.assertEqual(selection.read_text(), 'new renderer')


class RendererTests(unittest.TestCase):
    def test_fingerprint_cancel_is_left_and_guidance_is_not_a_touch_target(self):
        import cairo
        from paint import draw, hit_test
        for width, height in ((2170, 60), (1085, 30)):
            for state in ('authenticate', 'approve', 'retry', 'enrollment'):
                scene = scene_for({}, {'state': state, 'pid': 42})
                surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
                targets = []
                for frame in (0, 2, 4):
                    boxes = draw(surface, scene, width, height, frame=frame)
                    targets.append(boxes)
                    self.assertEqual(hit_test(boxes, width * .04, height / 2), 'hardware:cancel')
                    self.assertIsNone(hit_test(boxes, width * .98, height / 2))
                self.assertEqual(targets[0], targets[1])
                self.assertEqual(targets[1], targets[2])

    def test_touch_targets_survive_context_and_panel_scaling(self):
        from paint import regions, hit_test
        scenes = [scene_for({}, features=0x3f), scene_for({}, fn=True)]
        scenes += [scene_for({'kind': kind, 'actions': [
            {'id': str(i), 'label': 'Action', 'enabled': i != 1} for i in range(12)]}, page=page)
            for kind in ('desktop', 'shell-dialog', 'app-dialog') for page in range(3)]
        for width, height in ((2170, 60), (1085, 30)):
            for scene in scenes:
                boxes = regions(scene, width, height)
                ordered = sorted(boxes, key=lambda box: box[0])
                for i, (x, y, w, h, button) in enumerate(ordered):
                    self.assertTrue(w > 0 and h > 0 and 0 <= x < x+w <= width and 0 <= y < y+h <= height)
                    self.assertEqual(hit_test(boxes, x+w/2, y+h/2), button.action if button.enabled else None)
                    if i:
                        previous_end = ordered[i-1][0] + ordered[i-1][2]
                        self.assertLess(previous_end, x)
                        self.assertIsNone(hit_test(boxes, (previous_end+x)/2, height/2))
            normal = {b.action: (x, y, w, h) for x, y, w, h, b in regions(scenes[0], width, height)}
            profile = {b.action: (x, y, w, h) for x, y, w, h, b in regions(scenes[2], width, height)}
            for key in ('key:1', 'audio:mute', 'audio:down', 'audio:up'):
                self.assertEqual(normal[key], profile[key])

    def test_bundled_font_and_glyphs_render_independently_of_desktop_dpi(self):
        import cairo
        from paint import draw, FONT_MAP
        from gi.repository import Pango, PangoCairo
        font_map = PangoCairo.FontMap.get_default()
        context = FONT_MAP.create_context()
        font = context.load_font(Pango.FontDescription('Inter Medium 13'))
        self.assertEqual(font.describe().get_family(), 'Inter')
        scene = scene_for({}, features=0x3f)
        resolution = font_map.get_resolution()
        frames = []
        try:
            for dpi in (96, 192):
                font_map.set_resolution(dpi)
                surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 2170, 60)
                draw(surface, scene, 2170, 60)
                frames.append(bytes(surface.get_data()))
        finally:
            font_map.set_resolution(resolution)
        self.assertEqual(frames[0], frames[1])


class RuntimeTests(unittest.TestCase):
    def test_fingerprint_fade_stops_and_left_cancel_survives_frames(self):
        import bridge
        import protocol
        from types import SimpleNamespace
        now, frames, actions = [0.0], [], []
        case = self

        class FakeHardware:
            width, height, features, minor = 2170, 60, 0x3f, 1

            def __init__(self):
                self.memory = bytearray(self.width * self.height * 4)
                self.busy = False

            def submit(self):
                case.assertFalse(self.busy)
                frames.append((now[0], bytes(self.memory)))
                self.busy, self.release_at = True, now[0] + .08

            def send(self, kind):
                actions.append(kind)

            def event(self):
                if self.busy:
                    case.assertEqual(bytes(self.memory), frames[-1][1])
                now[0] = round(now[0] + .04, 2)
                if self.busy and now[0] >= self.release_at:
                    self.busy = False
                if now[0] >= 2:
                    raise KeyboardInterrupt
                contacts = {0.4: [(0, 80, 30)], 0.52: [],
                            0.8: [(0, 2140, 30)], 0.92: []}
                if now[0] in contacts:
                    return (int(now[0] * 1_000_000), False, contacts[now[0]])

            def close(self):
                pass

        worker = SimpleNamespace(read=lambda: {'token': 'fixture', 'display': now[0] < 1.6})
        overlay = lambda: {'state': 'authenticate' if now[0] < 1.2 else 'success', 'pid': 42}
        with patch.object(protocol, 'Hardware', FakeHardware), \
                patch.object(bridge, 'read_overlay', side_effect=overlay), \
                patch.object(bridge.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(KeyboardInterrupt):
                bridge.render_session(worker)
        self.assertEqual(actions, [7], 'only the left Cancel tap should cancel')
        fade = [pixels for stamp, pixels in frames if stamp < .3]
        self.assertGreaterEqual(len(set(fade)), 2, 'guidance must visibly fade in')
        self.assertFalse(any(.2 < stamp < .4 or .65 < stamp < 1.2 for stamp, _ in frames),
                         'the completed fade must stop redrawing')
        self.assertEqual(sum(1.2 <= stamp < 1.6 for stamp, _ in frames), 1)
        self.assertEqual(sum(stamp >= 1.6 for stamp, _ in frames), 1)
        self.assertFalse(any(pixel & 0x00ffffff for pixel in memoryview(frames[-1][1]).cast('I')),
                         'display-off must remain blank (ignore the unused RGB24 byte)')

    def test_cold_full_renderer_startup(self):
        import subprocess
        for _ in range(3):
            result = subprocess.run([sys.executable, str(ROOT / 'tests/touchbar/runtime-startup.py')],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS cold renderer startup', result.stdout)


if __name__ == '__main__':
    unittest.main()
