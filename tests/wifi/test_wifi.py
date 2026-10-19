#!/usr/bin/env python3
"""Check hardware isolation, honest verification, privacy, and edit-aware rollback."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'wifi'))
import check
import manage


class Diagnostics(unittest.TestCase):
    def test_unrelated_broadcom_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            sysfs = Path(tmp)
            dev = sysfs / 'bus/pci/devices/0000:02:00.0'
            dev.mkdir(parents=True)
            for name, value in dict(vendor='0x14e4', device='0x43a3',
                                    subsystem_vendor='0x106b', subsystem_device='0x0157').items():
                (dev / name).write_text(value)
            with self.assertRaises(RuntimeError):
                check.hardware(sysfs)
            (dev / 'device').write_text('0x43ba')
            self.assertEqual(check.hardware(sysfs), dev)

    def test_link_report_excludes_network_identity(self):
        # Synthetic test identifiers, not collected hardware data.
        raw = ('Connected to ' + ':'.join(['ab'] * 6) + ' (on wlan0)\n'
               '\tSSID: private-test-network\n\tfreq: 5180\n\tsignal: -48 dBm\n'
               '\ttx bitrate: 866.7 MBit/s VHT-MCS 9\n')
        result = check.link_metrics(raw)
        self.assertTrue(result['associated'])
        self.assertEqual(result['signal_dbm'], -48)
        self.assertEqual(result['tx_link_mbps'], 866.7)
        self.assertNotIn('private-test-network', json.dumps(result))
        self.assertNotIn('ab:', json.dumps(result))
        self.assertNotIn('throughput', result)

    def test_disconnected_card_cannot_pass_verification(self):
        result = dict(driver_detected=True, firmware_loaded=True, link_query_ok=True,
                      nm_activated=False, ip_assigned=False, link={'associated': False})
        self.assertFalse(check.healthy(result))

    def test_ethernet_connectivity_cannot_count_as_wifi(self):
        result = dict(driver_detected=True, firmware_loaded=True, link_query_ok=True,
                      nm_activated=True, ip_assigned=True, link={'associated': True},
                      connectivity={'dns_via_wifi': False, 'https_via_wifi': False})
        self.assertTrue(check.healthy(result))
        self.assertFalse(check.healthy(result, online=True))

    def test_ping_error_is_not_zero_loss(self):
        self.assertIsNone(check.ping_metrics('bind: device unavailable')['packet_loss_percent'])
        self.assertEqual(check.ping_metrics('3 packets transmitted, 0 received, 100% packet loss')
                         ['packet_loss_percent'], 100)

    def test_phy_prefixed_driver_errors_are_counted(self):
        text = ('ieee80211 phy0: brcmf_msgbuf_tx_ioctl: Failed to reserve space in commonring\n'
                'ieee80211 phy0: brcmf_msgbuf_query_dcmd: Timeout on response for query command\n'
                'brcmfmac: no clm_blob available (err=-2)\n')
        self.assertEqual(check.driver_errors(text), 2)

    def test_online_acceptance_includes_gateway_loss(self):
        result = dict(driver_detected=True, firmware_loaded=True, link_query_ok=True,
                      nm_activated=True, ip_assigned=True, link={'associated': True},
                      connectivity={'dns_via_wifi': True, 'https_via_wifi': True,
                                    'gateway_ping': {'success': True, 'packet_loss_percent': 0}})
        self.assertTrue(check.healthy(result, online=True))
        result['connectivity']['gateway_ping']['packet_loss_percent'] = 33.3
        self.assertFalse(check.healthy(result, online=True))
        result['connectivity']['gateway_ping'] = None
        self.assertFalse(check.healthy(result, online=True))


class Rollback(unittest.TestCase):
    def restore(self, current):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            record = {'uuid': 'test-profile', 'key': '802-11-wireless.powersave', 'old': '0', 'new': '2'}
            (state / 'profile.json').write_text(json.dumps([record]))
            with patch.object(manage, 'profile_value', return_value=current), patch.object(manage, 'run') as run:
                result = manage.restore_profile(state)
                return result, json.loads((state / 'profile.json').read_text()), run.call_args_list

    def test_restores_only_owned_field(self):
        ok, remaining, calls = self.restore('2')
        self.assertTrue(ok)
        self.assertFalse(remaining)
        self.assertEqual(calls[0].args[-2:], ('802-11-wireless.powersave', '0'))

    def test_later_user_edit_survives(self):
        ok, remaining, calls = self.restore('3')
        self.assertFalse(ok)
        self.assertEqual(len(remaining), 1)
        self.assertFalse(calls)

    def test_write_ahead_record_without_modification_is_safe(self):
        ok, remaining, calls = self.restore('0')
        self.assertTrue(ok)
        self.assertFalse(remaining)
        self.assertFalse(calls)

    def test_default_payload_does_not_override_radio_or_security(self):
        opts = dict(country=None, disable_offload=None, roamoff=None, profile=None,
                    powersave=None, stable_mac=None)
        files = manage.payload(opts)
        self.assertTrue(all('modprobe' not in name and 'firmware' not in name for name in files))
        self.assertEqual(manage.profile_changes(opts), {})


if __name__ == '__main__':
    unittest.main()
