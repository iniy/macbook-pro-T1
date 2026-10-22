// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {getMixerControl} from 'resource:///org/gnome/shell/ui/status/volume.js';

export default class VolumeIndicator extends Extension {
    enable() {
        // An installed trial helper must remain inert on the ordinary boot.
        const [ok, contents] = GLib.file_get_contents('/proc/cmdline');
        if (!ok || !new TextDecoder().decode(contents).trim().split(/\s+/)
            .includes('t1bridge.trial=1'))
            return;

        this._control = getMixerControl();
        this._controlSignals = [
            this._control.connect('default-sink-changed', () => this._bindSink()),
            this._control.connect('state-changed', () => this._bindSink()),
        ];
        this._bindSink();
    }

    _unbindSink() {
        if (this._timeoutId) {
            GLib.Source.remove(this._timeoutId);
            this._timeoutId = 0;
        }
        for (const id of this._sinkSignals ?? [])
            this._sink.disconnect(id);
        this._sinkSignals = [];
        this._sink = null;
        this._lastState = null;
    }

    _bindSink() {
        const sink = this._control.get_default_sink();
        if (sink === this._sink)
            return;
        this._unbindSink();
        this._sink = sink;
        if (!sink)
            return;

        // Connecting or changing the output device alone must not pop up an OSD.
        this._lastState = this._readState();
        this._sinkSignals = ['notify::volume', 'notify::is-muted'].map(signal =>
            sink.connect(signal, () => this._queueOSD()));
    }

    _readState() {
        return {volume: this._sink.volume, muted: this._sink.is_muted};
    }

    _queueOSD() {
        // GNOME and PipeWire can notify volume and mute together. Coalesce them.
        if (this._timeoutId)
            return;
        this._timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 30, () => {
            this._timeoutId = 0;
            const state = this._readState();
            const previous = this._lastState;
            this._lastState = state;
            if (state.volume === previous.volume && state.muted === previous.muted)
                return GLib.SOURCE_REMOVE;
            if (Main.sessionMode.isLocked || Main.sessionMode.isGreeter)
                return GLib.SOURCE_REMOVE;

            const normal = this._control.get_vol_max_norm();
            if (!(normal > 0))
                return GLib.SOURCE_REMOVE;
            const level = state.muted ? 0 : Math.max(0, state.volume / normal);
            const maxLevel = Math.max(1, this._control.get_vol_max_amplified() / normal);
            const name = level === 0 ? 'muted' : level <= 0.33 ? 'low'
                : level <= 0.66 ? 'medium' : 'high';
            const icon = new Gio.ThemedIcon({name: `audio-volume-${name}-symbolic`});
            Main.osdWindowManager.showAll(icon, null, Math.min(level, maxLevel),
                level > 1 ? maxLevel : 1);
            return GLib.SOURCE_REMOVE;
        });
    }

    disable() {
        this._unbindSink();
        for (const id of this._controlSignals ?? [])
            this._control.disconnect(id);
        this._controlSignals = [];
        this._control = null;
    }
}
