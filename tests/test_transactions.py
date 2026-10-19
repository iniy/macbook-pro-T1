#!/usr/bin/env python3
"""Exercise real deployment/restoration, including interrupted writes and later edits."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deploy', ROOT / 'lib/deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class Transactions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'root'
        self.state = Path(self.tmp.name) / 'state'
        self.original = self.root / 'etc/modprobe.d/macbook-t1-touchbar.conf'
        self.original.parent.mkdir(parents=True)
        self.original.write_text('# original user configuration\n')
        self.original.chmod(0o640)
        rule = self.root / 'usr/lib/udev/rules.d/39-usbmuxd.rules'
        rule.parent.mkdir(parents=True)
        rule.write_text('SUBSYSTEM=="usb", ATTR{idProduct}=="8600", RUN+="usbmuxd"\n'
                        'SUBSYSTEM=="usb", ATTR{idProduct}=="12a8", RUN+="usbmuxd"\n')

    def test_restore_backups_and_remove_only_owned_files(self):
        deploy.deploy(ROOT, self.state, self.root)
        rule = self.root / 'etc/udev/rules.d/39-usbmuxd.rules'
        self.assertIn('12a8', rule.read_text())
        self.assertTrue(rule.read_text().index('GOTO=') < rule.read_text().index('RUN+='))
        self.assertTrue(deploy.restore(self.state, self.root))
        self.assertEqual(self.original.read_text(), '# original user configuration\n')
        self.assertEqual(self.original.stat().st_mode & 0o777, 0o640)
        self.assertFalse(rule.exists())
        self.assertTrue(deploy.restore(self.state, self.root))

    def test_preserve_later_user_edit(self):
        deploy.deploy(ROOT, self.state, self.root)
        self.original.write_text('# later edit\n')
        self.assertFalse(deploy.restore(self.state, self.root))
        self.assertEqual(self.original.read_text(), '# later edit\n')
        self.original.unlink()  # user explicitly chooses restoration
        self.assertTrue(deploy.restore(self.state, self.root))
        self.assertEqual(self.original.read_text(), '# original user configuration\n')

    def test_interrupted_deployment_restores_every_written_file(self):
        atomic = deploy.atomic
        calls = 0
        def interrupted(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError('simulated disk failure')
            return atomic(*args, **kwargs)
        with patch.object(deploy, 'atomic', interrupted):
            with self.assertRaises(OSError):
                deploy.deploy(ROOT, self.state, self.root)
        self.assertTrue(deploy.restore(self.state, self.root))
        self.assertEqual(self.original.read_text(), '# original user configuration\n')

    def test_symlink_destination_never_overwritten(self):
        self.original.unlink()
        target = self.root / 'personal-file'
        target.write_text('keep')
        self.original.symlink_to(target)
        with self.assertRaises(RuntimeError):
            deploy.deploy(ROOT, self.state, self.root)
        self.assertTrue(self.original.is_symlink())
        self.assertEqual(target.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
