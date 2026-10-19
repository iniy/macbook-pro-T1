#!/usr/bin/env python3
"""Check that the convenience installer selects existing components without resets."""
import argparse
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
spec = importlib.util.spec_from_file_location('one_shot', ROOT / 'lib/one_shot.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OneShot(unittest.TestCase):
    def test_default_routes_all_hardware_and_desktop_without_live_reset(self):
        args = argparse.Namespace(no_install_deps=False, no_wifi=False, no_desktop=False,
                                  wifi_profile=None, activate_wifi=False)
        commands = [cmd for _, cmd in module.commands(args)]
        self.assertEqual([Path(cmd[1]).name for cmd in commands],
                         ['install-ubuntu.sh', 'install-5ghz.sh', 'configure.sh'])
        self.assertTrue(all(flag in commands[0] for flag in ['--touchbar', '--audio', '--camera']))
        self.assertFalse(any(flag in cmd for cmd in commands for flag in ['--activate', '--update', '--uninstall']))

    def test_plan_never_runs_root_installation(self):
        with patch.object(sys, 'argv', ['one_shot.py', '--plan']), \
             patch.object(module, 'host') as host, patch.object(module.subprocess, 'run') as run, \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(module.main(), 0)
            host.assert_not_called()
            run.assert_not_called()
            self.assertIn('install-5ghz.sh', output.getvalue())


if __name__ == '__main__':
    unittest.main()
