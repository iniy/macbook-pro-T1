#!/usr/bin/python3
# SPDX-License-Identifier: MIT
"""T1Bridge selected renderer for the GNOME desktop."""
import argparse
import os
from pathlib import Path
import signal
import struct
import sys
import time

from model import Gesture, scene_for
from overlay import read_overlay


def hardware_action(hardware, action):
    if action.startswith('key:'):
        key = int(action.split(':')[1])
        if key not in (1, *range(59, 69), 87, 88):
            return
        hardware.send(4, struct.pack('<B3x4H', 1, key, 0, 0, 0))
    elif action == 'hardware:cancel':
        hardware.send(7)
    elif action in ('light:up', 'light:down') and hardware.minor >= 1 and hardware.features & 8:
        hardware.send(8, bytes([int(action.endswith(':up'))]))
    elif action in ('backlight:up', 'backlight:down') and hardware.minor >= 1 and hardware.features & 16:
        hardware.send(9, bytes([int(action.endswith(':up'))]))


def render_session(worker):
    import cairo
    from paint import draw, hit_test
    from protocol import Hardware
    if os.geteuid() == 0:
        raise RuntimeError('Run the renderer as the desktop user')
    hardware = Hardware()
    surface = cairo.ImageSurface.create_for_data(hardware.memory, cairo.FORMAT_RGB24,
                                               hardware.width, hardware.height, hardware.width * 4)
    gesture, fn, page = Gesture(), False, 0
    rendered, render_state, boxes, token, context = None, None, [], '', None
    stamp = None
    try:
        while True:
            now = time.monotonic()
            state = worker.read()
            if state.get('token') != context:
                context, page = state.get('token'), 0
            overlay = read_overlay()
            scene = scene_for(state, overlay, fn, hardware.features if hardware.minor else 0x27, page)
            gesture.update_scene(scene.signature, now)
            pressed = gesture.held[1] if gesture.held and not gesture.blocked else None
            if (scene.signature, pressed) != render_state and not hardware.busy:
                boxes = draw(surface, scene, hardware.width, hardware.height, pressed)
                hardware.submit()
                rendered, token = scene.signature, state.get('token', '')
                render_state = (scene.signature, pressed)
            event = hardware.event()
            if event is None:
                continue
            timestamp, next_fn, contacts = event
            # The service timestamps events relative to its own Instant origin,
            # not the host CLOCK_MONOTONIC epoch. Only compare stream ordering.
            if stamp is not None and timestamp <= stamp:
                gesture.blocked, gesture.held = True, None
                continue
            stamp = timestamp
            if next_fn != fn:
                fn = next_fn
                gesture.blocked, gesture.held = bool(contacts), None
                continue
            hit = lambda x, y: hit_test(boxes, x, y) if rendered == scene.signature else None
            action = gesture.input(contacts, hit, time.monotonic())
            if action == 'page:next':
                page += 1
            elif action:
                if action.startswith(('context:', 'audio:', 'media:')):
                    worker.dispatch(action, token)
                else:
                    hardware_action(hardware, action)
    finally:
        surface.finish()
        del surface
        hardware.close()


def render():
    initialize_runtime()
    from desktop import DesktopWorker
    from protocol import ProtocolError
    worker = DesktopWorker()
    try:
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                render_session(worker)
                return
            except (OSError, ProtocolError):
                if time.monotonic() - started > 10:
                    attempt = 0
                if attempt >= 3:
                    raise
                # Allow the existing service to recover after a device/sleep
                # transition, without changing USB configuration or root units.
                time.sleep(0.4 * (attempt + 1))
                attempt += 1
    finally:
        worker.stop.set()


def initialize_runtime():
    # PyGObject builds shared override modules lazily. Concurrent first imports
    # of Pango on the renderer thread and Gio/AT-SPI on the worker can expose a
    # half-initialized GLib override (e.g. missing GLib.Idle). Load every runtime
    # namespace serially before starting any desktop worker.
    import gi
    gi.require_foreign('cairo')
    for namespace, version in (('Gio', '2.0'), ('GLib', '2.0'), ('Atspi', '2.0'),
                               ('Pango', '1.0'), ('PangoCairo', '1.0')):
        gi.require_version(namespace, version)
        __import__('gi.repository', fromlist=[namespace])
    import paint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check the GNOME bridge without taking the display')
    parser.add_argument('--preview', type=Path, help='Write a sample confirmation strip PNG without hardware')
    args = parser.parse_args()
    if args.check:
        from desktop import ShellClient
        state = ShellClient().state()
        print(f"GNOME bridge v{state['version']}: {state['kind']}, {len(state['actions'])} actions")
        return
    if args.preview:
        import cairo
        from paint import draw
        state = {'kind': 'shell-dialog', 'title': 'Power Off', 'token': 'preview',
                 'actions': [{'id': 'cancel', 'label': 'Cancel'},
                             {'id': 'power', 'label': 'Power Off'}]}
        surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 2170, 60)
        draw(surface, scene_for(state), 2170, 60)
        surface.write_to_png(str(args.preview))
        return
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    render()


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        # The T1Bridge launcher supervises this process and restores its built-in
        # renderer on exit. Never log desktop contents or exception payloads.
        print(f'GNOME Touch Bar bridge unavailable ({type(error).__name__}); '
              'returning to the built-in renderer.', file=sys.stderr)
        sys.exit(1)
