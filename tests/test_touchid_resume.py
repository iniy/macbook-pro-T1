#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Display wake protocol/failure tests; no physical-device acceptance implied."""
from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('t1_resume', ROOT / 'touchid/resume.py')
WAKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WAKE)


class DisplayWake(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for name, content in {'proc/cmdline': 'quiet t1bridge.trial=1',
                              'sys/class/dmi/id/product_name': 'MacBookPro13,2',
                              'sys/power/mem_sleep': '[s2idle] deep'}.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.make_device('hidraw42')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(WAKE.os, 'geteuid', return_value=0))
        self.open = self.stack.enter_context(patch.object(WAKE.os, 'open', return_value=123))
        self.close = self.stack.enter_context(patch.object(WAKE.os, 'close'))
        self.info = self.stack.enter_context(patch.object(WAKE.os, 'fstat', return_value=SimpleNamespace(
            st_mode=stat.S_IFCHR | 0o600, st_rdev=os.makedev(240, 42))))
        self.awake = False
        self.writes = []
        self.ioctl = self.stack.enter_context(patch.object(WAKE.fcntl, 'ioctl', side_effect=self.exchange))

    def make_device(self, name, interface='06', config='2'):
        usb = self.root / 'sys/devices' / ('synthetic-' + name)
        intf = usb / 'interface'
        hid = intf / 'hid'
        hid.mkdir(parents=True)
        for path, value in ((usb / 'idVendor', '05ac'), (usb / 'idProduct', '8600'),
                            (usb / 'bConfigurationValue', config),
                            (intf / 'bInterfaceNumber', interface)):
            path.write_text(value)
        node = self.root / 'sys/class/hidraw' / name
        node.mkdir(parents=True)
        (node / 'device').symlink_to(hid)
        (node / 'dev').write_text('240:42')

    def exchange(self, fd, operation, buffer, mutate):
        self.assertEqual(fd, 123)
        self.assertTrue(mutate)
        if operation == WAKE.GET_FEATURE:
            buffer[:] = bytes((3, 2 if self.awake else 1)) + bytes(13)
        elif operation == WAKE.SET_FEATURE:
            self.writes.append(bytes(buffer))
            self.awake = True
        else:
            self.fail('Unexpected device operation')
        return len(buffer)

    def recover(self, **kwargs):
        WAKE.recover(lambda _: None, self.root, **kwargs)

    def test_parked_panel_gets_one_wake_and_repeat_does_not_write(self):
        self.recover()
        self.assertEqual(self.writes, [bytes.fromhex('03 02 f4 01') + bytes(11)])
        self.recover()
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.close.call_count, 2)

    def test_read_only_probe_never_writes(self):
        self.recover(read_only=True)
        self.assertEqual(self.writes, [])
        self.close.assert_called_once_with(123)

    def test_other_boot_or_sleep_modes_never_open_hardware(self):
        for name, value in [('proc/cmdline', 'quiet'), ('sys/power/mem_sleep', 's2idle [deep]'),
                            ('sys/class/dmi/id/product_name', 'DifferentMac')]:
            path = self.root / name
            before = path.read_text()
            path.write_text(value)
            self.recover()
            self.open.assert_not_called()
            path.write_text(before)

    def test_discovery_rejects_wrong_configuration_and_ambiguous_devices(self):
        config = self.root / 'sys/devices/synthetic-hidraw42/bConfigurationValue'
        config.write_text('1')
        with self.assertRaisesRegex(RuntimeError, 'exactly one'):
            self.recover()
        self.make_device('hidraw73', interface='02')
        with self.assertRaisesRegex(RuntimeError, 'exactly one'):
            self.recover()
        config.write_text('2')
        self.make_device('hidraw88')
        with self.assertRaisesRegex(RuntimeError, 'exactly one'):
            self.recover()
        self.open.assert_not_called()

    def test_opened_node_must_match_the_discovered_character_device(self):
        for mode, rdev in [(stat.S_IFREG, os.makedev(240, 42)), (stat.S_IFCHR, os.makedev(240, 99))]:
            self.info.return_value = SimpleNamespace(st_mode=mode, st_rdev=rdev)
            with self.assertRaisesRegex(RuntimeError, 'changed during discovery'):
                self.recover()
        self.ioctl.assert_not_called()
        self.assertEqual(self.close.call_count, 2)

    def test_bad_report_does_not_trigger_a_write(self):
        for report in (bytes(15), bytes((3, 7)) + bytes(13), bytes((3, 1))):
            def malformed(fd, operation, buffer, mutate):
                buffer[:len(report)] = report
                return len(report)
            self.ioctl.side_effect = malformed
            with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
                self.recover()
        self.assertEqual(self.writes, [])

    def test_failed_write_or_failed_readback_reports_failure_without_retry(self):
        for failure in ('short-write', 'still-parked'):
            calls = []
            def failed(fd, operation, buffer, mutate):
                calls.append(operation)
                if operation == WAKE.SET_FEATURE:
                    return 4 if failure == 'short-write' else len(buffer)
                buffer[:] = bytes((3, 1)) + bytes(13)
                return len(buffer)
            self.ioctl.side_effect = failed
            with self.assertRaises((OSError, RuntimeError)):
                self.recover()
            self.assertEqual(calls.count(WAKE.SET_FEATURE), 1)
        self.assertEqual(self.close.call_count, 2)

    def test_only_post_suspend_invokes_recovery(self):
        with patch.object(WAKE, 'recover') as recover, patch.dict(os.environ, {}, clear=True):
            for args in (['pre', 'suspend'], ['post', 'hibernate'], ['post', 'suspend-then-hibernate']):
                self.assertEqual(WAKE.main(args), 0)
            recover.assert_not_called()
            self.assertEqual(WAKE.main(['post', 'suspend']), 0)
            recover.assert_called_once()
            recover.reset_mock()
            with patch.dict(os.environ, {'SYSTEMD_SLEEP_ACTION': 'suspend-then-hibernate'}):
                self.assertEqual(WAKE.main(['post', 'suspend']), 0)
            recover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
