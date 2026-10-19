#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Allowlisted firmware GETs. No setters, register access, identities or keys."""
import re
import struct
import subprocess
import tempfile

# Broadcom's public wlioctl ABI; see SOURCES.md. Buffers fit both request names
# and response structures. An iovar name must never be truncated to four bytes.
QUERIES = {
    'antenna_rssi_dbm': (262, b'phy_rssi_ant\0', 64),
    'rx_chain_mask': (262, b'rxchain\0', 32),
    'tx_chain_mask': (262, b'txchain\0', 32),
    'srom_revision': (262, b'sromrev\0', 32),
    'noise_dbm': (135, b'', 4),
    'revision': (98, b'', 68),
    'bands': (140, b'', 12),
}


def response(text, expected):
    # iw repeats the prefix on each 16-byte line on the tested version.
    encoded = text.replace('vendor response:', '')
    if not re.fullmatch(r'[0-9a-fA-F\s]*', encoded):
        raise ValueError('Unexpected vendor response format')
    raw = bytes.fromhex(encoded)
    data = bytearray()
    offset = 0
    while offset < len(raw):
        if offset + 4 > len(raw):
            raise ValueError('Truncated attribute header')
        length, kind = struct.unpack_from('<HH', raw, offset)
        if length < 4 or offset + length > len(raw):
            raise ValueError('Truncated attribute data')
        if kind & 0x3fff == 2:
            data.extend(raw[offset + 4:offset + length])
        offset += (length + 3) & ~3
    if len(data) != expected:
        raise ValueError('Unexpected response length')
    return bytes(data)


def get(iface, name):
    cmd, payload, size = QUERIES[name]
    packet = struct.pack('<IiIII', cmd, size, 20, 0, 0) + payload.ljust(size, b'\0')
    with tempfile.NamedTemporaryFile() as stream:
        stream.write(packet)
        stream.flush()
        result = subprocess.run(['iw', 'dev', iface, 'vendor', 'recv', '0x001018', '0x1', stream.name],
                                capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError('Firmware GET unavailable')
    return response(result.stdout, size)


def decode(name, data):
    if name == 'antenna_rssi_dbm':
        version, count = struct.unpack_from('<II', data)
        if version != 1 or not 1 <= count <= 4:
            raise ValueError('Unrecognized antenna structure')
        return list(struct.unpack_from('<' + 'b' * count, data, 8))
    if name == 'revision':
        values = struct.unpack_from('<17I', data)
        return {'board_id': values[5], 'board_vendor': values[6], 'board_revision': values[7],
                'chip_number': values[11], 'chip_revision': values[3]}
    if name == 'bands':
        count, *bands = struct.unpack_from('<3I', data)
        if count > 2 or any(band not in (1, 2) for band in bands[:count]):
            raise ValueError('Unrecognized band list')
        return ['5GHz' if band == 1 else '2.4GHz' for band in bands[:count]]
    return struct.unpack_from('<i' if name == 'noise_dbm' else '<I', data)[0]


def snapshot(iface):
    result = {}
    for name in QUERIES:
        try:
            result[name] = decode(name, get(iface, name))
        except (OSError, RuntimeError, ValueError, struct.error, subprocess.SubprocessError):
            result[name] = None
    return result
