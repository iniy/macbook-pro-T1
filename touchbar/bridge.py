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

from model import Gesture, Scrub, scene_for
from motion import FrameBlend, TimelineMotion
from overlay import read_overlay
from volume import VolumePanel, VolumeWorker
from spectrum import SpectrumWorker


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
    from paint import animation_frame, draw, draw_visualizer, hit_test, seek_fraction, volume_fraction
    from protocol import Hardware
    if os.geteuid() == 0:
        raise RuntimeError('Run the renderer as the desktop user')
    hardware = Hardware()
    surface = cairo.ImageSurface.create_for_data(hardware.memory, cairo.FORMAT_RGB24,
                                               hardware.width, hardware.height, hardware.width * 4)
    gesture, fn, page = Gesture(), False, 0
    scrub = Scrub()
    motion, lens = TimelineMotion(), FrameBlend()
    spectrum = SpectrumWorker()
    volume = VolumePanel(VolumeWorker(on_output_change=spectrum.output_changed))
    next_video_frame = 0
    rendered, render_state, boxes, token, context = None, None, [], '', None
    stamp = None
    guidance_since = None
    try:
        while True:
            now = time.monotonic()
            state = worker.read()
            if state.get('token') != context:
                context, page = state.get('token'), 0
            overlay = read_overlay()
            base = scene_for(state, overlay, fn, hardware.features if hardware.minor else 0x27, page)
            scene = volume.scene(base, now)
            gesture.update_scene(scene.signature, now)
            scrub.update_scene(scene.signature, now)
            pressed = gesture.held[1] if gesture.held and not gesture.blocked else None
            fraction = scrub.held[1] if scrub.held and not scrub.blocked else None
            if fraction is not None:
                pressed = 'video:seek'
            if volume.slider.held and not volume.slider.blocked:
                pressed = 'volume:level'
            if volume.opener and not volume.opener['cancelled'] and not volume.opener['opened']:
                pressed = volume.opener['action']
            if scene.kind != 'fingerprint':
                guidance_since = None
            elif guidance_since is None:
                guidance_since = now
            frame = animation_frame(scene, now - guidance_since if guidance_since is not None else 0)
            position = motion.update(scene.context, scene.playback, fraction, now) if scene.playback else None
            filmstrip = scene.playback.get('filmstrip') if scene.playback else None
            lens_frames = None
            if filmstrip and scene.playback['length']:
                lens_frames = lens.update(filmstrip.revision,
                    filmstrip.frame_at(position/scene.playback['length']), now)
            # Passive playback changes less than a pixel between many refreshes.
            # Keep touch/dissolve animation at 60 Hz; skip visually redundant
            # playback frames, retaining quarter-pixel marker precision.
            progress = (round(position/scene.playback['length']*3200)
                        if scene.playback and scene.playback['length'] else 0)
            video_frame = (position // (1_000 if fraction is not None else 1_000_000),
                           progress, fraction is not None,
                           filmstrip.revision if filmstrip else None, lens_frames) if position is not None else None
            volume_frame = ((round(scene.volume['level'], 3), scene.volume['muted'])
                            if scene.kind == 'volume' else bool(scene.volume and scene.volume['muted']))
            levels = spectrum.read(scene.context if scene.kind == 'video'
                                   and scene.playback['status'] == 'Playing'
                                   and not (scene.volume and scene.volume['muted']) else None)
            next_render_state = (scene.signature, pressed, frame, video_frame, volume_frame, levels)
            due = not scene.playback or now >= next_video_frame
            if scene.playback and due and not hardware.busy:
                # Advance even when no pixels changed, avoiding a 1 ms busy loop.
                next_video_frame = now + 1/60
            if next_render_state != render_state and not hardware.busy and due:
                visual_fraction = position/scene.playback['length'] if fraction is not None and scene.playback['length'] else None
                if scene.kind == 'video' and render_state and next_render_state[:-1] == render_state[:-1]:
                    draw_visualizer(surface, levels, hardware.width, hardware.height)
                else:
                    boxes = draw(surface, scene, hardware.width, hardware.height, pressed, frame or 0,
                                 position, visual_fraction, lens_frames, levels)
                hardware.submit()
                rendered = scene.signature
                token = scene.context if scene.kind == 'video' else state.get('token', '')
                render_state = next_render_state
            if scene.playback:
                # Wake for animation at 60 Hz; release messages still govern
                # when the shared buffer may be drawn into again.
                moving = (scene.playback['status'] == 'Playing' or fraction is not None
                          or next_render_state != render_state or now-lens.started < .1)
                timeout = max(.001, min(.04, next_video_frame-time.monotonic())) if moving and not hardware.busy else .04
                event = hardware.event(timeout=timeout)
            else:
                event = hardware.event()
            if event is None:
                continue
            timestamp, next_fn, contacts = event
            # The service timestamps events relative to its own Instant origin,
            # not the host CLOCK_MONOTONIC epoch. Only compare stream ordering.
            if stamp is not None and timestamp <= stamp:
                gesture.blocked, gesture.held = True, None
                scrub.blocked, scrub.held = True, None
                volume.cancel_touch()
                continue
            stamp = timestamp
            if next_fn != fn:
                fn = next_fn
                gesture.blocked, gesture.held = bool(contacts), None
                scrub.blocked, scrub.held = bool(contacts), None
                volume.cancel_touch()
                continue
            hit = lambda x, y: hit_test(boxes, x, y) if rendered == scene.signature else None
            if volume.button_input(contacts, hit, base, time.monotonic(), hardware.width, hardware.height,
                                   not gesture.blocked and gesture.held is None and now-gesture.changed >= .3):
                gesture.blocked, gesture.held = bool(contacts), None
                scrub.blocked, scrub.held = bool(contacts), None
                continue
            seek = scrub.input(contacts, hit, lambda x, y: seek_fraction(boxes, x, y), time.monotonic())
            volume.input(contacts, hit, lambda x, y: volume_fraction(boxes, x, y), time.monotonic())
            button_hit = lambda x, y: None if hit(x, y) in ('video:seek', 'volume:level') else hit(x, y)
            action = gesture.input(contacts, button_hit, time.monotonic())
            if seek is not None:
                motion.released(seek, scene.playback, time.monotonic())
                worker.dispatch(f'video:seek:{seek:.6f}', token)
            if volume.action(action, base, time.monotonic()):
                continue
            if action == 'page:next':
                page += 1
            elif action:
                if action.startswith(('context:', 'audio:', 'media:', 'video:')):
                    worker.dispatch(action, token)
                else:
                    hardware_action(hardware, action)
    finally:
        spectrum.close()
        volume.close()
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
