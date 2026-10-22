#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic failure-path tests, explicitly not physical fingerprint evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'touchid'))
import adapters
import build
import deploy
import probe
import trial
import persistent
import setup
from transaction import Transaction


def host():
    return dict(model='MacBookPro13,2', arch='x86_64', distro='ubuntu', version='26.10',
                kernel='7.3.0-9-generic', init='systemd', systemd_version=261,
                t1_devices=[{'configuration': '1'}], fdr='present', legacy_loaded=[], headers_match=True)


class Compatibility(unittest.TestCase):
    def test_no_automatic_promotion_from_a_successful_build(self):
        result = probe.assessment(host(), {'validated': [], 'build_tested': [host()]})
        self.assertFalse(result['eligible'])
        self.assertFalse(result['pam_changed'])

    def test_missing_each_acceptance_check_blocks_promotion(self):
        row = {**host(), 'upstream_commit': build.LOCK['t1bridge']['commit'],
               'acceptance': dict.fromkeys(probe.ACCEPTANCE, 'pass')}
        self.assertTrue(probe.assessment(host(), {'validated': [row]})['eligible'])
        for name in probe.ACCEPTANCE:
            with self.subTest(check=name):
                incomplete = copy.deepcopy(row)
                incomplete['acceptance'][name] = 'not-tested'
                self.assertFalse(probe.assessment(host(), {'validated': [incomplete]})['eligible'])

    def test_kernel_and_upstream_updates_invalidate_evidence(self):
        row = {**host(), 'upstream_commit': build.LOCK['t1bridge']['commit'],
               'acceptance': dict.fromkeys(probe.ACCEPTANCE, 'pass')}
        for field, value in [('kernel', '7.4.0-synthetic'), ('upstream_commit', '0' * 40)]:
            changed = {**row, field: value}
            self.assertFalse(probe.assessment(host(), {'validated': [changed]})['eligible'])

    def test_conflicts_missing_data_and_non_systemd_are_reported(self):
        data = {**host(), 'legacy_loaded': ['apple_touchbar'], 'fdr': 'unreadable', 'init': 'unsupported'}
        reasons = ' '.join(probe.assessment(data)['reasons'])
        for term in ('conflict', 'unreadable', 'systemd'):
            self.assertIn(term, reasons)

    def test_probe_never_reads_fdr_contents(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / 'boot/efi/EFI/APPLE/EMBEDDEDOS/FDRData'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'SYNTHETIC PRIVATE CONTENT')
            value = probe.inspect(root, kernel='synthetic')
            self.assertEqual(value['fdr'], 'present')
            self.assertNotIn('PRIVATE', json.dumps(value))
            path.unlink()
            path.symlink_to('/etc/passwd')
            self.assertEqual(probe.inspect(root, kernel='synthetic')['fdr'], 'unreadable')


class Adapters(unittest.TestCase):
    def test_dependency_detection_and_exact_headers(self):
        for distro in ('ubuntu', 'debian', 'linuxmint'):
            cmd = adapters.dependency_command(distro, '7.3.0-synthetic')
            self.assertIn('--no-remove', cmd)
            self.assertEqual(cmd[-1], 'linux-headers-7.3.0-synthetic')
        self.assertEqual(adapters.dependency_command('fedora', 'synthetic')[-1], 'kernel-devel-synthetic')
        self.assertEqual(adapters.dependency_command('arch', 'synthetic')[:2], ['pacman', '-S'])
        for distro in ('unknown', 'opensuse-leap'):
            with self.assertRaises(RuntimeError):
                adapters.dependency_command(distro, 'synthetic')

    def test_service_and_initramfs_limits(self):
        adapters.Systemd.require(host())
        with self.assertRaises(RuntimeError):
            adapters.Systemd.require({**host(), 'systemd_version': 255})
        cmd = adapters.initramfs_command('synthetic', lambda s: s == 'dracut')
        self.assertEqual(cmd, ['dracut', '--force', '--kver', 'synthetic'])
        with self.assertRaises(RuntimeError):
            adapters.initramfs_command('synthetic', lambda s: False)


