// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import Clutter from 'gi://Clutter';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';
import {ActionRegistry} from './state.js';

const PATH = '/org/gnome/Shell/Extensions/T1TouchBar';
const XML = `<node><interface name="org.gnome.Shell.Extensions.T1TouchBar">
<method name="GetState"><arg type="s" direction="out"/></method>
<method name="Activate"><arg type="s" direction="in"/><arg type="s" direction="in"/>
<arg type="b" direction="out"/></method></interface></node>`;

// Fixed desktop shortcuts. No command strings or caller-supplied key sequences.
const PROFILES = [
    [/firefox|chromium|google-chrome|brave/i, [
        ['Back', ['Alt_L', 'Left']], ['Forward', ['Alt_L', 'Right']],
        ['Reload', ['Control_L', 'r']], ['New tab', ['Control_L', 't']],
        ['Find', ['Control_L', 'f']], ['Address', ['Control_L', 'l']]]],
    [/^(code|codium)(\.|$)|com\.visualstudio\.code/i, [
        ['Save', ['Control_L', 's']], ['Find', ['Control_L', 'f']],
        ['Commands', ['Control_L', 'Shift_L', 'p']],
        ['Terminal', ['Control_L', 'grave']], ['Files', ['Control_L', 'p']]]],
    [/terminal|org\.gnome\.Console|ptyxis|tilix|alacritty|kitty/i, [
        ['Copy', ['Control_L', 'Shift_L', 'c']], ['Paste', ['Control_L', 'Shift_L', 'v']],
        ['New tab', ['Control_L', 'Shift_L', 't']], ['Find', ['Control_L', 'Shift_L', 'f']]]],
    [/org\.gnome\.Nautilus/i, [
        ['Back', ['Alt_L', 'Left']], ['Forward', ['Alt_L', 'Right']],
        ['Search', ['Control_L', 'f']], ['New folder', ['Control_L', 'Shift_L', 'n']],
        ['New tab', ['Control_L', 't']]]],
];

export default class TouchBarBridge extends Extension {
    enable() {
        this._registry = new ActionRegistry(GLib.uuid_string_random());
        this._tracker = Shell.WindowTracker.get_default();
        this._focusSerial = 0;
        this._focusSignal = global.display.connect('notify::focus-window', () => {
            this._focusSerial++;
            this._registry.invalidate();
        });
        this._sessionSignal = Main.sessionMode.connect('updated', () => this._registry.invalidate());
        this._keyboard = global.stage.context.get_backend().get_default_seat()
            .create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        this._dbus = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._dbus.export(Gio.DBus.session, PATH);
    }

    _shortcut(keys) {
        const symbols = keys.map(k => Clutter[`KEY_${k}`]);
        if (symbols.some(s => !Number.isInteger(s)))
            return;
        const pressed = [];
        try {
            for (const symbol of symbols) {
                this._keyboard.notify_keyval(GLib.get_monotonic_time(), symbol, Clutter.KeyState.PRESSED);
                pressed.push(symbol);
            }
        } finally {
            for (const symbol of pressed.reverse())
                this._keyboard.notify_keyval(GLib.get_monotonic_time(), symbol, Clutter.KeyState.RELEASED);
        }
    }

    _state() {
        const r = this._registry;
        const window = global.display.focus_window;
        const app = window ? this._tracker.get_window_app(window) : null;
        const base = {kind: 'desktop', title: (app?.get_name() ?? 'Desktop').slice(0, 160),
            app: (app?.get_id() ?? '').slice(0, 200), pid: window?.get_pid() ?? 0,
            window: window ? String(window.get_stable_sequence()) : '',
            focus: this._focusSerial};
        if (Main.sessionMode.isLocked || Main.sessionMode.isGreeter)
            return r.publish({kind: 'locked', title: 'Locked'}, []);

        const top = Main.modalActorFocusStack.at(-1)?.actor;
        if (top) {
            // GNOME owns button creation, ordering, sensitivity, and callbacks.
            // Only the top modal is actionable, and only after its open animation.
            if (top instanceof ModalDialog.ModalDialog && top.state === ModalDialog.State.OPENED) {
                const buttons = top.buttonLayout.get_children().filter(b => b.visible && b.mapped);
                const title = top.contentLayout.get_children()
                    .find(c => typeof c.title === 'string')?.title ?? 'Confirmation';
                return r.publish({kind: 'shell-dialog', title: title.slice(0, 160), dialog: r.identity(top)},
                    buttons.slice(0, 12).map(b => ({
                        id: r.identity(b), label: b.label ?? '', enabled: b.reactive,
                        suggested: b.has_style_pseudo_class('default'),
                        run: () => b.emit('clicked', 1),
                    })));
            }
            return r.publish({kind: 'blocked', title: 'GNOME', modal: r.identity(top)}, []);
        }
        if (Main.overview.visible)
            return r.publish({kind: 'blocked', title: 'Overview'}, []);

        const tray = Main.messageTray;
        const notification = tray._notification;
        if (notification && !notification._destroyed && tray._banner?.mapped) {
            const actions = notification.actions.slice(0, 10).map(a => ({
                id: r.identity(a), label: a.label, run: () => a.activate(),
            }));
            actions.push({id: `dismiss-${r.identity(notification)}`, label: 'Dismiss',
                run: () => notification.destroy()});
            return r.publish({...base, kind: 'notification',
                title: notification.title.slice(0, 160), notification: r.identity(notification)}, actions);
        }
        const profile = PROFILES.find(([pattern]) => pattern.test(base.app));
        return r.publish(base, (profile?.[1] ?? []).map(([label, keys], i) => ({
            id: `shortcut-${i}`, label, run: () => this._shortcut(keys),
        })));
    }

    GetState() {
        return JSON.stringify(this._state());
    }

    Activate(token, id) {
        try {
            return this._registry.activate(token, id, () => this._state());
        } catch (error) {
            console.error('T1 Touch Bar action was unavailable');
            return false;
        }
    }

    disable() {
        this._dbus?.unexport();
        if (this._focusSignal)
            global.display.disconnect(this._focusSignal);
        if (this._sessionSignal)
            Main.sessionMode.disconnect(this._sessionSignal);
        this._focusSignal = this._sessionSignal = 0;
        this._registry = this._keyboard = this._dbus = this._tracker = null;
    }
}
