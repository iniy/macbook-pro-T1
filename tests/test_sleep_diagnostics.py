#!/usr/bin/env python3
"""Exercise restoration and result classification without touching real PM state."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'sleep_test_stages', Path(__file__).resolve().parents[1] / 'sleep/test-stages.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REAL_SPEC = importlib.util.spec_from_file_location(
    'sleep_test_s2idle', Path(__file__).resolve().parents[1] / 'sleep/test-s2idle.py')
REAL = importlib.util.module_from_spec(REAL_SPEC)
REAL_SPEC.loader.exec_module(REAL)


class SleepDiagnostics(unittest.TestCase):
    def test_real_sleep_restores_selected_mode_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            power = Path(directory)
            (power / 'mem_sleep').write_text('s2idle [deep]\n')
            with patch.object(MODULE, 'POWER', power):
                with self.assertRaisesRegex(RuntimeError, 'sleep failed'):
                    with MODULE.temporary_settings({'mem_sleep': 's2idle'}):
                        self.assertEqual((power / 'mem_sleep').read_text(), 's2idle\n')
                        raise RuntimeError('sleep failed')
            self.assertEqual((power / 'mem_sleep').read_text(), 'deep\n')

    def test_existing_rtc_alarm_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            alarm = Path(directory) / 'alarm'
            alarm.write_text('1792603000\n')
            with patch.object(REAL, 'RTC', alarm), patch.object(Path, 'write_text') as write:
                with self.assertRaisesRegex(RuntimeError, 'already armed'):
                    with REAL.wake_alarm():
                        self.fail('Must not replace existing alarm')
                write.assert_not_called()
            self.assertEqual(alarm.read_text(), '1792603000\n')

    def test_rtc_alarm_cleared_after_sleep_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            alarm, wakeup = Path(directory) / 'alarm', Path(directory) / 'wakeup'
            alarm.write_text('')
            wakeup.write_text('enabled\n')
            with patch.object(REAL, 'RTC', alarm), patch.object(REAL, 'RTC_WAKEUP', wakeup):
                with self.assertRaisesRegex(RuntimeError, 'sleep failed'):
                    with REAL.wake_alarm():
                        self.assertEqual(alarm.read_text(), '+20\n')
                        raise RuntimeError('sleep failed')
            self.assertEqual(alarm.read_text(), '0\n')

    def test_disabled_rtc_wakeup_refused_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            alarm, wakeup = Path(directory) / 'alarm', Path(directory) / 'wakeup'
            alarm.write_text('')
            wakeup.write_text('disabled\n')
            with patch.object(REAL, 'RTC', alarm), patch.object(REAL, 'RTC_WAKEUP', wakeup), \
                 patch.object(Path, 'write_text') as write:
                with self.assertRaisesRegex(RuntimeError, 'not enabled'):
                    with REAL.wake_alarm():
                        self.fail('Must not sleep without RTC wake enabled')
                write.assert_not_called()

    def test_real_sleep_requires_duration_success_and_no_rediscovery_faults(self):
        log = 'PM: suspend entry (s2idle)\nPM: suspend exit\n'
        before = {'success': '3', 'fail': '0', 'failed_resume': '0'}
        after = dict(before, success='4')
        self.assertTrue(REAL.completed(log, before, after, 18))
        self.assertFalse(REAL.completed(log, before, after, 0.2))
        self.assertFalse(REAL.completed(log, before, dict(after, failed_resume='1'), 18))
        self.assertFalse(REAL.completed(log + 'device inaccessible', before, after, 18))
        self.assertFalse(REAL.completed(log.replace('s2idle', 'deep'), before, after, 18))

    def test_removal_requires_port_pm_disabled_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            cmdline = Path(directory) / 'cmdline'
            for value in ('quiet splash', 'pcie_port_pm=force',
                          'pcie_port_pm=off pcie_port_pm=force'):
                cmdline.write_text(value)
                with patch.object(MODULE, 'CMDLINE', cmdline), \
                     patch.object(Path, 'write_text') as write:
                    with self.assertRaisesRegex(RuntimeError, 'requires a boot'):
                        with MODULE.temporary_thunderbolt_removal(lambda _: None):
                            self.fail('Must reject unsafe rediscovery configuration')
                    write.assert_not_called()
            cmdline.write_text('quiet splash pcie_port_pm=off')
            with patch.object(MODULE, 'CMDLINE', cmdline):
                MODULE.require_port_pm_off()

    def test_removed_branches_rescanned_after_test_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pci, buses = root / 'pci', root / 'buses'
            for name in MODULE.TB_BRIDGES:
                (pci / name).mkdir(parents=True)
                (pci / name / 'remove').touch()
            for name in ('0000:03', '0000:79'):
                (buses / name).mkdir(parents=True)
                (buses / name / 'rescan').touch()
            original_write = Path.write_text
            rescanned = []

            def write(path, data, *args, **kwargs):
                if path.name == 'remove':
                    shutil.rmtree(path.parent)
                    return len(data)
                if path.name == 'rescan':
                    rescanned.append(path.parent.name)
                    for name, driver in MODULE.TB_ENDPOINTS.items():
                        (pci / name).mkdir(parents=True, exist_ok=True)
                        link = pci / name / 'driver'
                        if not link.is_symlink():
                            link.symlink_to(root / 'drivers' / driver)
                return original_write(path, data, *args, **kwargs)

            with patch.object(MODULE, 'PCI', pci), patch.object(MODULE, 'PCI_BUSES', buses), \
                 patch.object(MODULE, 'require_port_pm_off'), \
                 patch.object(MODULE, 'thunderbolt_attributes'), \
                 patch.object(MODULE, 'reject_thunderbolt_storage'), \
                 patch.object(MODULE.time, 'sleep'), patch.object(Path, 'write_text', write):
                with self.assertRaisesRegex(RuntimeError, 'suspend failed'):
                    with MODULE.temporary_thunderbolt_removal(lambda _: None):
                        self.assertTrue(all(not (pci / n).exists() for n in MODULE.TB_BRIDGES))
                        raise RuntimeError('suspend failed')
            self.assertEqual(rescanned, ['0000:03', '0000:79'])

    def test_thunderbolt_storage_is_rejected_but_internal_nvme_is_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pci, block = root / 'pci', root / 'block'
            pci.mkdir()
            block.mkdir()
            internal = pci / '0000:01:00.0' / 'block' / 'nvme0n1'
            internal.mkdir(parents=True)
            (block / 'nvme0n1').symlink_to(internal)
            with patch.object(MODULE, 'PCI', pci), patch.object(MODULE, 'BLOCK', block):
                MODULE.reject_thunderbolt_storage()
                usb = pci / '0000:03:00.0' / 'usb3' / 'block' / 'sda'
                usb.mkdir(parents=True)
                (block / 'sda').symlink_to(usb)
                with self.assertRaisesRegex(RuntimeError, 'Storage attached'):
                    MODULE.reject_thunderbolt_storage()

    def test_removal_refuses_storage_before_any_write(self):
        with patch.object(MODULE, 'require_port_pm_off'), \
             patch.object(MODULE, 'thunderbolt_attributes'), \
             patch.object(MODULE, 'reject_thunderbolt_storage',
                          side_effect=RuntimeError('Storage attached')), \
             patch.object(Path, 'write_text') as write:
            with self.assertRaisesRegex(RuntimeError, 'Storage attached'):
                with MODULE.temporary_thunderbolt_removal(lambda _: None):
                    self.fail('Storage guard must prevent the test')
            write.assert_not_called()

    def test_thunderbolt_attributes_restore_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('bridge', 'usb')]
            for path in paths:
                path.write_text('1\n')
            with self.assertRaisesRegex(RuntimeError, 'device disappeared'):
                with MODULE.temporary_attributes(paths, lambda _: None):
                    self.assertTrue(all(p.read_text() == '0\n' for p in paths))
                    raise RuntimeError('device disappeared')
            self.assertTrue(all(p.read_text() == '1\n' for p in paths))

    def test_invalid_thunderbolt_value_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('bridge', 'usb')]
            paths[0].write_text('1\n')
            paths[1].write_text('invalid\n')
            with self.assertRaisesRegex(RuntimeError, 'Unexpected D3cold'):
                with MODULE.temporary_attributes(paths, lambda _: None):
                    self.fail('invalid data must not trigger a trial')
            self.assertEqual(paths[0].read_text(), '1\n')

    def test_restore_after_test_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            power = Path(directory)
            (power / 'pm_test').write_text('[none] freezer devices\n')
            (power / 'pm_debug_messages').write_text('0\n')
            with patch.object(MODULE, 'POWER', power):
                with self.assertRaisesRegex(OSError, 'simulated suspend failure'):
                    with MODULE.temporary_settings({'pm_debug_messages': '1', 'pm_test': 'devices'}):
                        raise OSError('simulated suspend failure')
            self.assertEqual((power / 'pm_test').read_text(), 'none\n')
            self.assertEqual((power / 'pm_debug_messages').read_text(), '0\n')

    def test_restore_partial_setup_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            power = Path(directory)
            (power / 'pm_debug_messages').write_text('0\n')
            with patch.object(MODULE, 'POWER', power):
                with self.assertRaises(FileNotFoundError):
                    with MODULE.temporary_settings({'pm_debug_messages': '1', 'pm_test': 'devices'}):
                        self.fail('Must not run a test after failed setup')
            self.assertEqual((power / 'pm_debug_messages').read_text(), '0\n')

    def test_early_wake_is_not_a_pass(self):
        self.assertFalse(MODULE.completed('PM: suspend exit',
                                         {'success': '0', 'fail': '0'},
                                         {'success': '1', 'fail': '0'}))

    def test_resume_error_is_not_a_pass(self):
        log = 'suspend debug: Waiting for 5 second(s).\nPM: suspend exit'
        self.assertFalse(MODULE.completed(log,
                                         {'success': '0', 'fail': '0', 'failed_resume': '0'},
                                         {'success': '1', 'fail': '0', 'failed_resume': '1'}))

    def test_checkpoint_and_successful_return(self):
        log = 'suspend debug: Waiting for 5 second(s).\nPM: suspend exit'
        self.assertTrue(MODULE.completed(log, {'success': '0', 'fail': '0'},
                                        {'success': '1', 'fail': '0'}))

    def test_driver_faults_override_success_counters(self):
        for fault in ['WARNING: drivers/thunderbolt/ctl.c:1130',
                      'thunderbolt: not ready 1023ms after resume; giving up',
                      'pcieport: Unable to change power state from D3cold to D0, device inaccessible']:
            with self.subTest(fault=fault):
                log = 'suspend debug: Waiting for 5 second(s).\n' + fault + '\nPM: suspend exit'
                self.assertFalse(MODULE.completed(log, {'success': '0', 'fail': '0'},
                                                  {'success': '1', 'fail': '0'}))

    def test_ambiguous_selection_is_rejected(self):
        with self.assertRaises(RuntimeError):
            MODULE.selected('none freezer devices')


if __name__ == '__main__':
    unittest.main()
