# SPDX-License-Identifier: MIT
"""GNOME bridge client; blocking desktop APIs stay off the rendering thread."""
import json
import queue
import subprocess
import threading
import time

BUS = 'org.gnome.Shell'
PATH = '/org/gnome/Shell/Extensions/T1TouchBar'
INTERFACE = 'org.gnome.Shell.Extensions.T1TouchBar'


def validate_state(state):
    if not isinstance(state, dict) or state.get('version') != 1:
        raise ValueError('Unsupported GNOME bridge version')
    if state.get('kind') not in ('desktop', 'shell-dialog', 'notification', 'blocked', 'locked'):
        raise ValueError('Unknown GNOME context')
    if not isinstance(state.get('token'), str) or len(state['token']) > 200:
        raise ValueError('Invalid context token')
    actions = state.get('actions')
    if not isinstance(actions, list) or len(actions) > 12:
        raise ValueError('Invalid actions')
    ids = set()
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError('Invalid action')
        for field in ('id', 'label'):
            if not isinstance(action.get(field), str) or len(action[field]) > 200:
                raise ValueError('Invalid action field')
        if action['id'] in ids or type(action.get('enabled', True)) is not bool:
            raise ValueError('Duplicate action or invalid sensitivity')
        ids.add(action['id'])
    return state


class ShellClient:
    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(self, method, signature, values, reply):
        result = self.bus.call_sync(BUS, PATH, INTERFACE, method,
            self.GLib.Variant(signature, values), self.GLib.VariantType.new(reply),
            self.Gio.DBusCallFlags.NO_AUTO_START, 350, None)
        return result.unpack()[0]

    def state(self):
        data = self.call('GetState', '()', (), '(s)')
        if len(data) > 16384:
            raise ValueError('Oversized GNOME state')
        return validate_state(json.loads(data))

    def activate(self, token, ident):
        return self.call('Activate', '(ss)', (token, ident), '(b)')

    def display_on(self):
        try:
            result = self.bus.call_sync('org.gnome.Mutter.DisplayConfig',
                '/org/gnome/Mutter/DisplayConfig', 'org.freedesktop.DBus.Properties', 'Get',
                self.GLib.Variant('(ss)', ('org.gnome.Mutter.DisplayConfig', 'PowerSaveMode')),
                None, self.Gio.DBusCallFlags.NO_AUTO_START, 200, None)
            return result.unpack()[0] <= 0
        except Exception:
            return True


class DesktopWorker:
    def __init__(self):
        self.queue = queue.Queue(maxsize=1)
        self.lock = threading.Lock()
        self.snapshot = {'title': 'GNOME bridge unavailable', 'actions': []}
        self.updated = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def read(self):
        with self.lock:
            if time.monotonic() - self.updated > 1.5:
                return {'title': 'GNOME bridge unavailable', 'actions': []}
            return dict(self.snapshot)

    def dispatch(self, action, token):
        try:
            self.queue.put_nowait((action, token))
        except queue.Full:
            pass

    def run(self):
        from accessibility import DialogReader
        from media import FIREFOX, MediaClient, video_token
        from thumbnails import ThumbnailWorker
        client, reader = ShellClient(), DialogReader()
        media = MediaClient()
        thumbnails = ThumbnailWorker()
        consumed = None
        while not self.stop.is_set():
            started = time.monotonic()
            try:
                focus = client.state()
                snapshot = reader.scan(focus) or focus
                if snapshot.get('kind') == 'desktop' and FIREFOX.search(snapshot.get('app', '')):
                    snapshot = {**snapshot, 'media_title': reader.media_title(focus)}
                snapshot['display'] = client.display_on()
                video = media.read(snapshot)
                if video:
                    # Chrome keeps the requested basic controls, with no
                    # capture, browser scanning or thumbnail work.
                    filmstrip = thumbnails.read(video if video.get('browser')=='firefox'
                                                else {'length':0,'can_seek':False})
                    if filmstrip:
                        video = {**video, 'filmstrip': filmstrip}
                    snapshot = {**snapshot, 'video': video}
                else:
                    thumbnails.read({'length': 0, 'can_seek': False})
            except Exception:
                focus = None
                snapshot = {'title': 'GNOME bridge unavailable', 'actions': [],
                            'display': client.display_on()}
            with self.lock:
                self.snapshot, self.updated = snapshot, time.monotonic()
            try:
                action, token = self.queue.get_nowait()
            except queue.Empty:
                action = None
            try:
                if action and action.startswith('video:'):
                    if snapshot.get('video') and token == video_token(snapshot):
                        def still_playing_in_focus():
                            latest = client.state()
                            return (latest.get('kind') == 'desktop' and client.display_on()
                                and all(latest.get(key) == snapshot.get(key)
                                        for key in ('token', 'app', 'pid', 'window', 'focus'))
                                and reader.scan(latest) is None
                                and (not FIREFOX.search(latest.get('app', '')) or
                                     reader.media_title(latest) == snapshot.get('media_title')))
                        media.activate(action, snapshot['video'], still_playing_in_focus)
                elif action and action.startswith('context:') and token != consumed:
                    ident = action.removeprefix('context:')
                    if snapshot.get('token') == token and snapshot.get('display', True):
                        consumed = token
                        current = client.state()
                        if (FIREFOX.search(snapshot.get('app', '')) and
                                reader.media_title(current) != snapshot.get('media_title')):
                            raise ValueError('Browser tab changed')
                        if token.startswith('atspi:'):
                            def still_focused():
                                latest = client.state()
                                return latest['kind'] in ('desktop', 'notification') and all(
                                    latest.get(key) == current.get(key) for key in ('pid', 'window', 'focus'))
                            reader.activate(token, ident, current, still_focused)
                        else:
                            client.activate(token, ident)
                elif action:
                    self.control(action)
            except Exception:
                # No retries: a timeout may mean the action already happened.
                pass
            self.stop.wait(max(0, 0.15 - (time.monotonic() - started)))
        media.close()
        thumbnails.close()
        reader.close()

    @staticmethod
    def control(action):
        if action.startswith('audio:'):
            options = {'audio:mute': ['set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle'],
                       'audio:down': ['set-volume', '@DEFAULT_AUDIO_SINK@', '5%-'],
                       'audio:up': ['set-volume', '-l', '1.0', '@DEFAULT_AUDIO_SINK@', '5%+']}
            if action in options:
                subprocess.run(['/usr/bin/wpctl', *options[action]], timeout=0.4,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        elif action in ('media:previous', 'media:play-pause', 'media:next'):
            subprocess.run(['/usr/local/libexec/macbook-t1-touchid-desktop', 'v1',
                            action.replace(':', '-')], timeout=0.5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