class Rollback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'root'
        self.root.mkdir()
        self.tx = Transaction(Path(self.tmp.name) / 'state', self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_repeated_install_and_rollback(self):
        self.tx.put('etc/example', b'new')
        self.tx.put('etc/example', b'new')
        self.assertEqual(len(self.tx.entries), 1)
        self.tx.rollback()
        self.assertFalse((self.root / 'etc/example').exists())
        self.tx.rollback()

    def test_restore_existing_mode_and_contents(self):
        path = self.root / 'configuration'
        path.write_bytes(b'password fallback')
        path.chmod(0o640)
        self.tx.put('configuration', b'new', replace=True)
        Transaction(self.tx.state, self.root).rollback()
        self.assertEqual(path.read_bytes(), b'password fallback')
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)

    def test_rollback_preserves_concurrent_edits(self):
        self.tx.put('configuration', b'new')
        (self.root / 'configuration').write_bytes(b'user edit')
        with self.assertRaises(RuntimeError):
            self.tx.rollback()
        self.assertEqual((self.root / 'configuration').read_bytes(), b'user edit')

    def test_write_failure_after_journal_is_recoverable(self):
        import transaction
        original = transaction.atomic
        def fail_target(path, data, mode=0o600):
            if path == self.root / 'configuration':
                raise OSError('synthetic disk failure')
            original(path, data, mode)
        with patch.object(transaction, 'atomic', side_effect=fail_target):
            with self.assertRaises(OSError):
                self.tx.put('configuration', b'new')
        Transaction(self.tx.state, self.root).rollback()
        self.assertEqual(json.loads(self.tx.journal.read_text()), [])

    def test_symlinks_and_unowned_files_are_rejected(self):
        (self.root / 'link').symlink_to('/etc')
        with self.assertRaises(RuntimeError):
            self.tx.put('link/example', b'new')
        (self.root / 'existing').write_bytes(b'existing')
        with self.assertRaises(RuntimeError):
            self.tx.put('existing', b'new')


class Bundle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.bundle = self.base / 'bundle'
        self.bundle.mkdir()
        path = self.bundle / 'synthetic-binary'
        path.write_bytes(b'SYNTHETIC')
        path.chmod(0o755)
        manifest = {'schema': 1, 'lock': build.LOCK, 'files': {'synthetic-binary': {
            'sha256': build.digest(path), 'mode': 0o755}}}
        (self.bundle / 'manifest.json').write_text(json.dumps(manifest))
        self.root = self.base / 'system'
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_private_install_repeat_uninstall_preserves_authentication(self):
        pam = self.root / 'etc/pam.d/common-auth'
        pam.parent.mkdir(parents=True)
        pam.write_bytes(b'password policy')
        target = deploy.install(self.bundle, self.root)
        self.assertEqual(deploy.install(self.bundle, self.root), target)
        deploy.uninstall(self.root)
        self.assertFalse(target.exists())
        self.assertEqual(pam.read_bytes(), b'password policy')

    def test_modified_install_and_upgrade_are_refused(self):
        target = deploy.install(self.bundle, self.root)
        (target / 'synthetic-binary').write_bytes(b'edited')
        with self.assertRaises(RuntimeError):
            deploy.install(self.bundle, self.root)
        with self.assertRaises(RuntimeError):
            deploy.uninstall(self.root)

    def test_corrupt_source_cannot_be_installed(self):
        (self.bundle / 'synthetic-binary').write_bytes(b'corrupt')
        with self.assertRaises(RuntimeError):
            deploy.install(self.bundle, self.root)
        self.assertFalse((self.root / build.PREFIX.relative_to('/')).exists())

    def test_active_service_blocks_removal(self):
        deploy.install(self.bundle, self.root)
        unit = self.root / 'etc/systemd/system/fprintd.service.d/t1.conf'
        unit.parent.mkdir(parents=True)
        unit.write_text('ExecStart=' + str(build.PREFIX / 'libexec/fprintd'))
        with self.assertRaises(RuntimeError):
            deploy.uninstall(self.root)


