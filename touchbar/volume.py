# SPDX-License-Identifier: MIT
"""On-demand volume slider; mixer calls never block Touch Bar input."""
import math
import os
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import replace

from model import Button, Scene, Scrub

HOLD_DELAY = .35
SLIDER_WIDTH = 480
SLIDER_TRAVEL = SLIDER_WIDTH * 276/502


def anchored_layout(x, level):
    # Put the thumb under the opening finger wherever the panel edge permits.
    # Reserve the dismiss target on the left, leaving the right edge for volume.
    left = max(100, min(2170-SLIDER_WIDTH-6,
                       x-SLIDER_WIDTH*113/502-level*SLIDER_TRAVEL))
    return {'left': left, 'width': SLIDER_WIDTH, 'close_left': left-94}


class VolumeWorker:
    def __init__(self, monitor=True, on_output_change=None):
        self.condition = threading.Condition()
        self.active = self.visible = self.stopped = self.subscribed = False
        self.commands = deque()
        self.state = None
        self.next_read = self.last_write = 0
        self.dirty = True
        self.thread = None
        self.monitor_enabled, self.monitor_thread, self.subscription = monitor, None, None
        self.stop_event = threading.Event()
        self.on_output_change = on_output_change

    def command(self, *args):
        result = subprocess.run(['/usr/bin/wpctl', *args], timeout=.4,
            capture_output=True, text=True, env={**os.environ, 'LC_ALL': 'C'})
        if result.returncode:
            raise RuntimeError('Mixer unavailable')
        return result.stdout.strip()

    def start_locked(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, daemon=True, name='touchbar-volume')
            self.thread.start()
            if self.monitor_enabled:
                self.monitor_thread = threading.Thread(target=self.monitor, daemon=True, name='touchbar-mixer-events')
                self.monitor_thread.start()

    def observe(self, visible):
        with self.condition:
            if visible == self.visible:
                return
            self.visible = visible
            if visible:
                self.start_locked()
                self.dirty, self.next_read = True, 0
            self.condition.notify_all()

    def open(self):
        with self.condition:
            self.active, self.dirty, self.next_read = True, True, 0
            self.start_locked()
            self.condition.notify_all()

    def hide(self):
        with self.condition:
            self.active = False
            self.condition.notify()

    def close(self):
        with self.condition:
            self.stopped = True
            self.stop_event.set()
            subscription = self.subscription
            self.condition.notify_all()
        if subscription and subscription.poll() is None:
            subscription.terminate()
        if self.thread:
            self.thread.join(timeout=1)
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)

    def read(self):
        with self.condition:
            return dict(self.state) if self.state else None

    def set_level(self, level):
        if not isinstance(level, (float, int)) or not math.isfinite(level) or not 0 <= level <= 1:
            return
        with self.condition:
            if self.active and self.state is not None:
                # Replace intermediate drag positions; always deliver the latest.
                request = ('level', round(level, 3))
                if self.commands and self.commands[-1][0] == 'level':
                    self.commands[-1] = request
                elif len(self.commands) < 32:
                    self.commands.append(request)
                self.condition.notify()

    def step(self, direction):
        if direction not in (-1, 1):
            return
        self.enqueue('step', direction)

    def toggle_mute(self):
        self.enqueue('mute', None)

    def enqueue(self, action, value):
        with self.condition:
            self.start_locked()
            if len(self.commands) < 32:
                self.commands.append((action, value))
            self.condition.notify()

    def source_changed(self):
        with self.condition:
            self.dirty = True
            self.next_read = time.monotonic()+.05
            self.condition.notify()
        if self.on_output_change:
            self.on_output_change()

    def monitor(self):
        while not self.stop_event.is_set():
            try:
                process = subprocess.Popen(['/usr/bin/pactl', 'subscribe'], stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, env={**os.environ, 'LC_ALL': 'C'})
            except OSError:
                return  # Bounded polling below remains available without pactl.
            with self.condition:
                self.subscription = process
                self.subscribed = True
                self.dirty, self.next_read = True, 0
                self.condition.notify()
                if self.stopped:
                    process.terminate()
            try:
                for line in process.stdout:
                    if ' on sink ' in line or ' on server ' in line:
                        self.source_changed()
            finally:
                process.stdout.close()
                process.wait()
                with self.condition:
                    self.subscription, self.subscribed = None, False
                    self.dirty, self.next_read = True, 0
                    self.condition.notify()
            self.stop_event.wait(2)

    def mixer_state(self):
        output = self.command('get-volume', '@DEFAULT_AUDIO_SINK@')
        match = re.fullmatch(r'Volume:\s+(\d+(?:\.\d+)?)(\s+\[MUTED\])?', output)
        if not match:
            raise ValueError('Invalid mixer volume')
        return {'level': min(1.0, float(match[1])), 'muted': bool(match[2])}

    def run(self):
        while True:
            with self.condition:
                if self.stopped:
                    return
                now = time.monotonic()
                write_at = self.last_write+.05 if self.commands and self.commands[0][0] == 'level' else now
                read_at = max(self.next_read, self.last_write+.1)
                watching = (self.active or self.visible) and (self.dirty or not self.subscribed)
                if self.commands and now >= write_at:
                    action, value = self.commands.popleft()
                elif watching and now >= read_at:
                    action, value = 'read', None
                    self.dirty = False
                else:
                    deadlines = [write_at] if self.commands else []
                    if watching:
                        deadlines.append(read_at)
                    self.condition.wait(max(.001, min(deadlines)-now) if deadlines else None)
                    continue
                state = dict(self.state) if self.state else None
            failed = False
            try:
                if action == 'level':
                    self.command('set-volume', '-l', '1.0', '@DEFAULT_AUDIO_SINK@', f'{value:.3f}')
                    if state and state['muted'] and value > 0:
                        self.command('set-mute', '@DEFAULT_AUDIO_SINK@', '0')
                        state['muted'] = False
                    state = {**(state or {'muted': False}), 'level': value}
                elif action == 'mute':
                    self.command('set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle')
                    state = self.mixer_state()
                elif action == 'step':
                    limit = ('-l', '1.0') if value > 0 else ()
                    self.command('set-volume', *limit, '@DEFAULT_AUDIO_SINK@', '5%+' if value > 0 else '5%-')
                    state = self.mixer_state()
                else:
                    state = self.mixer_state()
            except (OSError, subprocess.SubprocessError, ValueError, RuntimeError):
                # Retain the last confirmed mute state through a transient
                # mixer failure instead of falsely showing an unmuted button.
                failed = True
            with self.condition:
                self.state = state
                now = time.monotonic()
                if action != 'read':
                    self.last_write = now
                if failed:
                    self.dirty = True
                self.next_read = now + (.1 if self.dirty else 2)
                if failed:
                    self.next_read = now+2


