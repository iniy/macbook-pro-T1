#!/usr/bin/env python3
"""Exercise public component routing without modifying the host."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('components', ROOT / 'lib/components.py')
components = importlib.util.module_from_spec(spec)
spec.loader.exec_module(components)


class Components(unittest.TestCase):
    def run_cli(self, *args):
        with patch.object(sys, 'argv', ['components.py', *args]), patch.object(
                components.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(components.main(), 0)
            return [call.args[0] for call in run.call_args_list]

    def test_audio_removal_cannot_remove_touchbar(self):
        commands = self.run_cli('uninstall', '--audio')
        self.assertEqual(len(commands), 1)
        self.assertEqual(Path(commands[0][1]).name, 'uninstall-audio.sh')

    def test_shared_camera_dependency_removed_first(self):
        commands = self.run_cli('uninstall', '--all')
        self.assertEqual([Path(cmd[1]).name for cmd in commands],
                         ['suite.py', 'uninstall-camera.sh', 'uninstall-audio.sh', 'uninstall-ubuntu.sh'])

    def test_verify_alias_never_installs(self):
        commands = self.run_cli('install', '--verify', '--all')
        self.assertEqual([Path(cmd[1]).name for cmd in commands],
                         ['verify-ubuntu.sh', 'verify-audio.sh', 'verify-camera.sh'])


if __name__ == '__main__':
    unittest.main()