class Trial(unittest.TestCase):
    def test_consumed_boot_choice_allows_restage_but_pending_choice_is_preserved(self):
        for env in ('', 'next_entry=\n', 'saved_entry=0\nnext_entry=\n'):
            self.assertFalse(trial.has_pending_boot(env))
        for choice in ('0', 'other-os', trial.ENTRY):
            self.assertTrue(trial.has_pending_boot('next_entry=' + choice + '\n'))

    def test_legacy_udev_guard_and_rollback_preserve_normal_boot_rule(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / 'root'
            path = root / trial.LEGACY_UDEV_RULE
            path.parent.mkdir(parents=True)
            original = (ROOT / 'config' / path.name).read_bytes()
            path.write_bytes(original)
            path.chmod(0o640)
            tx = Transaction(base / 'transaction', root)
            trial.guard_legacy_udev(tx)
            guarded = path.read_bytes()
            self.assertIn(b'IMPORT{cmdline}="t1bridge.trial"', guarded)
            self.assertLess(guarded.index(b'GOTO="macbook_t1_trial_end"'),
                            guarded.index(b'ATTR{bConfigurationValue}="1"'))
            self.assertIn(original, guarded)
            self.assertTrue(guarded.endswith(b'LABEL="macbook_t1_trial_end"\n'))
            tx.rollback()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)

    def test_missing_or_modified_legacy_udev_rule_is_preserved(self):
        for content in (None, b'# local customization\n'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                root = base / 'root'
                path = root / trial.LEGACY_UDEV_RULE
                path.parent.mkdir(parents=True)
                if content is not None:
                    path.write_bytes(content)
                tx = Transaction(base / 'transaction', root)
                with self.assertRaisesRegex(RuntimeError, 'legacy T1 udev rule'):
                    trial.guard_legacy_udev(tx)
                self.assertEqual(tx.entries, [])
                self.assertEqual(path.read_bytes() if path.exists() else None, content)

    def test_single_boot_entry_preserves_root_and_power_arguments(self):
        config = """menuentry 'Ubuntu' --id 'synthetic-normal' {
 search --fs-uuid --set=root synthetic-uuid
 linux /boot/vmlinuz-7.3.0-synthetic root=UUID=synthetic-uuid ro quiet pcie_port_pm=off
 initrd /boot/initrd.img-7.3.0-synthetic
}
"""
        result = trial.menuentry(config, '7.3.0-synthetic', 'initrd-trial')
        self.assertIn('root=UUID=synthetic-uuid ro quiet pcie_port_pm=off t1bridge.trial=1', result)
        self.assertIn('initrd /boot/initrd-trial', result)
        self.assertIn("--id 'macbook-t1-touchid-trial'", result)
        self.assertIn('initrd /boot/initrd.img-7.3.0-synthetic', config)

    def test_ambiguous_grub_is_rejected(self):
        for config in ('', 'menuentry bad {\nlinux /vmlinuz-synthetic\n}\n'):
            with self.assertRaises(RuntimeError):
                trial.menuentry(config, 'synthetic', 'trial')

    def test_units_only_start_on_trial_boot(self):
        unit = trial.conditioned('[Unit]\nDescription=Synthetic\n[Service]\nExecStart=/usr/bin/true\n')
        self.assertIn('ConditionKernelCommandLine=t1bridge.trial=1', unit)
        self.assertIn('Environment=T1BRIDGE_DIAGNOSTICS=1', unit)
        socket = trial.conditioned('[Unit]\nDescription=Synthetic\n[Socket]\nListenStream=1\n')
        self.assertNotIn('Environment=', socket)
        with self.assertRaises(RuntimeError):
            trial.conditioned('[Service]\nExecStart=/usr/bin/true\n')

    def test_configuration_transaction_has_no_pam_or_normal_boot_changes(self):
        import shutil
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            prefix = base / 'prefix'
            upstream = ROOT / 'sources/t1bridge/systemd'
            if not upstream.exists():
                self.skipTest('Upstream checkout absent; covered by local source build')
            shutil.copytree(upstream, prefix / 'integration/systemd')
            root = base / 'root'
            root.mkdir()
            legacy_rule = root / trial.LEGACY_UDEV_RULE
            legacy_rule.parent.mkdir(parents=True)
            original = (ROOT / 'config' / legacy_rule.name).read_bytes()
            legacy_rule.write_bytes(original)
            tx = Transaction(base / 'transaction', root)
            with patch.object(trial, 'PREFIX', prefix):
                trial.install_configuration(tx)
            names = [x['name'] for x in tx.entries]
            self.assertFalse(any(n.startswith(('etc/pam.d/', 'boot/', 'lib/modules/')) for n in names))
            self.assertIn('etc/systemd/system/macbook-t1-touchbar.service.d/90-t1bridge-trial.conf', names)
            self.assertIn(trial.LEGACY_UDEV_RULE, names)
            units = root / 'etc/systemd/system'
            importer = (units / 't1bridge-import.service').read_text()
            xart = (units / 't1-xart-storage@.service').read_text()
            self.assertNotIn('t1bridge-import.service', trial.UNITS)
            self.assertNotIn('WantedBy=multi-user.target', importer)
            self.assertIn('Wants=t1bridge-import.service\n', xart)
            self.assertIn('Before=t1bridge-import.service\n', xart)
            self.assertIn('Type=notify\n', xart)
            self.assertIn('Requires=t1-ncm-ready@%i.service\n', xart)
            self.assertIn('t1-ncm-ready@%i.service\n', next(
                line + '\n' for line in xart.splitlines() if line.startswith('After=')))
            tx.rollback()
            self.assertEqual([p for p in root.rglob('*') if p.is_file()], [legacy_rule])
            self.assertEqual(legacy_rule.read_bytes(), original)


class Desktop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location('touchid_desktop', ROOT / 'touchid/desktop-provider.py')
        cls.provider = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.provider)

    def test_audio_parser_and_bounded_volume(self):
        with patch.object(self.provider, 'command', return_value='Volume: 1.50 [MUTED]\n'):
            self.assertEqual(self.provider.audio_status(), (100, 1))
        with patch.object(self.provider, 'command', return_value='unexpected'):
            with self.assertRaises(ValueError):
                self.provider.audio_status()

    def test_unknown_or_injected_actions_never_execute(self):
        with patch.object(self.provider.os, 'geteuid', return_value=1000), \
             patch.object(self.provider, 'command') as run:
            for args in (['v1', 'set-volume', '101'], ['v1', 'set-volume', '5;id'],
                         ['v1', 'run', 'id'], ['v2', 'status']):
                self.assertEqual(self.provider.main(args), 1)
            run.assert_not_called()

    def test_missing_session_retains_audio(self):
        from contextlib import redirect_stdout
        import io
        with patch.object(self.provider, 'audio_status', return_value=(30, 0)), \
             patch.object(self.provider, 'session', side_effect=ImportError), \
             redirect_stdout(io.StringIO()) as output:
            self.provider.status()
            self.assertEqual(output.getvalue().strip(), 'T1BRIDGE-DESKTOP 1 1 30 0')


