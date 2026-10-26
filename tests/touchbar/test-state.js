// Run with: gjs -m tests/touchbar/test-state.js
import {ActionRegistry} from '../../touchbar/gnome/state.js';
let count = 0;
function assert(value, message) { if (!value) throw new Error(message); }
const registry = new ActionRegistry('fixture');
const button = {};
let enabled = true;
let context = {kind: 'shell-dialog', dialog: 1};
const refresh = () => registry.publish(context, [{id: registry.identity(button), label: 'Cancel',
    enabled, run: () => count++}]);
let state = refresh();
assert(refresh().token === state.token, 'stable scene must retain token');
assert(registry.activate(state.token, state.actions[0].id, refresh), 'fresh action');
assert(count === 1, 'one callback');
assert(!registry.activate(state.token, state.actions[0].id, refresh), 'replay rejected');
state = refresh(); enabled = false;
assert(!registry.activate(state.token, state.actions[0].id, refresh), 'disabled before tap');
enabled = true; state = refresh(); context = {kind: 'shell-dialog', dialog: 2};
assert(!registry.activate(state.token, state.actions[0].id, refresh), 'replaced dialog rejected');
state = refresh(); registry.invalidate();
assert(!registry.activate(state.token, state.actions[0].id, refresh), 'focus away and back rejected');
assert(count === 1, 'stale actions never invoked');
print('PASS GNOME action identity, sensitivity, replay and context validation');
