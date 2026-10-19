#!/usr/bin/env python3
"""5 GHz-only policy, native country handling, recovery, and exact-source build gates."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'wifi'))
import radio
spec = importlib.util.spec_from_file_location('fiveg_deploy', ROOT / 'wifi/5ghz/deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class FiveGHz(unittest.TestCase):
    def test_boot_archive_requires_vendor_helper_and_selected_firmware(self):
        files = ['updates/dkms/brcmfmac.ko.zst', 'wcc/brcmfmac-wcc.ko.zst',
                 'macbook-t1-5ghz/brcm/brcmfmac43602-pcie.bin.zst',
                 'macbook-t1-5ghz/brcm/brcmfmac43602-pcie.txt']
        deploy.verify_boot_archive('\n'.join(files))
        for index in range(len(files)):
            with self.assertRaisesRegex(RuntimeError, 'Initramfs lacks'):
                deploy.verify_boot_archive('\n'.join(files[:index] + files[index + 1:]))

    def test_interrupted_helper_update_accepts_only_journaled_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            helper = state / 'helper.py'
            versions = [hashlib.sha256(s).hexdigest() for s in [b'old', b'new']]
            (state / 'files.json').write_text(json.dumps({str(helper): versions}))
            with patch.object(deploy, 'STATE', state):
                for content in [b'old', b'new']:
                    helper.write_bytes(content)
                    deploy.owned_files()
                helper.write_text('user edit')
                with self.assertRaisesRegex(RuntimeError, 'Later file edit'):
                    deploy.owned_files()

    def test_profile_is_5ghz_only_without_automatic_original_fallback(self):
        with patch.object(deploy, 'run') as run:
            deploy.configure_profile_preference('original', 'preferred')
        self.assertEqual(run.call_args_list[0].args,
                         ('nmcli', 'connection', 'modify', 'uuid', 'preferred',
                          '802-11-wireless.band', 'a', '802-11-wireless.bssid', '',
                          'connection.autoconnect', 'yes', 'connection.autoconnect-priority', '100'))
        self.assertEqual(run.call_args_list[1].args,
                         ('nmcli', 'connection', 'modify', 'uuid', 'original', 'connection.autoconnect', 'no'))

    def test_restoration_preserves_later_edits_and_deleted_profiles(self):
        values = {'first': 'no', 'edited': 'yes'}
        def run(*args):
            return 'first\nedited' if args[:3] == ('nmcli', '-g', 'UUID') else ''
        with patch.object(deploy, 'run', side_effect=run) as calls, \
             patch.object(deploy, 'value', side_effect=lambda uuid, key: values[uuid]):
            deploy.restore_autoconnect({'saved_autoconnect': {'first': 'yes', 'edited': 'no', 'deleted': 'yes'}})
        self.assertEqual(calls.call_args_list[-1].args,
                         ('nmcli', 'connection', 'modify', 'uuid', 'first', 'connection.autoconnect', 'yes'))
        self.assertEqual(len(calls.call_args_list), 2)

    def test_profile_backup_excludes_other_interfaces_and_wired_profiles(self):
        def run(*args):
            return 'first:wifi\nother:802-11-wireless\nwired:802-3-ethernet'
        def value(uuid, key):
            return {'first': '', 'other': 'external-wifi'}[uuid] if key.endswith('interface-name') else 'yes'
        with patch.object(deploy, 'run', side_effect=run), patch.object(deploy, 'value', side_effect=value):
            self.assertEqual(deploy.saved_autoconnect('wlp2s0'), {'first': 'yes'})

    def test_build_has_no_foreign_country_or_power_override_patch(self):
        names = {p.name for p in (ROOT / 'wifi/5ghz/patches').glob('*.patch')}
        self.assertEqual(names, {'0004-log-pcie-board-data.patch'})
        text = (ROOT / 'wifi/5ghz/deploy.py').read_text()
        self.assertNotIn('legacy_80mhz=1', text)
        self.assertNotIn('fixed_regdom=1', text)
        self.assertIn('add_drivers+=', text)
        self.assertIn('brcmfmac brcmfmac_wcc brcmutil cfg80211', text)

    def test_active_channel_width_and_country(self):
        self.assertEqual(radio.decode('active_chanspec', struct.pack('<4I', 0xd92e, 0, 0, 0)),
                         dict(raw=0xd92e, width_mhz=40, center_channel=46, control_channel=48))
        self.assertEqual(radio.decode('firmware_country', b'IN\0\0' + struct.pack('<i', 0) + b'IN\0\0' + bytes(4)),
                         dict(abbreviation='IN', revision=0, table='IN'))

    def test_missing_provider_fails_without_reboot_or_2ghz_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'state.json').write_text(json.dumps({'boot_id': 'earlier-boot'}))
            (state / 'boot-armed').touch()
            def output(*args):
                raise RuntimeError('missing provider')
            snap = {'link': {'frequency_mhz': 5240}, 'loaded_driver_srcversion': 'wrong-source'}
            with patch.object(deploy, 'STATE', state), patch.object(deploy, 'run', side_effect=output) as run, \
                 patch.object(deploy.check, 'snapshot', return_value=snap), \
                 patch.object(deploy.check, 'healthy', return_value=True), \
                 patch.object(deploy.time, 'sleep'), patch.object(deploy, 'remove') as remove:
                with self.assertRaisesRegex(RuntimeError, 'verification failed'):
                    deploy.boot_check()
                remove.assert_not_called()
                self.assertEqual(len(run.call_args_list), 1)

    def test_boot_verifier_checks_current_kernel_and_clears_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'state.json').write_text(json.dumps({'boot_id': 'earlier-boot'}))
            (state / 'boot-armed').touch()
            def output(*args):
                if args[0] == 'dkms':
                    return 'macbook-t1-wifi-5ghz/1.1.0: installed'
                if 'srcversion' in args:
                    return 'current-source'
                return '/lib/modules/current/updates/dkms/brcmfmac.ko'
            snap = {'link': {'frequency_mhz': 5240}, 'loaded_driver_srcversion': 'current-source'}
            with patch.object(deploy, 'STATE', state), patch.object(deploy, 'run', side_effect=output), \
                 patch.object(deploy.check, 'snapshot', return_value=snap), \
                 patch.object(deploy.check, 'healthy', return_value=True):
                deploy.boot_check()
            self.assertTrue((state / 'boot-validated').exists())
            self.assertFalse((state / 'boot-armed').exists())

    def test_later_owned_file_edit_blocks_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            config = state / 'owned.conf'
            config.write_text('later edit')
            (state / 'state.json').write_text(json.dumps({'version': deploy.VERSION}))
            (state / 'files.json').write_text(json.dumps({str(config): hashlib.sha256(b'original').hexdigest()}))
            with patch.object(deploy, 'STATE', state), patch.object(deploy, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'Later edit'):
                    deploy.remove()
                run.assert_not_called()

    def test_old_deployment_cannot_be_removed_with_wrong_dkms_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'state.json').write_text('{}')
            with patch.object(deploy, 'STATE', state), patch.object(deploy, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'older deployment'):
                    deploy.remove()
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
