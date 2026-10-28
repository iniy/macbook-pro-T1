#!/usr/bin/env python3
"""Installer behavior without touching host services, accounts or video devices."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import ExitStack, redirect_stdout

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('camera_setup', ROOT / 'camera/browser-setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class UserInstallation(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.home = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(setup, 'host'))
        self.stack.enter_context(patch.object(setup.os, 'geteuid', return_value=1000))
        self.stack.enter_context(patch.object(setup.pwd, 'getpwuid', return_value=SimpleNamespace(pw_dir=str(self.home))))
        self.session = self.stack.enter_context(patch.object(setup, 'session_environment', return_value=({}, True)))
        self.run = self.stack.enter_context(patch.object(setup.subprocess, 'run', side_effect=self.command))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.disabled = False
        self.fail_enable = False
        self.destination, self.paths, self.manifest = setup.user_paths(self.home)

    def command(self, command, **kwargs):
        if command[0] == 'cc':
            Path(command[command.index('-o') + 1]).write_bytes(b'test executable')
        if 'enable' in command and self.fail_enable:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 1 if 'is-enabled' in command and self.disabled else 0)

    def service_commands(self):
        return [call.args[0] for call in self.run.call_args_list if call.args[0][0] == 'systemctl']

    def test_fresh_install_and_repeat_preserve_running_service(self):
        setup.user_install()
        self.assertTrue(self.manifest.is_file())
        self.assertIn(['systemctl', '--user', 'enable', '--now', setup.SERVICE], self.service_commands())
        self.run.reset_mock()
        setup.user_install()
        self.assertEqual(self.service_commands(), [])

    def test_adopts_exact_manual_install_without_restart(self):
        setup.user_install()
        self.manifest.unlink()
        self.run.reset_mock()
        setup.user_install()
        self.assertTrue(self.manifest.is_file())
        self.assertEqual(self.service_commands(), [])

    def test_preflight_does_not_write_or_start_services(self):
        setup.user_install(check=True)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.service_commands(), [])

    def test_local_edits_stop_install_and_removal_before_service_changes(self):
        setup.user_install()
        self.paths['check.py'].write_text('# local edit\n')
        original_unit = self.paths['service'].read_bytes()
        self.run.reset_mock()
        for removing in (False, True):
            with self.assertRaisesRegex(RuntimeError, 'locally modified'):
                setup.user_install(remove=removing)
        self.assertEqual(self.service_commands(), [])
        self.assertEqual(self.paths['service'].read_bytes(), original_unit)

    def test_pending_first_activation_retries_after_enable_failure(self):
        self.fail_enable = True
        with self.assertRaises(subprocess.CalledProcessError):
            setup.user_install()
        self.assertTrue((self.destination / 'pending-activation.json').is_file())
        self.fail_enable = False
        self.run.reset_mock()
        setup.user_install()
        self.assertIn(['systemctl', '--user', 'enable', '--now', setup.SERVICE], self.service_commands())
        self.assertFalse((self.destination / 'pending-activation.json').exists())

    def test_disabled_service_stays_disabled_during_update(self):
        setup.user_install()
        self.disabled = True
        self.run.reset_mock()
        with patch.object(setup, 'unit_text', return_value=setup.unit_text(self.destination) + '# updated\n'):
            setup.user_install()
        self.assertFalse(any('enable' in command or 'restart' in command or 'try-restart' in command
                             for command in self.service_commands()))

    def test_logged_out_install_enables_without_bus_or_service_restart(self):
        self.session.return_value = ({}, False)
        setup.user_install()
        self.assertEqual(self.service_commands(), [
            ['systemctl', '--user', 'enable', '--no-reload', setup.SERVICE]])

    def test_remove_without_compiler_and_preserve_unrelated_files(self):
        setup.user_install()
        unrelated = self.destination / 'my-notes.txt'
        unrelated.write_text('keep')
        self.run.reset_mock()
        setup.user_install(remove=True)
        self.assertFalse(any(call.args[0][0] == 'cc' for call in self.run.call_args_list))
        self.assertTrue(unrelated.is_file())
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.paths['service'].exists())

    def test_remove_rejects_empty_modified_binary(self):
        setup.user_install()
        self.paths['browser-bridge'].write_bytes(b'')
        with self.assertRaisesRegex(RuntimeError, 'locally modified'):
            setup.user_install(remove=True)

    def test_symlink_is_not_followed(self):
        self.destination.mkdir(parents=True)
        target = self.home / 'unrelated'
        target.write_text('keep')
        self.paths['check.py'].symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, 'unsafe'):
            setup.user_install()
        self.assertEqual(target.read_text(), 'keep')


class RootInstallation(unittest.TestCase):
    def test_stages_sources_and_checks_user_before_system_mutation(self):
        events = []
        def run(command, **kwargs):
            self.assertEqual(command[:4], ['/usr/sbin/runuser', '-u', 'desktop', '--'])
            source = Path(command[5])
            self.assertEqual(source.read_bytes(), (ROOT / 'camera/browser-setup.py').read_bytes())
            self.assertEqual((source.parent.parent / 'lib/component_support.py').read_bytes(),
                             (ROOT / 'lib/component_support.py').read_bytes())
            self.assertNotIn('LD_PRELOAD', kwargs['env'])
            events.append('check' if '--check' in command else 'user')
        with patch.object(setup, 'host'), \
             patch.object(setup, 'account', return_value=SimpleNamespace(pw_name='desktop')) as account, \
             patch.object(setup, 'dependencies') as dependencies, \
             patch.object(setup, 'system_install', side_effect=lambda: events.append('system')), \
             patch.object(setup.subprocess, 'run', side_effect=run):
            setup.install('desktop', install_deps=True)
        self.assertEqual(events, ['check', 'system', 'user'])
        account.assert_called_once_with('desktop')
        dependencies.assert_called_once_with(True)

    def test_user_preflight_failure_does_not_modify_system_configuration(self):
        with patch.object(setup, 'host'), \
             patch.object(setup, 'account', return_value=SimpleNamespace(pw_name='desktop')), \
             patch.object(setup, 'dependencies'), patch.object(setup, 'system_install') as system, \
             patch.object(setup.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, [])):
            with self.assertRaises(subprocess.CalledProcessError):
                setup.install()
        system.assert_not_called()

    def test_no_dependencies_option_never_invokes_apt(self):
        with patch.object(setup.shutil, 'which', return_value=None), \
             patch.object(setup.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, '--install-deps'):
                setup.dependencies(False)
        run.assert_not_called()

    def test_missing_module_selects_exact_signed_ubuntu_package(self):
        with patch.object(setup.shutil, 'which', return_value='/usr/bin/tool'), \
             patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run, \
             patch.object(setup.subprocess, 'check_output', side_effect=[os.uname().release + ' SMP', '0.15.3\n']):
            setup.dependencies(True)
        self.assertEqual(run.call_args.args[0], ['apt-get', 'install', '--no-remove', '-y',
                         'linux-main-modules-v4l2loopback-' + os.uname().release])

    def test_root_account_rejected(self):
        with patch.object(setup.pwd, 'getpwuid', return_value=SimpleNamespace(
                pw_dir='/root', pw_uid=0, pw_shell='/bin/bash')), patch.dict(os.environ, {'SUDO_UID': '0'}):
            with self.assertRaisesRegex(RuntimeError, 'normal desktop'):
                setup.account()

    def test_readiness_and_boot_guard_precede_camera_discovery(self):
        text = setup.unit_text(Path('/home/desktop/.local/lib/camera'))
        self.assertIn('ConditionKernelCommandLine=t1bridge.trial=1', text)
        self.assertIn('Type=notify', text)
        self.assertIn('Before=wireplumber.service', text)
        self.assertIn('WantedBy=default.target graphical-session.target', text)
        self.assertNotIn('After=graphical-session.target', text)


if __name__ == '__main__':
    unittest.main()
