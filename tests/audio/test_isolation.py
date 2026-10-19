#!/usr/bin/env python3
"""Audio deployment/rollback must never modify shared iBridge rules."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('deploy', ROOT / 'lib/deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class Isolation(unittest.TestCase):
    def test_audio_only_transaction_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root, state = Path(directory) / 'root', Path(directory) / 'state'
            rule = root / 'etc/udev/rules.d/39-usbmuxd.rules'
            rule.parent.mkdir(parents=True)
            original = b'# Existing shared T1 exclusion 05ac:8600\n'
            rule.write_bytes(original)
            config = root / 'etc/wireplumber/wireplumber.conf.d/51-macbook-t1-audio.conf'
            config.parent.mkdir(parents=True)
            config.write_text('# preexisting audio policy\n')
            deploy.FILES = {'audio/config/51-macbook-t1-audio.conf': '/' + str(config.relative_to(root))}
            deploy.deploy(ROOT, state, root, usbmux=False)
            self.assertEqual(rule.read_bytes(), original)
            self.assertIn('api.alsa.soft-mixer = true', config.read_text())
            self.assertTrue(deploy.restore(state, root))
            self.assertEqual(config.read_text(), '# preexisting audio policy\n')
            self.assertEqual(rule.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
