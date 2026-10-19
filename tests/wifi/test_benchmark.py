#!/usr/bin/env python3
"""Do not count local routing, counter resets or missing metrics as RF success."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'wifi'))
import benchmark
import country


class Measurements(unittest.TestCase):
    def test_missing_and_reset_statistics_are_unknown(self):
        self.assertIsNone(benchmark.distribution([None]))
        self.assertEqual(benchmark.delta({'retries': None, 'failed': 20}, {'retries': 0, 'failed': 1}),
                         {'retries': None, 'failed': None})

    def test_local_iperf_server_cannot_bypass_wifi(self):
        data = [{'ifname': 'eth-test', 'addr_info': [{'local': '192.168.10.5'}]}]
        with patch.object(benchmark.check, 'command', return_value=(0, json.dumps(data))):
            with self.assertRaisesRegex(ValueError, 'bypass Wi-Fi'):
                benchmark.transfers('wifi-test', '192.168.10.5', 1, 0)

    def test_dispatcher_does_not_change_country_for_ethernet(self):
        with patch.object(sys, 'argv', ['country.py', 'IN', '--interface', 'ethernet-test']), \
             patch.object(country.Path, 'read_text', return_value='MacBookPro13,2'), \
             patch.object(country, 'hardware'), patch.object(country, 'interface', return_value='wifi-test'), \
             patch.object(country.subprocess, 'run') as run:
            country.main()
            run.assert_not_called()

if __name__ == '__main__':
    unittest.main()