class Persistent(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        from contextlib import ExitStack
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        self.root.mkdir()
        self.state = Path(self.temp.name) / 'state'
        self.state.mkdir(mode=0o700)
        self.kernel = '7.3.0-synthetic'
        self.original = ("menuentry 'Ubuntu' --id 'normal' {\n"
                         " linux /boot/vmlinuz-7.3.0-synthetic root=UUID=synthetic ro pcie_port_pm=off\n"
                         " initrd /boot/initrd.img-7.3.0-synthetic\n}\n")
        for name, content in {persistent.MENU: self.original,
                              'boot/vmlinuz-' + self.kernel: 'kernel',
                              'boot/initrd.img-' + self.kernel: 'normal initramfs',
                              'boot/initrd-t1': 'isolated T1 image',
                              'boot/grub/grubenv': 'environment',
                              'etc/pam.d/common-auth': 'original password authentication'}.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.tx = Transaction(self.state / 'files', self.root)
        self.tx.put(trial.LEGACY_UDEV_RULE, b'guard')
        self.prior = list(self.tx.entries)
        (self.state / 'state.json').write_text(json.dumps(
            dict(phase='staged', user='test-account', kernel=self.kernel, image='initrd-t1')))
        self.baseline = {'/' + name: build.digest(self.root / name) for name in (
            persistent.MENU, 'boot/vmlinuz-' + self.kernel, 'boot/initrd.img-' + self.kernel)}
        (self.state / 'baseline-sha256.json').write_text(json.dumps(self.baseline))
        self.env = 'next_entry=\n'
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target, value in ((persistent.os, ('geteuid', 0)),
                              (persistent.platform, ('release', self.kernel)),
                              (persistent.pwd, ('getpwnam', SimpleNamespace(pw_gid=1000))),
                              (persistent.grp, ('getgrnam', SimpleNamespace(gr_gid=1001))),
                              (persistent.os, ('getgrouplist', [1000, 1001]))):
            self.stack.enter_context(patch.object(target, value[0], return_value=value[1]))
        self.stack.enter_context(patch.object(persistent, 'verify', return_value={
            'kernel': self.kernel, 'tests_requested': True}))
        self.stack.enter_context(patch.object(persistent.subprocess, 'check_output', side_effect=self.output))
        self.run = self.stack.enter_context(patch.object(persistent.subprocess, 'run', side_effect=self.command))

    def output(self, cmd, **kwargs):
        if cmd[0] == 'grub-editenv':
            return self.env
        if cmd[0] == 'lsinitrd' and '-f' in cmd:
            return b'guard'
        if cmd[0] == 'lsinitrd':
            return '\n'.join('updates/t1bridge-trial/' + name + '.ko' for name in
                             ('t1_cfgsel', 'appletbdrm', 'apple_t1_ncm', 'uvcvideo'))
        self.fail(str(cmd))

    def command(self, cmd, **kwargs):
        if cmd[0] == 'grub-mkconfig':
            generator = (self.root / persistent.GENERATOR).read_text()
            entry = generator.split("cat <<'MACBOOK_T1_ENTRY'\n", 1)[1].rsplit('MACBOOK_T1_ENTRY\n', 1)[0]
            Path(cmd[-1]).write_text(f'set default="{persistent.ENTRY}"\n' + self.original + entry)
        elif cmd[0] == 'grub-editenv':
            self.env = ''
        return subprocess.CompletedProcess(cmd, 0)

    def enable(self):
        return persistent.enable('test-account', self.root, self.state)

    def test_fresh_unenrolled_setup_repeat_and_full_rollback(self):
        self.enable()  # No fingerprint files exist: enrollment happens after boot.
        self.assertTrue(persistent.configured(self.root))
        self.assertEqual((self.root / 'etc/pam.d/common-auth').read_text(), 'original password authentication')
        for name, checksum in self.baseline.items():
            if name != '/' + persistent.MENU:
                self.assertEqual(build.digest(self.root / name.lstrip('/')), checksum)
        self.run.reset_mock()
        self.enable()
        self.run.assert_not_called()
        Transaction(self.state / 'files', self.root).rollback()
        self.assertEqual((self.root / persistent.MENU).read_text(), self.original)
        self.assertFalse((self.root / persistent.GENERATOR).exists())
        self.assertFalse((self.root / persistent.DROPIN).exists())

    def test_failed_menu_check_restores_only_new_boot_files(self):
        def fail(cmd, **kwargs):
            if cmd[0] == 'grub-script-check':
                raise subprocess.CalledProcessError(1, cmd)
            return self.command(cmd, **kwargs)
        self.run.side_effect = fail
        with self.assertRaises(subprocess.CalledProcessError):
            self.enable()
        self.assertEqual(Transaction(self.state / 'files', self.root).entries, self.prior)
        self.assertEqual((self.root / trial.LEGACY_UDEV_RULE).read_bytes(), b'guard')
        self.assertEqual((self.root / persistent.MENU).read_text(), self.original)
        self.assertFalse((self.root / persistent.DROPIN).exists())
        self.assertFalse((self.state / 'persistent-default.json').exists())

    def test_missing_normal_fallback_is_rejected(self):
        def invalid(cmd, **kwargs):
            result = self.command(cmd, **kwargs)
            if cmd[0] == 'grub-mkconfig':
                path = Path(cmd[-1])
                path.write_text(path.read_text().replace(self.original, ''))
            return result
        self.run.side_effect = invalid
        with self.assertRaisesRegex(RuntimeError, 'fallback'):
            self.enable()
        self.assertEqual((self.root / persistent.MENU).read_text(), self.original)

    def test_later_edits_are_preserved_on_repeat(self):
        self.enable()
        path = self.root / persistent.MENU
        path.write_text('later user boot configuration')
        self.run.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'Managed Touch ID file changed'):
            self.enable()
        self.assertEqual(path.read_text(), 'later user boot configuration')
        self.run.assert_not_called()

    def test_other_pending_boot_is_preserved(self):
        self.env = 'next_entry=another-os\n'
        with self.assertRaisesRegex(RuntimeError, 'one-time boot selection'):
            self.enable()
        self.run.assert_not_called()

    def test_owned_one_time_choice_is_consumed_when_enabling_persistence(self):
        self.env = 'next_entry=' + trial.ENTRY + '\n'
        self.enable()
        self.assertEqual(self.env, '')
        self.assertTrue(persistent.configured(self.root))


