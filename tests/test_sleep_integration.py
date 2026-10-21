#!/usr/bin/env python3
"""Test suspend cancellation and configuration rollback without real sleep."""
from contextlib import contextmanager
from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, BASE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WRAPPER = load('suspend_wrapper', 'sleep/suspend-wrapper.py')
MANAGE = load('manage_resume', 'sleep/manage-resume.py')
VENDOR_COMMAND = '{ path=/usr/lib/systemd/systemd-sleep ; argv[]=/usr/lib/systemd/systemd-sleep suspend ; ignore_errors=no ; }'
WRAPPER_COMMAND = '{ argv[]=/usr/bin/python3 /usr/local/lib/macbook-t1-sleep/suspend.py ; }'
GRUB_BEFORE = ('linux /boot/vmlinuz-test root=UUID=test ro quiet splash\n'
               'linux /boot/vmlinuz-test root=UUID=test ro recovery\n')
GRUB_AFTER = GRUB_BEFORE.replace('quiet splash', 'quiet splash pcie_port_pm=off')


@contextmanager
def installer_host(active=False, fail_command=None):
    """Emulate GRUB regeneration and sysfs readback, never modify the host."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        power = root / 'power'
        power.mkdir()
        (power / 'mem_sleep').write_text('s2idle [deep]\n')
        grub = root / 'boot/grub/grub.cfg'
        grub.parent.mkdir(parents=True)
        grub.write_text(GRUB_BEFORE)
        grub.chmod(0o600)
        defaults = root / 'etc/default/grub'
        defaults.parent.mkdir(parents=True)
        defaults.write_text('GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\n')
        commands = []
        real_mkdtemp, real_write = tempfile.mkdtemp, Path.write_text

        def command(*args):
            commands.append(args)
            if args[0] == 'update-grub':
                grub.write_text(GRUB_AFTER if (root / MANAGE.BOOT_DROPIN).exists() else GRUB_BEFORE)
            if args[0] == fail_command:
                raise RuntimeError('simulated ' + args[0] + ' failure')

        def output(*args, **kwargs):
            if args[0][0] == 'systemd-analyze':
                return (MANAGE.SOURCE / '99-macbook-t1-s2idle.conf').read_text()
            unit = root / 'etc/systemd/system/systemd-suspend.service.d/99-macbook-t1-suspend.conf'
            return WRAPPER_COMMAND if unit.exists() else VENDOR_COMMAND

        def write(path, content, *args, **kwargs):
            if path == power / 'mem_sleep' and content.strip() in ('deep', 's2idle'):
                content = '[s2idle] deep\n' if content.strip() == 's2idle' else 's2idle [deep]\n'
            return real_write(path, content, *args, **kwargs)

        with patch.object(MANAGE, 'ROOT', root), patch.object(MANAGE, 'POWER', power), \
             patch.object(MANAGE, 'installation_preflight'), patch.object(MANAGE, 'check_idle'), \
             patch.object(MANAGE.subprocess, 'check_output', output), \
             patch.object(MANAGE, 'boot_active', return_value=active), \
             patch.object(MANAGE, 'command', command), \
             patch.object(Path, 'write_text', write), \
             patch.object(MANAGE.tempfile, 'mkdtemp', side_effect=lambda **kw: real_mkdtemp(dir=root)), \
             redirect_stdout(io.StringIO()) as stdout:
            yield root, power, grub, commands, stdout


class SleepIntegration(unittest.TestCase):
    def test_storage_guard_cancels_upstream_suspend(self):
        @contextmanager
        def guarded_removal(_record):
            raise RuntimeError('Storage attached')
            yield

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(WRAPPER, 'preflight'), \
                 patch.object(WRAPPER, 'KMSG', Path(directory) / 'kmsg'), \
                 patch.object(WRAPPER.PM, 'statistics', return_value={'success': '0'}), \
                 patch.object(WRAPPER.PM, 'temporary_thunderbolt_removal', guarded_removal), \
                 patch.object(WRAPPER.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'Storage attached'):
                    WRAPPER.suspend(lambda _: None)
                run.assert_not_called()

    def test_upstream_failure_still_restores_controllers(self):
        events = []

        @contextmanager
        def removal(_record):
            events.append('detach')
            try:
                yield
            finally:
                events.append('restore')

        def fail(*args, **kwargs):
            events.append('upstream sleep')
            raise subprocess.CalledProcessError(1, args[0])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'mem_sleep').write_text('s2idle [deep]')
            with patch.object(WRAPPER, 'preflight'), patch.object(WRAPPER, 'KMSG', root / 'kmsg'), \
                 patch.object(WRAPPER.PM, 'POWER', root), \
                 patch.object(WRAPPER.PM, 'selected', return_value='s2idle'), \
                 patch.object(WRAPPER.PM, 'statistics', return_value={'success': '0'}), \
                 patch.object(WRAPPER.PM, 'temporary_thunderbolt_removal', removal), \
                 patch.object(WRAPPER.subprocess, 'run', side_effect=fail):
                with self.assertRaises(subprocess.CalledProcessError):
                    WRAPPER.suspend(lambda _: None)
        self.assertEqual(events, ['detach', 'upstream sleep', 'restore'])

    def test_existing_different_configuration_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(MANAGE, 'ROOT', root):
                target = next(iter(MANAGE.files()))
                target.parent.mkdir(parents=True)
                target.write_text('existing local customization')
                with patch.object(MANAGE, 'installation_preflight'), patch.object(MANAGE, 'check_idle'), \
                     patch.object(MANAGE, 'command') as command:
                    with self.assertRaisesRegex(RuntimeError, 'Existing file differs'):
                        MANAGE.install()
                    command.assert_not_called()
                self.assertEqual(target.read_text(), 'existing local customization')

    def test_failed_unit_validation_rolls_back_new_files(self):
        with installer_host(fail_command='systemd-analyze') as (_, power, grub, commands, _):
            with self.assertRaisesRegex(RuntimeError, 'systemd-analyze failure'):
                MANAGE.install()
            self.assertTrue(all(not target.exists() for target in MANAGE.files()))
            self.assertEqual((power / 'mem_sleep').read_text(), 's2idle [deep]\n')
            self.assertEqual(grub.read_text(), GRUB_BEFORE)
            self.assertEqual(grub.stat().st_mode & 0o777, 0o600)
            self.assertEqual(commands[-1], ('systemctl', 'daemon-reload'))

    def test_failed_grub_generation_restores_boot_menu_and_files(self):
        with installer_host(fail_command='update-grub') as (_, power, grub, commands, _):
            with self.assertRaisesRegex(RuntimeError, 'update-grub failure'):
                MANAGE.install()
            self.assertEqual(grub.read_text(), GRUB_BEFORE)
            self.assertTrue(all(not target.exists() for target in MANAGE.files()))
            self.assertEqual((power / 'mem_sleep').read_text(), 's2idle [deep]\n')

    def test_fresh_install_stages_boot_without_claiming_live_activation(self):
        with installer_host() as (_, power, grub, commands, output):
            MANAGE.install()
            self.assertTrue(all(p.read_bytes() == source.read_bytes() for p, source in MANAGE.files().items()))
            self.assertEqual(grub.read_text(), GRUB_AFTER)
            self.assertEqual((power / 'mem_sleep').read_text(), 's2idle [deep]\n')
            self.assertIn('RESTART REQUIRED', output.getvalue())
            self.assertFalse(any('suspend' in command for command in commands))

    def test_reinstall_is_idempotent_and_active_boot_selects_s2idle(self):
        with installer_host(active=True) as (_, power, grub, _, output):
            MANAGE.install()
            before = {p: p.read_bytes() for p in MANAGE.files()}
            MANAGE.install()
            self.assertEqual({p: p.read_bytes() for p in MANAGE.files()}, before)
            self.assertEqual(grub.read_text(), GRUB_AFTER)
            self.assertEqual((power / 'mem_sleep').read_text(), '[s2idle] deep\n')
            self.assertNotIn('RESTART REQUIRED', output.getvalue())

    def test_uninstall_removes_owned_boot_option_and_keeps_nvme(self):
        with installer_host(active=True) as (root, _, grub, _, _):
            nvme = root / 'etc/udev/rules.d/99-macbook-t1-nvme-sleep.rules'
            nvme.parent.mkdir(parents=True)
            nvme.write_text('keep NVMe rule')
            MANAGE.install()
            MANAGE.uninstall()
            self.assertTrue(all(not p.exists() for p in MANAGE.files()))
            self.assertEqual(grub.read_text(), GRUB_BEFORE)
            self.assertEqual(nvme.read_text(), 'keep NVMe rule')

    def test_exact_original_trial_dropin_can_be_upgraded(self):
        legacy = ('# Diagnostic trial for MacBookPro13,2, not a validated suspend fix.\n'
                  '# Installed separately from the normal installer. Remove this file and run\n'
                  '# update-grub to undo; the running kernel changes only after a restart.\n'
                  'GRUB_CMDLINE_LINUX_DEFAULT="${GRUB_CMDLINE_LINUX_DEFAULT} pcie_port_pm=off"\n')
        with installer_host() as (root, _, _, _, _):
            dropin = root / MANAGE.BOOT_DROPIN
            dropin.parent.mkdir(parents=True)
            dropin.write_text(legacy)
            MANAGE.install()
            self.assertEqual(dropin.read_bytes(), MANAGE.files()[dropin].read_bytes())

    def test_grub_rejects_conflicting_or_unrelated_changes(self):
        for text in (GRUB_BEFORE, GRUB_AFTER.replace('pcie_port_pm=off', 'pcie_port_pm=off pcie_port_pm=force'),
                     GRUB_AFTER.replace('quiet', 'unrelated-parameter')):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                MANAGE.validate_grub(text, GRUB_BEFORE)
        MANAGE.validate_grub(GRUB_AFTER, GRUB_BEFORE)

    def test_boot_dropin_preserves_arguments_without_duplicates(self):
        script = str(MANAGE.SOURCE / '99-macbook-t1-pcie-pm-trial.cfg')
        for original in ('quiet splash crashkernel=512M', 'quiet pcie_port_pm=off', ''):
            output = subprocess.check_output(
                ['/bin/bash', '-eu', '-c', '. "$1"; printf "%s" "$GRUB_CMDLINE_LINUX_DEFAULT"', 'sh', script],
                env={'PATH': '/usr/bin:/bin', 'GRUB_CMDLINE_LINUX_DEFAULT': original}, text=True)
            expected = original.split()
            if 'pcie_port_pm=off' not in expected:
                expected.append('pcie_port_pm=off')
            self.assertEqual(output.split(), expected)

    def test_sleep_configuration_rejects_later_overrides(self):
        good = (MANAGE.SOURCE / '99-macbook-t1-s2idle.conf').read_text()
        MANAGE.validate_sleep_config('[Sleep]\nMemorySleepMode=deep\n' + good)
        for extra in ('MemorySleepMode=deep', 'MemorySleepMode=\nMemorySleepMode=deep', 'SuspendState=freeze'):
            with self.subTest(extra=extra), self.assertRaisesRegex(RuntimeError, 'conflicts'):
                MANAGE.validate_sleep_config(good + '\n[Sleep]\n' + extra)

    def test_symlink_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(MANAGE, 'ROOT', root):
                target = next(iter(MANAGE.files()))
                target.parent.mkdir(parents=True)
                victim = root / 'existing-file'
                victim.write_text('preserve')
                target.symlink_to(victim)
                with self.assertRaisesRegex(RuntimeError, 'symlink'):
                    MANAGE.check_paths()
                self.assertEqual(victim.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
