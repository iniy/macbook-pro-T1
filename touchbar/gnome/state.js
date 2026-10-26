// SPDX-License-Identifier: MIT
// Pure state/activation logic, also exercised outside GNOME by gjs tests.
export class ActionRegistry {
    constructor(epoch) {
        this.epoch = epoch;
        this.serial = 0;
        this.signature = '';
        this.actions = [];
        this.ids = new WeakMap();
        this.nextId = 0;
    }

    identity(object) {
        if (!object)
            return 0;
        if (!this.ids.has(object))
            this.ids.set(object, ++this.nextId);
        return this.ids.get(object);
    }

    publish(context, actions) {
        const descriptors = actions.map(a => ({
            id: String(a.id), label: String(a.label).slice(0, 120),
            enabled: a.enabled !== false, suggested: Boolean(a.suggested),
        }));
        const signature = JSON.stringify([context, descriptors]);
        if (signature !== this.signature) {
            this.signature = signature;
            this.serial++;
        }
        this.actions = actions;
        this.snapshot = {...context, version: 1,
            token: `${this.epoch}:${this.serial}`, actions: descriptors};
        return this.snapshot;
    }

    activate(token, id, refresh) {
        refresh(); // Revalidate the actual current dialog, not a cached scene.
        if (token !== this.snapshot.token)
            return false;
        const action = this.actions.find(a => String(a.id) === id);
        if (!action || action.enabled === false)
            return false;
        this.invalidate(); // One-shot even if the callback opens a nested dialog.
        action.run();
        return true;
    }

    invalidate() {
        this.serial++;
        this.signature = '';
        this.actions = [];
    }
}
