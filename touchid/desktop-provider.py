#!/usr/bin/python3
# SPDX-License-Identifier: MIT
"""Unprivileged T1Bridge desktop-provider v1 for PipeWire and MPRIS desktops."""
import os
import re
import subprocess
import sys


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=0.15).stdout


def audio_status():
    value = command('/usr/bin/wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@').strip()
    match = re.fullmatch(r'Volume: ([0-9]+[.][0-9]+)( \[MUTED\])?', value)
    if not match:
        raise ValueError('Unknown PipeWire volume response')
    return min(100, round(float(match[1]) * 100)), int(bool(match[2]))


def session():
    import dbus
    bus = dbus.SessionBus()
    return dbus, bus


def player(dbus, bus):
    broker = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus', introspect=False)
    names = broker.ListNames(dbus_interface='org.freedesktop.DBus', timeout=0.08)
    for name in sorted(n for n in names if n.startswith('org.mpris.MediaPlayer2.')):
        obj = bus.get_object(name, '/org/mpris/MediaPlayer2', introspect=False)
        props = dbus.Interface(obj, 'org.freedesktop.DBus.Properties')
        if props.Get('org.mpris.MediaPlayer2.Player', 'CanControl', timeout=0.08):
            return dbus.Interface(obj, 'org.mpris.MediaPlayer2.Player')
    return None


def status():
    caps, volume, muted = 0, '-', '-'
    try:
        volume, muted = audio_status()
        caps |= 1
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    display = None
    try:
        dbus, bus = session()
        try:
            if player(dbus, bus) is not None:
                caps |= 2
        except dbus.DBusException:
            pass
        try:
            obj = bus.get_object('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig', introspect=False)
            props = dbus.Interface(obj, 'org.freedesktop.DBus.Properties')
            power = int(props.Get('org.gnome.Mutter.DisplayConfig', 'PowerSaveMode', timeout=0.08))
            if power >= 0:
                display = int(power == 0)
                caps |= 16
        except dbus.DBusException:
            pass
    except (ImportError, OSError):
        pass
    suffix = '' if display is None else ' ' + str(display)
    print(f'T1BRIDGE-DESKTOP 1 {caps} {volume} {muted}{suffix}')


def main(args):
    if os.geteuid() == 0:
        return 1
    if len(args) < 2 or args[0] != 'v1':
        return 1
    op = args[1]
    if op == 'status' and len(args) == 2:
        status()
    elif op == 'set-volume' and len(args) == 3 and re.fullmatch(r'[0-9]{1,3}', args[2]) and int(args[2]) <= 100:
        command('/usr/bin/wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', args[2] + '%')
    elif op == 'toggle-mute' and len(args) == 2:
        command('/usr/bin/wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle')
    elif op in ('media-previous', 'media-play-pause', 'media-next') and len(args) == 2:
        dbus, bus = session()
        target = player(dbus, bus)
        if target is None:
            return 1
        method = {'media-previous': 'Previous', 'media-play-pause': 'PlayPause', 'media-next': 'Next'}[op]
        getattr(target, method)(timeout=0.15)
    else:
        return 1
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception:
        # Unavailable desktop actions withdraw capabilities; never affect auth.
        raise SystemExit(1)
