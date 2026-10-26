#!/usr/bin/python3
# SPDX-License-Identifier: MIT
"""Cold-process renderer test with real GI/Cairo and a simulated hardware session."""
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'touchbar'))
import bridge
import desktop
import accessibility
import protocol

threads = []
failures = []
frames = []
closed = []
activated = []


class Client:
    def __init__(self):
        # These are the same namespaces the real desktop thread imports. Running
        # this in a fresh process catches lazy-override initialization failures.
        from gi.repository import Gio, GLib
        assert hasattr(GLib, 'Idle')
        assert hasattr(Gio, 'bus_get_sync')
        threads.append(threading.get_ident())

    def state(self):
        return {'version': 1, 'kind': 'shell-dialog', 'title': 'Startup fixture',
                'token': 'fixture', 'actions': [{'id': 'cancel', 'label': 'Cancel'}]}

    def activate(self, token, ident):
        activated.append((token, ident))
        return True

    def display_on(self):
        return True


class Reader:
    def __init__(self):
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        assert hasattr(Atspi, 'Accessible')

    def scan(self, focus):
        return None


class Hardware:
    def __init__(self):
        self.width, self.height, self.features, self.minor = 2170, 60, 0x3f, 1
        self.memory = bytearray(self.width * self.height * 4)
        self.busy = False
        self.start = time.monotonic()
        self.phase = 0

    def submit(self):
        assert any(self.memory), 'renderer did not draw a frame'
        frames.append(bytes(self.memory))

    def event(self):
        elapsed = time.monotonic() - self.start
        if elapsed > 1.2:
            raise KeyboardInterrupt
        time.sleep(.01)
        # Service-relative timestamps deliberately have a different epoch from
        # time.monotonic_ns(). Valid taps must still reach the GNOME callback.
        if self.phase == 0 and elapsed > .65:
            self.phase = 1
            return (5_000_000, False, [(0, 1085, 30)])
        if self.phase == 1 and elapsed > .80:
            self.phase = 2
            return (155_000_000, False, [])
        return None

    def close(self):
        closed.append(True)


threading.excepthook = lambda args: failures.append(args.exc_type.__name__)
with patch.object(desktop, 'ShellClient', Client), patch.object(accessibility, 'DialogReader', Reader), \
        patch.object(protocol, 'Hardware', Hardware):
    try:
        bridge.render()
    except KeyboardInterrupt:
        pass
assert not failures, failures
assert threads and threads[0] != threading.get_ident(), 'desktop worker did not start'
assert frames and closed, 'full render and cleanup path did not complete'
assert len(frames) >= 3 and frames[-1] == frames[-3] != frames[-2], 'press highlight did not clear on release'
assert activated == [('fixture', 'cancel')], 'service-relative tap did not activate exactly once'
print('PASS cold renderer startup: GI imports, desktop worker, Cairo frame, service-relative touch, cleanup')
