#!/usr/bin/python3
# SPDX-License-Identifier: MIT
"""Typed playback/seek integration against a fake browser on a private bus."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'touchbar'))
from gi.repository import Gio, GLib
from media import MediaClient, PATH, PLAYER, video_token, media_title_key, window_media_title_keys

NAME = 'org.mpris.MediaPlayer2.firefox.touchbar_fixture'


def server(folder, browser):
    metadata = {'mpris:trackid': GLib.Variant('o', '/track/one'),
                'mpris:length': GLib.Variant('x', 120_000_000),
                'xesam:title': GLib.Variant('s', 'Fixture video')}
    props = {'PlaybackStatus': GLib.Variant('s', 'Playing'),
             'Metadata': GLib.Variant('a{sv}', metadata),
             'Position': GLib.Variant('x', 30_000_000), 'Rate': GLib.Variant('d', 1),
             **{key: GLib.Variant('b', True) for key in ('CanSeek', 'CanControl', 'CanPlay', 'CanPause')}}
    xml = '<node><interface name="org.mpris.MediaPlayer2.Player">' + ''.join(
        f'<property name="{key}" type="{value.get_type_string()}" access="read"/>'
        for key, value in props.items()) + '''
        <method name="Play"/><method name="Pause"/>
        <method name="SetPosition"><arg type="o" direction="in"/><arg type="x" direction="in"/></method>
        <method name="Seek"><arg type="x" direction="in"/></method>
        <method name="ChangeTrack"/>
        <signal name="Seeked"><arg type="x"/></signal>
        </interface></node>'''
    events = []
    actual_position = 30_000_000
    def method(connection, sender, path, interface, name, args, invocation):
        nonlocal actual_position
        values = args.unpack()
        events.append([name, list(values)])
        if name in ('Play', 'Pause'):
            props['PlaybackStatus'] = GLib.Variant('s', 'Playing' if name == 'Play' else 'Paused')
            props['Position'] = GLib.Variant('x', actual_position)
            props['Metadata'] = GLib.Variant('a{sv}', metadata)
        elif name in ('SetPosition', 'Seek'):
            actual_position = values[1] if name == 'SetPosition' else actual_position + values[0]
            # Reproduce Firefox 2065930: playback continues, property polls
            # lose both position and length, but Seeked reports the right time.
            props['Position'] = GLib.Variant('x', 0)
            props['Metadata'] = GLib.Variant('a{sv}', {k:v for k,v in metadata.items() if k != 'mpris:length'})
            connection.emit_signal(None, PATH, PLAYER, 'Seeked', GLib.Variant('(x)', (actual_position,)))
        elif name == 'ChangeTrack':
            # Firefox can reuse the same track path for a different video.
            props['Metadata'] = GLib.Variant('a{sv}', {
                'mpris:trackid': GLib.Variant('o', '/track/one'),
                'xesam:title': GLib.Variant('s', 'Different fixture video')})
            props['Position'] = GLib.Variant('x', 0)
        (folder / 'events.json').write_text(json.dumps(events))
        invocation.return_value(GLib.Variant('()', ()))
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    node = Gio.DBusNodeInfo.new_for_xml(xml)
    bus.register_object(PATH, node.interfaces[0], method, lambda *args: props[args[-1]], None)
    name = {'firefox':NAME,'chrome':'org.mpris.MediaPlayer2.chromium.touchbar_fixture',
            'vlc':'org.mpris.MediaPlayer2.vlc.touchbar_fixture'}[browser]
    Gio.bus_own_name_on_connection(bus, name, Gio.BusNameOwnerFlags.NONE,
        lambda *_: (folder / 'ready').touch(), None)
    GLib.MainLoop().run()


def exercise(browser='firefox'):
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        process = subprocess.Popen([sys.executable, __file__, '--server', tmp, browser])
        try:
            deadline = time.monotonic() + 4
            while not (folder / 'ready').exists():
                if time.monotonic() > deadline or process.poll() is not None:
                    raise RuntimeError('MPRIS fixture did not start')
                time.sleep(.02)
            client = MediaClient()
            focus = {'kind': 'desktop', 'app': {'firefox':'firefox.desktop','chrome':'google-chrome.desktop',
                      'vlc':'vlc.desktop'}[browser], 'pid': process.pid,
                      'media_title': window_media_title_keys('(1) Fixture video - YouTube — Mozilla Firefox')}
            video = client.read(focus)
            assert video and video['length'] == 120_000_000 and video['position'] == 30_000_000
            assert video['browser'] == ('player' if browser == 'vlc' else browser)
            # Chromium omits xesam:url. A source verified by the explicit
            # focused web document remains attached only to this exact identity.
            video['thumbnail_source'] = 'abcdefghijk'
            assert client.read(focus)['thumbnail_source'] == 'abcdefghijk'
            assert client.activate('video:toggle', video, lambda: True)
            assert client.read(focus)['status'] == 'Paused'
            assert client.activate('video:toggle', video, lambda: True)
            assert client.read(focus)['status'] == 'Playing'
            assert client.activate('video:seek:0.75', video, lambda: True)
            first = client.read(focus)
            assert first['length'] == 120_000_000 and 90_000_000 <= first['position'] < 91_000_000
            assert video_token({**focus, 'video': first}) == video_token({**focus, 'video': video})
            assert client.activate('video:seek:0.25', first, lambda: True)
            second = client.read(focus)
            assert second['length'] == 120_000_000 and 30_000_000 <= second['position'] < 31_000_000
            client.call(video['owner'], PATH, PLAYER, 'Seek', '(x)', (-10_000_000,))
            external = client.read(focus)
            assert 20_000_000 <= external['position'] < 21_000_000, external['position']
            if browser == 'firefox':
                # The media session continues in a background tab. Returning
                # restores its known duration even though MPRIS still omits it.
                assert client.read({**focus, 'media_title': window_media_title_keys('(1) New Tab - YouTube — Mozilla Firefox')}) is None
                restored = client.read(focus)
                assert restored['length'] == 120_000_000 and restored['position'] >= external['position']
                assert not client.read({**focus, 'media_title': None})
            assert not client.activate('video:forward', video, lambda: False)
            assert client.read({**focus, 'pid': process.pid + 1}) is None
            assert client.read({**focus, 'app': 'org.gnome.Nautilus.desktop'}) is None
            assert json.loads((folder / 'events.json').read_text()) == [
                ['Pause', []], ['Play', []], ['SetPosition', ['/track/one', 90_000_000]],
                ['SetPosition', ['/track/one', 30_000_000]], ['Seek', [-10_000_000]]]
            client.call(video['owner'], PATH, PLAYER, 'ChangeTrack')
            focus['media_title'] = media_title_key('Different fixture video - YouTube — Mozilla Firefox')
            changed = client.read(focus)
            assert changed['track'] == video['track'] and changed['identity'] != video['identity']
            assert changed['length'] == 0 and changed['position'] == 0
            assert changed['thumbnail_source'] is None
            assert not client.activate('video:seek:0.5', video, lambda: True)
            client.close()
        finally:
            process.terminate()
            process.wait(timeout=3)
    print('PASS browser MPRIS: repeated seeks with Firefox timing loss, Seeked, track/focus rejection')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--server']:
        server(Path(sys.argv[2]), sys.argv[3])
    else:
        exercise('vlc' if '--vlc' in sys.argv else 'chrome' if '--chrome' in sys.argv else 'firefox')
