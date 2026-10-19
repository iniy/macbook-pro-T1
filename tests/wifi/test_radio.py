import struct
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'wifi'))
import radio


class Radio(unittest.TestCase):
    def test_multiline_vendor_attributes(self):
        data = struct.pack('<II4b', 1, 3, -88, -80, -85, 0) + bytes(52)
        raw = struct.pack('<HHI', 8, 1, 64) + struct.pack('<HH', 68, 2) + data
        text = '\n'.join('vendor response: ' + raw[i:i+16].hex(' ') for i in range(0, len(raw), 16))
        self.assertEqual(radio.decode('antenna_rssi_dbm', radio.response(text, 64)), [-88, -80, -85])

    def test_truncated_or_wrong_version_is_rejected(self):
        with self.assertRaises(ValueError):
            radio.response('vendor response: 08 00 02 00 01', 4)
        with self.assertRaises(ValueError):
            radio.decode('antenna_rssi_dbm', struct.pack('<II4b', 2, 3, -1, -2, -3, 0))
        with self.assertRaises(ValueError):
            radio.decode('antenna_rssi_dbm', struct.pack('<II4b', 1, 5, -1, -2, -3, 0))

    def test_no_arbitrary_iovar_or_setter(self):
        with patch.object(radio.subprocess, 'run') as run:
            with self.assertRaises(KeyError):
                radio.get('wlan0', 'set_country')
            run.assert_not_called()
        for cmd, name, length in radio.QUERIES.values():
            self.assertIn(cmd, (98, 135, 140, 262))
            self.assertGreaterEqual(length, len(name))

    def test_band_list_uses_firmware_enumeration(self):
        self.assertEqual(radio.decode('bands', struct.pack('<III', 1, 2, 0)), ['2.4GHz'])

    def test_revision_offsets_match_kernel_abi(self):
        values = [0] * 17
        values[3], values[5], values[6], values[7], values[11], values[12] = 2, 1563, 5348, 5153, 43602, 11
        result = radio.decode('revision', struct.pack('<17I', *values))
        self.assertEqual(result, dict(chip_revision=2, chip_number=43602,
                                     board_id=1563, board_vendor=5348, board_revision=5153))


if __name__ == '__main__':
    unittest.main()
