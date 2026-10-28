#!/usr/bin/env python3
"""A camera label alone must not select an unrelated USB camera."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('camera_check', ROOT / 'camera/check.py')
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)


class Discovery(unittest.TestCase):
    def test_both_t1_boot_formats_are_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(4):
                (root / f'video{i}').mkdir()
            formats = ["'MJPG'", "'H264'", "'META'", "'H264'"]
            with patch.object(camera, 'Path', return_value=root), \
                 patch.object(camera, 't1_ancestor', side_effect=[True, True, True, False]), \
                 patch.object(camera.subprocess, 'check_output', side_effect=formats[:3]):
                self.assertEqual(camera.capture_nodes(), [('/dev/video0', "'MJPG'"), ('/dev/video1', "'H264'")])

    def test_h264_capture_uses_decoder_and_retains_no_file(self):
        completed = subprocess.CompletedProcess([], 0, bytes(range(256)) * 90, b'')
        with patch.object(camera.subprocess, 'run', return_value=completed) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            report = camera.capture('/dev/video0', '1280x720', 'h264')
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('-input_format') + 1], 'h264')
        self.assertEqual(command[-1], 'pipe:1')
        self.assertEqual(report['decoded_frames'], 30)

    def test_usb_ancestry(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / 'synthetic-usb'
            node = parent / 'synthetic-interface/video'
            node.mkdir(parents=True)
            (parent / 'idVendor').write_text('05ac\n')
            (parent / 'idProduct').write_text('8600\n')
            self.assertTrue(camera.t1_ancestor(node))
            (parent / 'idProduct').write_text('ffff\n')
            self.assertFalse(camera.t1_ancestor(node))
            (parent / 'idVendor').write_text('ffff\n')
            self.assertFalse(camera.t1_ancestor(node))


if __name__ == '__main__':
    unittest.main()
