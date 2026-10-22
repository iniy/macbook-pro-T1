#!/usr/bin/env python3
"""Check that the convenience installer selects existing components without resets."""
import argparse
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
spec = importlib.util.spec_from_file_location('one_shot', ROOT / 'lib/one_shot.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OneShot(unittest.TestCase):
    def test_default_routes_all_hardware_and_desktop_without_live_reset(self):
        args = argparse.Namespace(no_install_deps=False, no_sleep=False, no_wifi=False, no_desktop=False,
                                  wifi_profile=None, activate_wifi=False)
        commands = [cmd for _, cmd in module.commands(args)]
        self.assertEqual([Path(cmd[1]).name for cmd in commands if cmd[0] == 'bash'],
                         ['install-ubuntu.sh', 'manage.sh', 'install-5ghz.sh', 'configure.sh'])
        self.assertEqual(commands[0][2], 'preflight')
        self.assertEqual(commands[2][-1], 'install')
        self.assertEqual(commands[3][0], 'systemd-inhibit')
        self.assertIn('--what=sleep:shutdown', commands[3])
        self.assertEqual(commands[3][-3:], ['python3', str(ROOT / 'sleep/manage-resume.py'), 'install'])
        self.assertTrue(all(flag in commands[1] for flag in ['--touchbar', '--audio', '--camera']))
        self.assertFalse(any(flag in cmd for cmd in commands for flag in ['--activate', '--update', '--uninstall']))

    def test_plan_never_runs_root_installation(self):
        with patch.object(sys, 'argv', ['one_shot.py', '--plan']), \
             patch.object(module, 'host') as host, patch.object(module.subprocess, 'run') as run, \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(module.main(), 0)
            host.assert_not_called()
            run.assert_not_called()
            self.assertIn('install-5ghz.sh', output.getvalue())
            self.assertIn('manage-resume.py', output.getvalue())

    def test_no_sleep_skips_sleep_but_retains_touchid(self):
        args = argparse.Namespace(no_install_deps=False, no_sleep=True, no_wifi=False, no_desktop=False,
                                  wifi_profile=None, activate_wifi=False)
        commands = [cmd for _, cmd in module.commands(args)]
        self.assertFalse(any('sleep/manage' in word for cmd in commands for word in cmd))
        self.assertEqual(commands[0][2], 'preflight')
        self.assertIn('install', commands[-1])
        self.assertIn(str(ROOT / 'touchid/manage.py'), commands[-1])

    def test_persistent_touchid_is_in_default_flow_without_dependency_or_desktop_changes(self):
        args = argparse.Namespace(no_install_deps=True, no_sleep=True, no_wifi=True,
                                  no_desktop=True, wifi_profile=None, activate_wifi=False)
        commands = [cmd for _, cmd in module.commands(args)]
        self.assertEqual(commands[-1][-4:], ['python3', str(ROOT / 'touchid/manage.py'), 'install', '--no-desktop'])
        self.assertEqual(commands[-1][0], 'systemd-inhibit')
        self.assertNotIn('--install-deps', commands[-1])

    def test_no_touchid_preserves_baseline_flow(self):
        with patch.object(sys, 'argv', ['one_shot.py', '--plan', '--no-touchid']), \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(module.main(), 0)
            self.assertNotIn('touchid/manage.py', output.getvalue())
            self.assertIn('install-ubuntu.sh', output.getvalue())

    def test_explicit_account_reaches_preflight_and_persistent_install(self):
        args = argparse.Namespace(no_install_deps=False, no_sleep=True, no_wifi=True,
                                  no_desktop=True, wifi_profile=None, activate_wifi=False,
                                  touchid_user='test-account')
        commands = [cmd for _, cmd in module.commands(args)]
        for cmd in (commands[0], commands[-1]):
            self.assertIn('--install-deps', cmd)
            self.assertEqual(cmd[cmd.index('--user') + 1], 'test-account')

    def test_preflight_failure_prevents_baseline_mutations(self):
        with patch.object(sys, 'argv', ['one_shot.py']), patch.object(module, 'host'), \
             patch.dict(module.os.environ, {'SUDO_UID': '1000'}), \
             patch.object(module.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(), 1)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][2], 'preflight')

    def test_development_trial_requires_explicit_selection(self):
        args = argparse.Namespace(no_install_deps=True, no_sleep=True, no_wifi=True,
                                  no_desktop=True, wifi_profile=None, activate_wifi=False,
                                  touchid_trial=True)
        commands = [cmd for _, cmd in module.commands(args)]
        self.assertEqual(commands[-1], ['python3', str(ROOT / 'touchid/manage.py'), 'trial'])

    def test_resume_install_failure_stops_before_wifi_and_desktop(self):
        results = [subprocess.CompletedProcess([], code) for code in (0, 0, 0, 1)]
        with patch.object(sys, 'argv', ['one_shot.py']), patch.object(module, 'host'), \
             patch.dict(module.os.environ, {'SUDO_UID': '1000'}), \
             patch.object(module.subprocess, 'run', side_effect=results) as run, \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(module.main(), 1)
            self.assertEqual(run.call_count, 4)
            self.assertIn('Stopped at: Guarded s2idle', output.getvalue())


if __name__ == '__main__':
    unittest.main()
