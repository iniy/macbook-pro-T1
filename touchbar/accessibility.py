# SPDX-License-Identifier: MIT
"""Bounded AT-SPI discovery of buttons in the focused application's dialog.

Only labels, roles and states are read. Entry contents, passwords, document text,
clipboard data, and background application trees are never inspected.
"""
import hashlib
import json
import time


class DialogReader:
    def __init__(self):
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi, GLib
        self.api = Atspi
        self.context = GLib.MainContext.default()
        Atspi.set_timeout(100, 100)
        self.targets = {}
        self.dialog = None
        self.negative, self.checked, self.dirty, self.active_bus = None, -10, True, None
        self.events = ('window:create','window:activate','window:destroy',
                       'object:children-changed','object:state-changed:modal')
        self.listener = Atspi.EventListener.new(self.invalidate)
        self.listening = all(self.listener.register(event) for event in self.events)

    def invalidate(self, event, *_):
        try:
            if self.active_bus is None or event.source.app.bus_name == self.active_bus:
                self.dirty = True
        except Exception:
            self.dirty = True

    def close(self):
        for event in self.events:
            self.listener.deregister(event)

    def cached_absence(self, focus):
        for _ in range(32):
            if not self.context.pending():
                break
            self.context.iteration(False)
        key = tuple(focus.get(k) for k in ('token','pid','window','focus'))
        return (self.listening and not self.dirty and self.negative == key
                and time.monotonic()-self.checked < 1)

    @staticmethod
    def identity(node):
        return f'{node.app.bus_name}:{node.path}'

    def states(self, node):
        node.clear_cache_single()
        return node.get_state_set()

    def scan(self, focus):
        self.targets, self.dialog = {}, None
        if focus.get('kind') not in ('desktop', 'notification') or focus.get('pid', 0) <= 0:
            return None
        if self.cached_absence(focus):
            return None
        self.dirty, self.negative = False, None
        api = self.api
        deadline = time.monotonic() + 0.30
        visited = 0

        def walk(root, depth=0):
            nonlocal visited
            if depth > 14 or visited >= 256 or time.monotonic() > deadline:
                raise TimeoutError('Accessibility traversal budget exceeded')
            visited += 1
            states = self.states(root)
            if states.contains(api.StateType.DEFUNCT) or not states.contains(api.StateType.SHOWING):
                return
            yield root, depth, states
            # Never enter editable text or document content to find buttons.
            if root.get_role() in (api.Role.ENTRY, api.Role.PASSWORD_TEXT, api.Role.DOCUMENT_WEB,
                                   api.Role.DOCUMENT_TEXT):
                return
            for i in range(min(root.get_child_count(), 64)):
                child = root.get_child_at_index(i)
                if child is not None:
                    yield from walk(child, depth + 1)

        try:
            desktop = api.get_desktop(0)
            apps = [desktop.get_child_at_index(i) for i in range(min(desktop.get_child_count(), 128))]
            apps = [app for app in apps if app and app.get_process_id() == focus['pid']]
            candidates = []
            for app in apps:
                self.active_bus = app.app.bus_name
                for i in range(min(app.get_child_count(), 64)):
                    top = app.get_child_at_index(i)
                    states = self.states(top)
                    if not states.contains(api.StateType.ACTIVE):
                        continue
                    nodes = list(walk(top))
                    dialogs = [(node, depth) for node, depth, states in nodes
                               if node.get_role() in (api.Role.DIALOG, api.Role.ALERT)
                               or states.contains(api.StateType.MODAL)]
                    if dialogs:
                        candidates.append(max(dialogs, key=lambda item: item[1])[0])
            if len(candidates) != 1:
                if not candidates:
                    self.negative = tuple(focus.get(k) for k in ('token','pid','window','focus'))
                    self.checked = time.monotonic()
                return None
            dialog = candidates[0]
            self.dialog = dialog
            buttons = []
            for node, _, states in walk(dialog):
                if node.get_role() not in (api.Role.BUTTON,):
                    continue
                action = node.get_action_iface()
                if action is None:
                    continue
                # Select only a semantic button activation, not an arbitrary action.
                indices = [i for i in range(min(action.get_n_actions(), 8))
                           if action.get_action_name(i).lower() in ('click', 'press', 'activate')]
                label = node.get_name().strip()
                if len(indices) != 1 or not label:
                    continue
                ident = self.identity(node)
                # GTK4 exports SENSITIVE for enabled widgets but does not set
                # the legacy ENABLED bit (gtk/a11y/gtkatspicontext.c).
                enabled = states.contains(api.StateType.SENSITIVE)
                buttons.append({'id': ident, 'label': label[:120], 'enabled': enabled})
                self.targets[ident] = (node, indices[0])
            if not buttons or len(buttons) > 12:
                self.targets = {}
                return None
            signature = [self.identity(dialog), focus.get('window'), focus.get('focus'),
                         dialog.get_name(), buttons]
            token = 'atspi:' + hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
            return {**focus, 'kind': 'app-dialog', 'title': dialog.get_name()[:160] or 'Confirmation',
                    'token': token, 'actions': buttons}
        except Exception:
            self.targets, self.dialog = {}, None
            return None

    def activate(self, token, ident, focus, guard=lambda: True):
        current = self.scan(focus)
        if not current or current['token'] != token:
            return False
        button = next((a for a in current['actions'] if a['id'] == ident), None)
        if not button or not button['enabled'] or not guard():
            return False
        target, index = self.targets[ident]
        self.targets = {}
        return bool(target.get_action_iface().do_action(index))
