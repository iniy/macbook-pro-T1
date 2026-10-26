# SPDX-License-Identifier: MIT
"""Focused-player MPRIS playback, using typed calls to one exact bus owner."""
import hashlib
import json
import math
import re
import time
import unicodedata
from thumbnails import youtube_id

BROWSERS = re.compile(r'firefox|chromium|google-chrome|brave|vivaldi|epiphany|falkon|opera', re.I)
FIREFOX = re.compile(r'firefox', re.I)
VIDEO_PLAYERS = re.compile(r'vlc|mpv|celluloid|totem|showtime|haruna|smplayer|parole|dragonplayer|kodi', re.I)
PLAYER = 'org.mpris.MediaPlayer2.Player'
PATH = '/org/mpris/MediaPlayer2'
NO_TRACK = '/org/mpris/MediaPlayer2/TrackList/NoTrack'
FIREFOX_SUFFIX = re.compile(r'\s+[—–-]\s+(?:Mozilla\s+)?Firefox(?:\s+\(Private Browsing\))?$', re.I)


def media_title_key(title):
    """Compare media and active-window captions without retaining their text."""
    if not isinstance(title, str) or not title.strip() or len(title) > 8192:
        return None
    title = ' '.join(unicodedata.normalize('NFKC', title).split())
    title = FIREFOX_SUFFIX.sub('', title)
    title = re.sub(r'\s+[—–-]\s+(?:YouTube|Vimeo|Dailymotion|Twitch)$', '', title, flags=re.I)
    return hashlib.sha256(title.casefold().encode()).hexdigest() if title else None


def window_media_title_keys(caption):
    """Keep the exact title match and an optional YouTube notification-count match."""
    key = media_title_key(caption)
    if key is None:
        return ()
    caption = FIREFOX_SUFFIX.sub('', ' '.join(unicodedata.normalize('NFKC', caption).split()))
    if re.search(r'\s+[—–-]\s+YouTube$', caption, re.I):
        unbadged = re.sub(r'^\([0-9]+\)\s+', '', caption)
        alternate = media_title_key(unbadged)
        if alternate and alternate != key:
            # Only the window caption has this decoration. Preserve the exact
            # candidate too: a video's actual title may itself start with (1).
            return (key, alternate)
    return (key,)


def matches_focused_tab(focus, video):
    titles = focus.get('media_title') or ()
    if isinstance(titles, str):
        titles = (titles,)
    return (not FIREFOX.search(focus.get('app', '')) or
            bool(video.get('title_hash') and video['title_hash'] in titles))


def video_token(state):
    video = state['video']
    identity = [state.get('token'), state.get('media_title'), video['owner'], video['track'], video.get('identity')]
    return 'video:' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def position_at(video, now):
    position = video['position']
    if video['status'] == 'Playing':
        position += max(0, now - video['sampled_at']) * video['rate'] * 1_000_000
    length = video['length']
    return int(max(0, min(position, length) if length > 0 else position))


