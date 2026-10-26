#!/usr/bin/python3
# SPDX-License-Identifier: MIT
"""Real GNOME/GTK tests in a private bus, headless display and temporary home data.

Never invoke this script with --inside manually. The outer runner isolates the
session. End-session tests ONLY click Cancel, never any power/logout action.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'touchbar'))


def fixture(kind, result):
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, Adw, GLib
    app = Adw.Application(application_id='org.example.TouchbarFixture')
    def activate(app):
        win = Adw.ApplicationWindow(application=app, title='Touch Bar fixture',
                                   default_width=500, default_height=300)
        win.present()
        def response(dialog, value):
            Path(result).write_text(str(value))
            if kind == 'gtk':
                dialog.destroy()
        def show():
            if kind == 'gtk':
                dialog = Gtk.Dialog(title='Save changes?', transient_for=win, modal=True)
                dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
                dialog.add_button('Discard', Gtk.ResponseType.REJECT)
                dialog.add_button('Save', Gtk.ResponseType.ACCEPT).set_sensitive(False)
                dialog.connect('response', response)
                dialog.present()
            else:
                dialog = Adw.AlertDialog(heading='Save changes?', body='Synthetic test document')
                dialog.add_response('cancel', 'Cancel')
                dialog.add_response('discard', 'Discard')
                dialog.add_response('save', 'Save')
                dialog.set_response_enabled('save', False)
                dialog.set_close_response('cancel')
                dialog.connect('response', response)
                dialog.present(win)
            app.dialog = dialog
            return False
        GLib.timeout_add(500, show)
    app.connect('activate', activate)
    app.run([])


def eventually(callback, timeout=12):
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            value = callback()
            if value:
                return value
        except Exception as exc:
            error = exc
        time.sleep(.1)
    raise AssertionError(f'Timed out: {callback.__name__}') from error


def exercise(folder):
    from desktop import ShellClient
    from accessibility import DialogReader
    from gi.repository import Gio, GLib
    client = ShellClient()
    eventually(client.state)
    print('PASS GNOME 51 extension loads', flush=True)
    time.sleep(2)
    for mode, label in ((0, 'Log Out'), (1, 'Power Off'), (2, 'Restart')):
        client.bus.call_sync('org.gnome.Shell', '/org/gnome/SessionManager/EndSessionDialog',
            'org.gnome.SessionManager.EndSessionDialog', 'Open',
            GLib.Variant('(uuuao)', (mode, 0, 600, [])), None,
            Gio.DBusCallFlags.NONE, 3000, None)
        def shell_dialog():
            state = client.state()
            return state if state['kind'] == 'shell-dialog' else None
        state = eventually(shell_dialog)
        assert label in [a['label'] for a in state['actions']]
        cancel = next(a for a in state['actions'] if a['label'] == 'Cancel')
        assert client.activate(state['token'], cancel['id'])
        assert not client.activate(state['token'], cancel['id'])
        time.sleep(.4)
        print(f'PASS {label}: buttons, actual Cancel callback, replay rejection', flush=True)

    received = []
    subscription = client.bus.signal_subscribe('org.freedesktop.Notifications',
        'org.freedesktop.Notifications', 'ActionInvoked', '/org/freedesktop/Notifications',
        None, Gio.DBusSignalFlags.NONE, lambda *args: received.append(args[5].unpack()))
    client.bus.call_sync('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
        'org.freedesktop.Notifications', 'Notify',
        GLib.Variant('(susssasa{sv}i)', ('Touch Bar test', 0, '', 'Touch Bar test', '',
                                       ['open', 'Open test'], {}, 15000)),
        None, Gio.DBusCallFlags.NONE, 3000, None)
    def notification():
        state = client.state()
        return state if state['kind'] == 'notification' else None
    state = eventually(notification)
    action = next(a for a in state['actions'] if a['label'] == 'Open test')
    assert client.activate(state['token'], action['id'])
    def invoked():
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        return received
    assert eventually(invoked)[-1][1] == 'open'
    client.bus.signal_unsubscribe(subscription)
    print('PASS notification ActionInvoked reaches its sender', flush=True)

    registry = subprocess.Popen(['/usr/libexec/at-spi2-registryd'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        reader = DialogReader()
        for kind in ('gtk', 'adw'):
            result = folder / f'{kind}-response'
            app = subprocess.Popen([sys.executable, __file__, '--fixture', kind, str(result)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                def dialog():
                    state = reader.scan(client.state())
                    return state if state and state['kind'] == 'app-dialog' else None
                eventually(dialog)
                time.sleep(.4)  # Let focus settle after the new transient maps.
                state = eventually(dialog)
                save = next(a for a in state['actions'] if a['label'] == 'Save')
                assert not save['enabled']
                assert not reader.activate(state['token'], save['id'], client.state())
                cancel = next(a for a in state['actions'] if a['label'] == 'Cancel')
                assert not reader.activate(state['token'], cancel['id'], client.state(), lambda: False)
                # Match the renderer's fresh snapshot after the negative checks;
                # the transient window can finish changing focus during them.
                state = eventually(dialog)
                cancel = next(a for a in state['actions'] if a['label'] == 'Cancel')
                accepted = reader.activate(state['token'], cancel['id'], client.state())
                assert accepted, json.dumps({'expected': state, 'current': reader.scan(client.state())})
                eventually(result.exists)
                assert result.read_text() == ('-6' if kind == 'gtk' else 'cancel')
                assert not reader.activate(state['token'], cancel['id'], client.state())
                print(f'PASS {kind}: semantic Cancel, disabled Save, focus guard, stale dialog rejection', flush=True)
            finally:
                app.terminate()
                app.wait(timeout=5)
    finally:
        registry.terminate()
        registry.wait(timeout=5)


def inside(folder):
    if os.environ.get('T1_GNOME_TEST_PRIVATE') != str(folder) or os.environ.get('XDG_RUNTIME_DIR') != str(folder / 'runtime'):
        raise RuntimeError('This test requires its private session runner')
    with (folder / 'shell.log').open('w') as log:
        shell = subprocess.Popen(['gnome-shell', '--headless', '--wayland', '--no-x11',
            '--virtual-monitor', '1280x720', '--wayland-display', 't1-test', '--mode=t1-test'],
            stdout=log, stderr=subprocess.STDOUT)
        try:
            exercise(folder)
        except BaseException:
            print((folder / 'shell.log').read_text()[-6000:], file=sys.stderr)
            raise
        finally:
            shell.terminate()
            shell.wait(timeout=10)


def outer():
    with tempfile.TemporaryDirectory(prefix='t1-gnome-integration-') as name:
        folder = Path(name)
        for part in ('data', 'config', 'cache', 'state', 'runtime', 'system/gnome-shell/modes'):
            (folder / part).mkdir(parents=True, mode=0o700)
        uuid = 't1-gnome-bridge@local'
        shutil.copytree(ROOT / 'touchbar/gnome', folder / 'system/gnome-shell/extensions' / uuid)
        (folder / 'system/gnome-shell/modes/t1-test.json').write_text(json.dumps({
            'parentMode': 'user', 'enabledExtensions': [uuid]}))
        env = dict(os.environ)
        for key in ('DISPLAY', 'WAYLAND_SOCKET', 'AT_SPI_BUS_ADDRESS', 'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        env.update({f'XDG_{key}_HOME': str(folder / value) for key, value in
                    [('DATA', 'data'), ('CONFIG', 'config'), ('CACHE', 'cache'), ('STATE', 'state')]})
        env.update(XDG_RUNTIME_DIR=str(folder / 'runtime'), GSETTINGS_BACKEND='memory',
            GNOME_SHELL_SESSION_MODE='t1-test', GDK_BACKEND='wayland', GSK_RENDERER='cairo',
            WAYLAND_DISPLAY='t1-test', LC_ALL='C.UTF-8', T1_GNOME_TEST_PRIVATE=str(folder),
            XDG_DATA_DIRS=str(folder / 'system') + ':/usr/local/share:/usr/share')
        session = subprocess.Popen(['dbus-run-session', '--', sys.executable, __file__, '--inside', str(folder)],
                                   env=env, start_new_session=True)
        try:
            result = session.wait(timeout=100)
        finally:
            # Private bus activation can start helpers beyond the shell process.
            # Stop only this test's process group before removing its directories.
            try:
                os.killpg(session.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            session.wait(timeout=10)
        if result:
            raise SystemExit(result)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--fixture':
        fixture(sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 1 and sys.argv[1] == '--inside':
        inside(Path(sys.argv[2]))
    else:
        outer()
