# SPDX-License-Identifier: MIT
"""Scene selection and release-to-activate gesture state, independent of I/O."""
from dataclasses import dataclass, field
import hashlib
import json
import re
from media import video_token


ICON_PROFILE_APPS = re.compile(r'firefox|chromium|google-chrome|brave|org\.gnome\.Nautilus', re.I)
PROFILE_ICONS = {'Back': 'back', 'Forward': 'forward', 'Reload': 'reload',
                 'New tab': 'new-tab', 'Find': 'search', 'Search': 'search',
                 'Address': 'address', 'New folder': 'new-folder'}


def icon_profile(state):
    # Only decorate the existing fixed browser/Files shortcuts. Dialog and
    # notification labels belong to their applications and must stay textual.
    return state.get('kind') == 'desktop' and ICON_PROFILE_APPS.search(state.get('app', '')) is not None


def profile_icon(state, action):
    if icon_profile(state) and re.fullmatch(r'shortcut-\d+', action['id']):
        return PROFILE_ICONS.get(action['label'], '')
    return ''


@dataclass(frozen=True)
class Button:
    label: str
    action: str
    enabled: bool = True
    suggested: bool = False
    icon: str = ''


@dataclass(frozen=True)
class Scene:
    title: str
    buttons: tuple
    context: str
    kind: str = 'controls'
    progress: int = -1
    playback: dict = field(default=None, repr=False, compare=False)
    volume: dict = field(default=None, repr=False, compare=False)

    @property
    def signature(self):
        return hashlib.sha256(repr(self).encode()).hexdigest()


def scene_for(state, overlay=None, fn=False, features=0x27, page=0):
    if state.get('display') is False:
        return Scene('', (), 'blank', 'blank')
    if overlay:
        titles = {'authenticate': 'Touch ID — touch the sensor', 'approve': 'Touch ID — approve',
                  'retry': 'Touch ID — try again', 'success': 'Touch ID — verified',
                  'enrollment': 'Touch ID — touch and lift your finger'}
        buttons = () if overlay['state'] == 'success' else (Button('Cancel', 'hardware:cancel'),)
        return Scene(titles[overlay['state']], buttons, json.dumps(overlay, sort_keys=True),
                     'fingerprint', overlay.get('progress', -1))
    if fn:
        return Scene('', tuple([Button('esc', 'key:1')] + [Button(f'F{i}', f'key:{58+i if i <= 10 else 76+i}')
                      for i in range(1, 13)]), 'fn', 'function')
    kind = state.get('kind', 'controls')
    dialog = kind in ('shell-dialog', 'app-dialog')
    controls = [Button('Mute', 'audio:mute'), Button('Vol −', 'audio:down'), Button('Vol +', 'audio:up')]
    if kind == 'desktop' and state.get('video'):
        video = state['video']
        playing = video['status'] == 'Playing'
        buttons = (Button('esc', 'key:1'),
                   Button('Pause' if playing else 'Play', 'video:toggle',
                          video['can_pause' if playing else 'can_play'], icon='pause' if playing else 'play'),
                   Button('Seek', 'video:seek', video['can_seek'] and video['length'] > 0), *controls)
        return Scene('', buttons, video_token(state), 'video', playback=video)
    buttons = [] if dialog else [Button('esc', 'key:1')]
    actions = state.get('actions', [])
    if actions:
        pages = (len(actions) + 4) // 5
        page %= pages
        buttons += [Button(a['label'], 'context:' + a['id'], a.get('enabled', True),
                           a.get('suggested', False), profile_icon(state, a))
                    for a in actions[page*5:page*5+5]]
        if pages > 1:
            buttons.append(Button(f'{page+1}/{pages} ›', 'page:next',
                                  icon='more' if icon_profile(state) else ''))
    elif not dialog and state.get('kind') not in ('blocked', 'locked'):
        if features & 8:
            buttons += [Button('Light −', 'light:down'), Button('Light +', 'light:up')]
        if features & 16:
            buttons += [Button('Keys −', 'backlight:down'), Button('Keys +', 'backlight:up')]
        buttons += [Button('Previous', 'media:previous'), Button('Play/Pause', 'media:play-pause'),
                    Button('Next', 'media:next')]
    if not dialog:
        buttons += controls
    context = state.get('token', 'unavailable') + f':{page}'
    if state.get('media_title'):
        context += ':tab:' + json.dumps(state['media_title'])
    title = state.get('title', 'Touch Bar') if actions or kind not in ('desktop', 'controls') else ''
    return Scene(title, tuple(buttons), context, kind)


class Gesture:
    """A context change, drag, multi-touch, long hold or reconnect cancels a tap."""
    def __init__(self):
        self.signature = None
        self.changed = 0
        self.held = None
        self.blocked = False

    def update_scene(self, signature, now):
        if signature != self.signature:
            self.signature, self.changed = signature, now
            self.blocked = self.blocked or self.held is not None
            self.held = None

    def input(self, contacts, hit, now):
        if not contacts:
            held, self.held = self.held, None
            blocked, self.blocked = self.blocked, False
            if held and not blocked and 0.06 <= now - held[2] <= 5:
                return held[1]
            return None
        if self.blocked:
            return None
        if len(contacts) != 1 or now - self.changed < 0.3:
            self.blocked, self.held = True, None
            return None
        ident, x, y = contacts[0]
        target = hit(x, y)
        if self.held is None:
            if target is None:
                self.blocked = True
            else:
                self.held = (ident, target, now)
        elif ident != self.held[0] or target != self.held[1] or now - self.held[2] > 5:
            self.blocked, self.held = True, None
        return None


class Scrub:
    """Only a touch that starts on the timeline can become a video scrub."""
    def __init__(self, action='video:seek'):
        self.action = action
        self.signature, self.changed, self.held, self.blocked = None, 0, None, False

    def update_scene(self, signature, now):
        if signature != self.signature:
            self.signature, self.changed = signature, now
            self.blocked = self.blocked or self.held is not None
            self.held = None

    def input(self, contacts, hit, fraction, now):
        if not contacts:
            held, self.held = self.held, None
            blocked, self.blocked = self.blocked, False
            if held and not blocked and .06 <= now - held[2] <= 10:
                return held[1]
            return None
        if self.blocked:
            return None
        if len(contacts) != 1 or now - self.changed < .3:
            self.blocked, self.held = True, None
            return None
        ident, x, y = contacts[0]
        if (hit(x, y) != self.action or
                self.held and (ident != self.held[0] or now - self.held[2] > 10)):
            self.blocked, self.held = True, None
            return None
        self.held = (ident, fraction(x, y), self.held[2] if self.held else now)
        return None
