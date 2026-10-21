#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reopen the Apple playback PCM after wake without disconnecting clients."""
import json
from pathlib import Path
import pwd
import stat
import subprocess


def sessions():
    users = json.loads(subprocess.check_output(
        ['/usr/bin/loginctl', 'list-users', '--json=short'], text=True, timeout=10))
    for user in users:
        uid = user['uid']
        if not isinstance(uid, int) or uid <= 0:
            continue
        account = pwd.getpwuid(uid)
        runtime = Path('/run/user') / str(uid)
        socket = runtime / 'pulse/native'
        try:
            directory = runtime.lstat()
            endpoint = socket.lstat()
        except FileNotFoundError:
            continue  # No PulseAudio-compatible desktop server for this user.
        if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != uid
                or not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid != uid):
            raise RuntimeError('Unexpected audio session ownership for UID ' + str(uid))
        yield (account, runtime, (endpoint.st_dev, endpoint.st_ino))


def connected(session):
    _, runtime, identity = session
    try:
        endpoint = (runtime / 'pulse/native').stat()
    except FileNotFoundError:
        return False
    return (endpoint.st_dev, endpoint.st_ino) == identity


def pactl(session, *args):
    account, runtime, _ = session
    # Never run session programs as root or inherit its PulseAudio credentials.
    command = ['/usr/sbin/runuser', '-u', account.pw_name, '--', '/usr/bin/env', '-i',
               'PATH=/usr/bin:/bin', 'HOME=' + account.pw_dir,
               'XDG_RUNTIME_DIR=' + str(runtime),
               'PULSE_SERVER=unix:' + str(runtime / 'pulse/native'), '/usr/bin/pactl', *args]
    return subprocess.check_output(command, text=True, timeout=10, stderr=subprocess.PIPE)


def internal_sink(item):
    props = item.get('properties', {})
    return (props.get('media.class') == 'Audio/Sink'
            and props.get('device.bus_path') == 'pci-0000:00:1f.3'
            and 'HDA:10138409,106b3600,' in props.get('alsa.components', '')
            and props.get('alsa.name') == 'CS8409/CS42L83 Analog'
            and isinstance(item.get('name'), str)
            and item['name'].startswith('alsa_output.'))


def sinks(session):
    return [item for item in json.loads(pactl(session, '-f', 'json', 'list', 'sinks'))
            if internal_sink(item)]


def reopen_playback(record):
    """Cycle playback after systemd-sleep has thawed the desktop sessions.

    The custom CS8409 driver's prepare counter survives suspend while the HDA
    converter stream IDs are cleared. Closing the PCM runs cleanup and resets
    that counter. A fresh prepare then programs both speaker converters again.
    PipeWire can reopen immediately when a client is running. That is desired
    here, after wake. The client connection and software volume stay intact.
    """
    failures = []
    for session in sessions():
        try:
            for sink in sinks(session):
                if sink['state'] == 'SUSPENDED':
                    continue
                name = sink['name']
                try:
                    pactl(session, 'suspend-sink', name, '1')
                finally:
                    # Undo even if the first command took effect then timed out.
                    # A logged-out/restarted server no longer has our suspension.
                    if connected(session) and any(item['name'] == name for item in sinks(session)):
                        pactl(session, 'suspend-sink', name, '0')
                record('Reopened internal playback for UID ' + str(session[0].pw_uid))
        except Exception as error:
            failures.append(str(error))
    if failures:
        raise RuntimeError('Could not recover internal playback: ' + '; '.join(failures))