class VolumePanel:
    def __init__(self, worker=None):
        self.worker = worker or VolumeWorker()
        self.context = None
        self.slider = Scrub('volume:level')
        self.preview = None
        self.changed = self.touched = 0
        self.opener = None
        self.layout = None

    def hide(self):
        self.context, self.preview = None, None
        self.opener = None
        self.layout = None
        self.slider = Scrub('volume:level')
        self.worker.hide()

    def scene(self, base, now):
        available = any(b.action == 'audio:up' for b in base.buttons)
        self.worker.observe(available)
        if self.opener and (base.context != self.opener['context'] or not available):
            self.hide()
        if self.opener and not self.opener['cancelled'] and now-self.opener['at'] >= HOLD_DELAY:
            self.expand(now)
        state = self.worker.read()
        normal = replace(base, volume=state) if state else base
        if self.context is None:
            return normal
        if base.context != self.context or not available:
            self.hide()
            return normal
        level = dict(state) if state else {'level': 0, 'muted': False}
        level.update(self.layout)
        if self.preview is not None and (self.slider.held or self.opener or now-self.changed < .8):
            level['level'] = self.preview
        buttons = (
            Button('Volume', 'volume:level', state is not None),
            Button('Close volume', 'volume:close', icon='close'))
        result = Scene('', buttons, 'volume:' + base.context, 'volume', volume=level)
        self.slider.update_scene(result.signature, now)
        return result

    def expand(self, now):
        start = self.opener
        if start['opened']:
            return
        state = self.worker.read()
        start['level'] = state['level'] if state else None
        start['opened'] = True
        self.context, self.preview, self.touched = start['context'], None, now
        self.layout = anchored_layout(start['x']*2170/start['width'], start['level'] or 0)
        self.slider = Scrub('volume:level')
        self.worker.open()
        self.drag_opener(now)

    def drag_opener(self, now):
        start = self.opener
        if not start['opened'] or start['cancelled']:
            return
        state = self.worker.read()
        if start['level'] is None and state:
            start['level'] = state['level']
        if start['moved'] and start['level'] is not None:
            delta = (start['last_x']-start['x'])*2170/start['width']
            value = max(0, min(1, start['level'] + delta/SLIDER_TRAVEL))
            if value != self.preview:
                self.preview, self.changed = value, now
                self.worker.set_level(value)

    def action(self, action, base, now):
        if action in ('audio:down', 'audio:up'):
            self.worker.step(1 if action == 'audio:up' else -1)
        elif action == 'volume:close':
            self.hide()
        elif action == 'audio:mute':
            self.worker.toggle_mute()
            self.touched, self.preview = now, None
        else:
            return False
        return True

    def button_input(self, contacts, hit, base, now, width, height, can_open):
        # Wait before expanding so ordinary taps retain their 5% step. Once
        # expanded, a continuous hold-slide-release changes volume relatively.
        if self.opener is None:
            if self.context is not None or not can_open or len(contacts) != 1:
                return False
            ident, x, y = contacts[0]
            action = hit(x, y)
            if action not in ('audio:down', 'audio:up'):
                return False
            self.opener = {'id': ident, 'action': action, 'context': base.context,
                           'x': x, 'last_x': x, 'width': width, 'at': now,
                           'level': None, 'opened': False,
                           'moved': False, 'cancelled': False}
            return True
        start = self.opener
        if base.context != start['context'] or not any(b.action == 'audio:up' for b in base.buttons):
            start['cancelled'] = True
        if not contacts:
            duration = now-start['at']
            if not start['cancelled'] and HOLD_DELAY <= duration <= 10:
                self.expand(now)
            elif not start['cancelled'] and not start['moved'] and .06 <= duration < HOLD_DELAY:
                self.worker.step(1 if start['action'] == 'audio:up' else -1)
            dismiss = start['moved'] or start['cancelled']
            self.opener = None
            if dismiss:
                self.hide()
            return True
        if (len(contacts) != 1 or contacts[0][0] != start['id']
                or not 0 <= contacts[0][2] < height or now-start['at'] > 10):
            start['cancelled'] = True
        if start['cancelled']:
            return True
        start['last_x'] = contacts[0][1]
        delta = contacts[0][1]-start['x']
        if abs(delta) >= 8*width/2170:
            start['moved'] = True
        if now-start['at'] >= HOLD_DELAY:
            self.expand(now)
            self.drag_opener(now)
        return True

    def input(self, contacts, hit, fraction, now):
        if self.context is None:
            return
        released = self.slider.input(contacts, hit, fraction, now)
        value = self.slider.held[1] if self.slider.held and not self.slider.blocked else released
        if contacts or released is not None:
            self.touched = now
        if value is not None and value != self.preview:
            self.preview, self.changed = value, now
            self.worker.set_level(value)

    def cancel_touch(self):
        self.slider.blocked, self.slider.held = True, None
        if self.opener:
            self.opener['cancelled'] = True

    def close(self):
        self.worker.close()