class MediaClient:
    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.candidates, self.scanned, self.pid, self.selected = [], -10, None, None
        self.samples, self.seek_points, self.last_tracks = {}, {}, {}
        # This worker has no GLib main loop. Deliver seek notifications into a
        # private context and drain it alongside the bounded property polls.
        self.context = GLib.MainContext.new()
        self.context.push_thread_default()
        try:
            self.subscription = self.bus.signal_subscribe(None, PLAYER, 'Seeked', PATH,
                None, Gio.DBusSignalFlags.NONE, self.seeked)
        finally:
            self.context.pop_thread_default()

    def close(self):
        self.bus.signal_unsubscribe(self.subscription)

    def drain(self):
        for _ in range(32):
            if not self.context.pending():
                break
            self.context.iteration(False)

    def seeked(self, connection, owner, path, interface, signal, parameters):
        key = self.last_tracks.get(owner)
        position = parameters.unpack()[0]
        if key in self.samples and type(position) is int and 0 <= position < 2**63:
            self.remember_seek(self.samples[key], position)

    def remember_seek(self, video, position):
        key = (video['owner'], video.get('identity', video['track']))
        self.seek_points[key] = {**video, 'position': max(0, position),
                                 'sampled_at': time.monotonic()}

    def call(self, owner, path, interface, method, signature=None, values=()):
        args = self.GLib.Variant(signature, values) if signature else None
        return self.bus.call_sync(owner, path, interface, method, args, None,
            self.Gio.DBusCallFlags.NO_AUTO_START, 150, None).unpack()

    def properties(self, owner, *, firefox=False):
        props = self.call(owner, PATH, 'org.freedesktop.DBus.Properties',
                          'GetAll', '(s)', (PLAYER,))[0]
        self.drain()
        metadata = props.get('Metadata', {})
        track = metadata.get('mpris:trackid')
        if (not isinstance(track, str) or not self.GLib.Variant.is_object_path(track)
                or track == NO_TRACK or props.get('CanControl') is not True
                or props.get('PlaybackStatus') not in ('Playing', 'Paused')):
            key = self.last_tracks.pop(owner, None)
            self.samples.pop(key, None)
            self.seek_points.pop(key, None)
            return None
        # Firefox may reuse its track object path for different videos. Include
        # stable media metadata in a private hash so cached timing cannot leak
        # into another video; titles/URLs are never logged or persisted.
        identity = hashlib.sha256(json.dumps([track, *[metadata.get(k) for k in
            ('xesam:url', 'xesam:title', 'xesam:artist', 'xesam:album')]], sort_keys=True).encode()).hexdigest()
        key = (owner, identity)
        prior_key = self.last_tracks.get(owner)
        if prior_key != key:
            # Returning to a previously played video starts a new timing
            # session; an old zero-position fallback must not resume it.
            self.samples.pop(prior_key, None)
            self.seek_points.pop(prior_key, None)
        previous = self.samples.get(key)
        position = props.get('Position')
        if position is None:
            position = self.call(owner, PATH, 'org.freedesktop.DBus.Properties',
                                 'Get', '(ss)', (PLAYER, 'Position'))[0]
        length, rate = metadata.get('mpris:length', 0), props.get('Rate', 1.0)
        if type(position) is not int or position < 0 or position >= 2**63:
            return None
        if type(length) is not int or not 0 < length < 2**63:
            length = 0
        if previous and ('mpris:length' not in metadata or firefox and length == 0):
            length = previous['length']
        if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 < rate <= 16:
            rate = 1.0
        now = time.monotonic()
        anchor = self.seek_points.get(key)
        if anchor and position == 0:
            # Firefox bug 2065930: after a seek, Position can stay zero and
            # mpris:length can disappear until pause/play. Seeked remains valid.
            position = position_at(anchor, now)
        elif (firefox and position == 0 and previous
                and props['PlaybackStatus'] == 'Playing'):
            # Firefox can lose its position before the first Seeked signal,
            # including at video startup. A new zero on every property poll
            # must not rewind our running clock. Keep the same-track sample;
            # an explicit Seeked (including zero) still takes precedence above.
            position = position_at(previous, now)
        result = {'owner': owner, 'track': track, 'identity': identity, 'status': props['PlaybackStatus'],
                'thumbnail_source': youtube_id(metadata.get('xesam:url', '')) or (previous or {}).get('thumbnail_source'),
                'title_hash': media_title_key(metadata.get('xesam:title')),
                'position': position, 'length': length, 'rate': rate,
                'sampled_at': now, 'can_seek': props.get('CanSeek') is True,
                'can_play': props.get('CanPlay') is True, 'can_pause': props.get('CanPause') is True}
        url = metadata.get('xesam:url','')
        result['video_hint'] = (isinstance(url,str) and len(url) <= 8192 and bool(re.search(
            r'\.(mp4|m4v|mkv|webm|mov|avi|ogv|mpeg|mpg|m2ts|mts|vob|ts)(?:[?#].*)?$',url,re.I)))
        if anchor:
            self.seek_points[key] = result
        self.samples[key], self.last_tracks[owner] = result, key
        while len(self.samples) > 8:
            expired = next(iter(self.samples))
            del self.samples[expired]
            self.seek_points.pop(expired, None)
        return result

    def read(self, focus):
        if (focus.get('kind') != 'desktop' or focus.get('display') is False
                or focus.get('pid', 0) <= 0):
            return None
        try:
            now, pid = time.monotonic(), focus['pid']
            if pid != self.pid or now - self.scanned >= 1:
                self.pid, self.scanned, self.candidates = pid, now, []
                names = self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                  'org.freedesktop.DBus', 'ListNames')[0]
                deadline = now + .3
                for name in sorted(n for n in names if n.startswith('org.mpris.MediaPlayer2.'))[:32]:
                    if time.monotonic() > deadline:
                        break
                    try:
                        owner = self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                            'org.freedesktop.DBus', 'GetNameOwner', '(s)', (name,))[0]
                        owner_pid = self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                            'org.freedesktop.DBus', 'GetConnectionUnixProcessID', '(s)', (owner,))[0]
                        if owner_pid == pid:
                            self.candidates.append(owner)
                    except Exception:
                        continue
            videos = []
            for owner in self.candidates:
                try:
                    video = self.properties(owner, firefox=bool(re.search('firefox', focus.get('app', ''), re.I)))
                    if video and (BROWSERS.search(focus.get('app','')) or
                                  VIDEO_PLAYERS.search(focus.get('app','')) or video['video_hint']):
                        if matches_focused_tab(focus, video):
                            videos.append(video)
                except Exception:
                    continue
            if not videos:
                self.selected = None
                return None
            video = next((v for v in videos if v['owner'] == self.selected), None)
            video = video or next((v for v in videos if v['status'] == 'Playing'), videos[0])
            self.selected = video['owner']
            video['browser'] = ('firefox' if re.search('firefox', focus['app'], re.I) else
                                'chrome' if BROWSERS.search(focus['app']) else 'player')
            return video
        except Exception:
            return None

    def activate(self, action, expected, guard):
        # Resolve neither a different player nor a replacement bus owner here.
        # SetPosition also carries the track ID, so the player rejects stale seeks.
        current = self.properties(expected['owner'], firefox=expected.get('browser') == 'firefox')
        if (not current or current['track'] != expected['track']
                or current.get('identity') != expected.get('identity')):
            return False
        if action == 'video:toggle':
            playing = current['status'] == 'Playing'
            if not current['can_pause' if playing else 'can_play']:
                return False
            method, signature, values = 'Pause' if playing else 'Play', None, ()
        elif action in ('video:backward', 'video:forward') or action.startswith('video:seek:'):
            if not current['can_seek']:
                return False
            if action.startswith('video:seek:'):
                fraction = float(action.removeprefix('video:seek:'))
                if not math.isfinite(fraction) or not 0 <= fraction <= 1 or not current['length']:
                    return False
                target = round(current['length'] * fraction)
            else:
                offset = -10_000_000 if action == 'video:backward' else 10_000_000
                target = current['position'] + offset
                if not current['length']:
                    if not guard():
                        return False
                    self.call(current['owner'], PATH, PLAYER, 'Seek', '(x)', (offset,))
                    self.remember_seek(current, max(0, current['position'] + offset))
                    return True
            target = max(0, min(target, current['length'] - 1))
            method, signature, values = 'SetPosition', '(ox)', (current['track'], target)
        else:
            return False
        if not guard():
            return False
        self.call(current['owner'], PATH, PLAYER, method, signature, values)
        if method == 'SetPosition':
            self.remember_seek(current, target)
        return True
