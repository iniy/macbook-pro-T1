#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check readiness ordering and recovery failures without fingerprint hardware."""
from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('fingerprint_wake', ROOT / 'touchid/fingerprint_resume.py')
WAKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WAKE)


class FingerprintResume(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.keybag = self.root / 'synthetic-keybag'
        self.keybag.write_bytes(b'synthetic state must remain untouched')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.enabled = self.stack.enter_context(patch.object(WAKE, 'enabled', return_value=True))
        self.stack.enter_context(patch.object(WAKE, 'KEYBAG', self.keybag))
        self.stack.enter_context(patch.object(WAKE.os, 'geteuid', return_value=0))
        self.states = {WAKE.DAEMON: 'inactive', WAKE.BROKER: 'active', WAKE.RELAY: 'failed'}
        self.events = []
        self.real_control = WAKE.control
        self.query = self.stack.enter_context(patch.object(WAKE, 'state', side_effect=self.state))
        self.command = self.stack.enter_context(patch.object(WAKE, 'control', side_effect=self.control))

    def state(self, unit):
        self.events.append(('query', unit))
        return self.states[unit]

    def control(self, action, unit, **kwargs):
        self.events.append((action, unit))
        self.states[unit] = 'inactive' if action == 'stop' else 'active'

    def recover(self):
        WAKE.recover(lambda _: None)

    def test_clients_stop_before_relay_restart_and_readiness_is_checked(self):
        self.recover()
        self.assertEqual(self.events, [('query', WAKE.DAEMON), ('stop', WAKE.DAEMON),
                         ('stop', WAKE.BROKER), ('restart', WAKE.RELAY), ('query', WAKE.RELAY)])
        self.assertEqual(self.states[WAKE.DAEMON], 'inactive')
        self.assertEqual(self.keybag.read_bytes(), b'synthetic state must remain untouched')

    def test_active_daemon_is_restored_only_after_relay_ready(self):
        self.states[WAKE.DAEMON] = 'active'
        self.recover()
        self.assertEqual(self.events[-2:], [('query', WAKE.RELAY), ('start', WAKE.DAEMON)])

    def test_already_active_relay_is_reopened_to_discard_stale_connection(self):
        self.states[WAKE.RELAY] = 'active'
        self.recover()
        self.assertIn(('restart', WAKE.RELAY), self.events)

    def test_each_control_failure_restores_existing_daemon_without_claiming_success(self):
        for failed in (('stop', WAKE.DAEMON), ('stop', WAKE.BROKER), ('restart', WAKE.RELAY)):
            self.states[WAKE.DAEMON] = 'active'
            self.events.clear()
            def fail(action, unit, **kwargs):
                self.control(action, unit, **kwargs)
                if (action, unit) == failed:
                    raise subprocess.TimeoutExpired(['systemctl', action, unit], 6)
            self.command.side_effect = fail
            with self.assertRaises(subprocess.TimeoutExpired):
                self.recover()
            self.assertEqual(self.events[-1], ('start', WAKE.DAEMON))

    def test_skipped_relay_start_is_not_treated_as_ready(self):
        self.states[WAKE.DAEMON] = 'active'
        def skipped(action, unit, **kwargs):
            self.control(action, unit, **kwargs)
            if unit == WAKE.RELAY:
                self.states[unit] = 'inactive'
        self.command.side_effect = skipped
        with self.assertRaisesRegex(RuntimeError, 'readiness'):
            self.recover()
        self.assertEqual(self.events[-1], ('start', WAKE.DAEMON))

    def test_no_keybag_or_unsupported_boot_never_changes_services(self):
        self.enabled.return_value = False
        self.recover()
        self.enabled.return_value = True
        self.keybag.unlink()
        self.recover()
        self.assertEqual(self.events, [])
        self.assertFalse(self.keybag.exists())

    def test_concurrent_daemon_transition_is_preserved(self):
        self.states[WAKE.DAEMON] = 'deactivating'
        with self.assertRaisesRegex(RuntimeError, 'changing state'):
            self.recover()
        self.command.assert_not_called()

    def test_only_post_suspend_runs_recovery(self):
        with patch.object(WAKE, 'recover') as recover, patch.dict(os.environ, {}, clear=True):
            for args in (['pre', 'suspend'], ['post', 'hibernate'], ['post', 'suspend-then-hibernate']):
                self.assertEqual(WAKE.main(args), 0)
            recover.assert_not_called()
            self.assertEqual(WAKE.main(['post', 'suspend']), 0)
            recover.assert_called_once()

    def test_unit_commands_have_timeouts_and_propagate_failure(self):
        with patch.object(WAKE.subprocess, 'run', side_effect=subprocess.TimeoutExpired([], 6)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.real_control('stop', WAKE.DAEMON)
            self.assertEqual(run.call_args.kwargs['timeout'], 6)


if __name__ == '__main__':
    unittest.main()
