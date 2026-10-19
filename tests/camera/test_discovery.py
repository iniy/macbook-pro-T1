#!/usr/bin/env python3
"""A camera label alone must not select an unrelated USB camera."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('camera_check', ROOT / 'camera/check.py')
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)


class Discovery(unittest.TestCase):
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