class Setup(unittest.TestCase):
    def test_target_scope_does_not_claim_other_kernels_or_models(self):
        self.assertTrue(setup.supported(host()))
        for key, value in (('kernel', 'new-kernel'), ('model', 'other-model'), ('distro', 'debian')):
            self.assertFalse(setup.supported({**host(), key: value}))

    def test_existing_bundle_never_rebuilds_or_installs_packages(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(build, 'PREFIX', Path(folder)), \
             patch.object(deploy, 'verify', return_value={'kernel': host()['kernel'], 'tests_requested': True}), \
             patch.object(setup.subprocess, 'run') as run:
            setup.ensure_bundle(None, host(), True)
            run.assert_not_called()

    def test_build_runs_as_desktop_user_and_failed_build_is_not_installed(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(build, 'PREFIX', Path(folder) / 'absent'), \
             patch.object(setup.tempfile, 'mkdtemp', return_value=folder), \
             patch.object(setup.os, 'chown'), \
             patch.object(deploy, 'install') as install, \
             patch.object(setup.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['build'])) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                setup.ensure_bundle(SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_name='test-account'), host(), False)
            self.assertEqual(run.call_args.args[0][:5], ['runuser', '-u', 'test-account', '--', 'python3'])
            install.assert_not_called()

    def test_install_stages_persistent_image_and_existing_failures_do_not_remove_it(self):
        from types import SimpleNamespace
        owner = SimpleNamespace(pw_name='test-account')
        for previous in (None, {'phase': 'armed'}):
            with self.subTest(previous=previous), \
                 patch.object(setup, 'preflight', return_value=(owner, host())), \
                 patch.object(setup, 'ensure_runtime'), patch.object(setup, 'ensure_bundle'), \
                 patch.object(setup, 'existing_state', return_value=previous), \
                 patch.object(setup.resume, 'install'), patch.object(setup.fingerprint_resume, 'install'), \
                 patch.object(trial, 'Transaction'), \
                 patch.object(trial, 'prepare') as prepare, patch.object(trial, 'rollback') as rollback, \
                 patch.object(persistent, 'enable', side_effect=RuntimeError('synthetic failure')):
                with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
                    setup.install('test-account', False, desktop=False)
                if previous is None:
                    prepare.assert_called_once_with('test-account', arm=False)
                    rollback.assert_called_once_with()
                else:
                    prepare.assert_not_called()
                    rollback.assert_not_called()

    def test_missing_runtime_without_dependency_permission_stops_before_install(self):
        with patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, stdout='')) as run:
            with self.assertRaisesRegex(RuntimeError, 'runtime packages'):
                setup.ensure_runtime(False)
            self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
