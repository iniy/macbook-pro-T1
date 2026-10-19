#!/usr/bin/env python3
"""Regression: a sink monitor must never count as a working internal microphone."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('audio_check', ROOT / 'audio/check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class Verification(unittest.TestCase):
    def test_microphone_excludes_monitor_and_unrelated_device(self):
        component = 'HDA:10138409,106b3600,00100100'
        monitor = {'properties': {'alsa.components': component, 'media.class': 'Audio/Sink'}}
        mic = {'properties': {'alsa.components': component, 'media.class': 'Audio/Source'}}
        other = {'properties': {'alsa.components': 'synthetic-other-codec', 'media.class': 'Audio/Source'}}
        with patch.object(check, 'pulse', return_value=[monitor, mic, other]):
            self.assertEqual(check.endpoints('sources'), [mic])
        with patch.object(check, 'pulse', return_value=[monitor]):
            self.assertEqual(check.endpoints('sources'), [])


if __name__ == '__main__':
    unittest.main()
