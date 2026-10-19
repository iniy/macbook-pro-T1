#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Allowlisted Wi-Fi diagnostics; raw logs, SSIDs, addresses and keys never emitted."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import time

os.environ['PATH'] = '/usr/sbin:/usr/bin:/sbin:/bin'
os.environ['LC_ALL'] = 'C'


def command(*args, timeout=20):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ''


def hardware(sys=Path('/sys')):
    devices = []
    for dev in (sys / 'bus/pci/devices').glob('*'):
        try:
            ids = [(dev / name).read_text().strip() for name in
                   ('vendor', 'device', 'subsystem_vendor', 'subsystem_device')]
            if ids == ['0x14e4', '0x43ba', '0x106b', '0x0157']:
                devices.append(dev)
        except OSError:
            continue
    if len(devices) != 1:
        raise RuntimeError('Expected one Apple BCM43602 (14e4:43ba, 106b:0157)')
    return devices[0]


def interface(dev):
    names = [p.name for p in (dev / 'net').glob('*') if (p / 'wireless').exists()]
    if len(names) != 1:
        raise RuntimeError('Expected one managed Wi-Fi network interface')
    return names[0]


def link_metrics(text):
    result = {'associated': text.startswith('Connected to ')}
    for key, pattern in {
        'frequency_mhz': r'^\s*freq: ([\d.]+)',
        'signal_dbm': r'^\s*signal: (-?[\d.]+)',
        'tx_link_mbps': r'^\s*tx bitrate: ([\d.]+)',
        'rx_link_mbps': r'^\s*rx bitrate: ([\d.]+)',
    }.items():
        match = re.search(pattern, text, re.M)
        result[key] = float(match[1]) if match else None
    return result


def ping_metrics(text):
    result = {'packet_loss_percent': None, 'rtt_ms_min_avg_max': None}
    match = re.search(r'([\d.]+)% packet loss', text)
    if match:
        result['packet_loss_percent'] = float(match[1])
    match = re.search(r'= ([\d.]+)/([\d.]+)/([\d.]+)/[\d.]+ ms', text)
    if match:
        result['rtt_ms_min_avg_max'] = [float(x) for x in match.groups()]
    return result


def driver_errors(text):
    lines = [line for line in text.splitlines() if 'brcmfmac' in line or 'brcmf_' in line]
    return sum(bool(re.search(r'crash|firmware trap|timeout|timed out|commonring|FW failed', line, re.I))
               for line in lines)


def fresh_scan(iface):
    """Wait for NM's LastScan timestamp to advance, not merely for cached AP output."""
    rc, path = command('nmcli', '-g', 'GENERAL.DBUS-PATH', 'device', 'show', iface)
    if rc or not path.strip().startswith('/org/freedesktop/NetworkManager/Devices/'):
        return False

    def stamp():
        rc, text = command('busctl', '--system', 'get-property', 'org.freedesktop.NetworkManager',
                           path.strip(), 'org.freedesktop.NetworkManager.Device.Wireless', 'LastScan')
        match = re.fullmatch(r'x (-?\d+)\s*', text)
        return int(match[1]) if rc == 0 and match else None

    before = stamp()
    rc, _ = command('nmcli', 'device', 'wifi', 'rescan', 'ifname', iface, timeout=35)
    if rc or before is None:
        return False
    for _ in range(30):
        current = stamp()
        if current is not None and current > before:
            return True
        time.sleep(0.5)
    return False


def dns_address(iface, server):
    """Query example.com directly through this device, never the Ethernet resolver."""
    transaction = os.urandom(2)
    packet = transaction + struct.pack('!5H', 0x100, 1, 0, 0, 0)
    packet += b'\x07example\x03com\x00\x00\x01\x00\x01'
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, iface.encode() + b'\0')
        sock.settimeout(4)
        sock.connect((server, 53))
        sock.send(packet)
        data = sock.recv(4096)
    if len(data) < 12 or data[:2] != transaction or data[3] & 15:
        raise ValueError('DNS response failed')

    def skip_name(pos):
        while pos < len(data):
            length = data[pos]
            if length & 0xc0 == 0xc0:
                return pos + 2
            pos += 1
            if length == 0:
                return pos
            pos += length
        raise ValueError('Truncated DNS name')

    pos = 12
    for _ in range(struct.unpack_from('!H', data, 4)[0]):
        pos = skip_name(pos) + 4
    for _ in range(struct.unpack_from('!H', data, 6)[0]):
        pos = skip_name(pos)
        kind, cls, _, length = struct.unpack_from('!HHIH', data, pos)
        pos += 10
        if kind == 1 and cls == 1 and length == 4:
            return socket.inet_ntoa(data[pos:pos + 4])
        pos += length
    raise ValueError('No IPv4 DNS answer')


def connectivity(iface):
    result = {'gateway_ping': None, 'dns_via_wifi': False, 'https_via_wifi': False}
    _, routes = command('ip', '-j', '-4', 'route', 'show', 'default', 'dev', iface)
    gateways = [r['gateway'] for r in json.loads(routes or '[]') if 'gateway' in r]
    if gateways:
        rc, text = command('ping', '-n', '-I', iface, '-c', '3', '-W', '2', gateways[0])
        result['gateway_ping'] = dict(ping_metrics(text), success=rc == 0)
    _, servers = command('nmcli', '-g', 'IP4.DNS', 'device', 'show', iface)
    for server in servers.splitlines():
        try:
            socket.inet_aton(server)
            address = dns_address(iface, server)
            result['dns_via_wifi'] = True
        except (OSError, ValueError, struct.error):
            continue
        rc, code = command('curl', '--silent', '--noproxy', '*', '--interface', 'if!' + iface,
                           '--resolve', 'example.com:443:' + address, '--max-time', '10',
                           '--output', '/dev/null', '--write-out', '%{http_code}', 'https://example.com/')
        result['https_via_wifi'] = rc == 0 and code.strip() == '200'
        break
    return result


def snapshot(online=False, scan=False):
    dev = hardware()
    iface = interface(dev)
    driver = (dev / 'driver').resolve().name
    rc, link = command('iw', 'dev', iface, 'link')
    result = {'kernel': os.uname().release, 'pci_id': '14e4:43ba', 'subsystem_id': '106b:0157',
              'driver_detected': driver == 'brcmfmac', 'link_query_ok': rc == 0,
              'link': link_metrics(link)}
    _, firmware = command('ethtool', '-i', iface)
    version = re.search(r'^firmware-version: ([\w.-]+)$', firmware, re.M)
    result['firmware_loaded'] = version is not None
    result['firmware_version'] = version[1] if version else None
    _, state = command('nmcli', '-g', 'GENERAL.STATE', 'device', 'show', iface)
    result['nm_activated'] = state.startswith('100 ')
    _, addresses = command('ip', '-j', 'address', 'show', 'dev', iface)
    result['ip_assigned'] = any(a.get('scope') == 'global' for d in json.loads(addresses or '[]')
                                for a in d.get('addr_info', []))
    _, ps = command('iw', 'dev', iface, 'get', 'power_save')
    result['power_save'] = 'on' if 'Power save: on' in ps else 'off' if 'Power save: off' in ps else 'unknown'
    phy = (Path('/sys/class/net') / iface / 'phy80211').resolve().name
    _, bands = command('iw', 'phy', phy, 'info')
    enabled = re.findall(r'\* ([\d.]+) MHz \[\d+\](?![^\n]*disabled)', bands)
    result['enabled_2ghz_channels'] = sum(2400 < float(n) < 2500 for n in enabled)
    result['enabled_5ghz_channels'] = sum(4900 < float(n) < 5900 for n in enabled)
    result['fresh_scan_completed'] = fresh_scan(iface) if scan else None
    rc, networks = command('nmcli', '-t', '-f', 'FREQ,SIGNAL,SECURITY', 'device', 'wifi', 'list',
                           'ifname', iface, '--rescan', 'no', timeout=35)
    result['cached_scan_query_ok'] = rc == 0
    # The AP's advertised RATE is intentionally not treated as throughput or negotiated link rate.
    frequencies = re.findall(r'^(\d+) MHz:', networks, re.M)
    result['visible_2ghz_bss'] = sum(2400 < int(n) < 2500 for n in frequencies)
    result['visible_5ghz_bss'] = sum(4900 < int(n) < 5900 for n in frequencies)
    _, reg = command('iw', 'reg', 'get')
    result['regulatory_countries'] = re.findall(r'^country ([A-Z0-9]{2}):', reg, re.M)
    rc, logs = command('journalctl', '-b', '-k', '--no-pager', '-o', 'cat')
    result['kernel_log_access'] = rc == 0 and bool(logs)
    result['boot_driver_error_lines'] = driver_errors(logs) if result['kernel_log_access'] else None
    _, auth = command('journalctl', '-b', '-u', 'wpa_supplicant', '--no-pager', '-o', 'cat')
    result['boot_association_reject_codes'] = sorted({int(n) for n in re.findall(r'status_code=(\d+)', auth)})
    if online:
        result['connectivity'] = connectivity(iface) if result['nm_activated'] else {
            'gateway_ping': None, 'dns_via_wifi': False, 'https_via_wifi': False}
    result['throughput_mbps'] = None
    result['sustained_stability_verified'] = False
    return result


def healthy(result, online=False):
    return all(result[k] for k in ['driver_detected', 'firmware_loaded', 'link_query_ok',
                                  'nm_activated', 'ip_assigned']) and result['link']['associated'] and (
        not online or all(result['connectivity'][k] for k in ['dns_via_wifi', 'https_via_wifi']))


def throughput(server):
    address = ipaddress.IPv4Address(server)
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ValueError('Use an explicit private LAN iperf3 endpoint')
    iface = interface(hardware())
    results = {}
    for name, extra in [('upload_mbps', []), ('download_mbps', ['--reverse'])]:
        rc, text = command('iperf3', '--client', str(address), '--bind-dev', iface,
                           '--connect-timeout', '3000', '--time', '10', '--json', *extra, timeout=20)
        data = json.loads(text or '{}')
        bits = data.get('end', {}).get('sum_received', {}).get('bits_per_second')
        results[name] = round(bits / 1e6, 2) if rc == 0 and isinstance(bits, (float, int)) else None
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--online', action='store_true', help='Low-bandwidth DNS/HTTPS/ping bound to Wi-Fi')
    parser.add_argument('--scan', action='store_true', help='Request a fresh scan')
    parser.add_argument('--stability', type=int, default=0, metavar='SECONDS', help='Sample every 30 seconds; 1800 for 30 minutes')
    parser.add_argument('--iperf-server', help='Explicit private LAN IPv4 iperf3 endpoint; two 10-second device-bound tests')
    args = parser.parse_args()
    if args.stability < 0:
        parser.error('Duration must be nonnegative')
    start = time.monotonic()
    samples = failures = 0
    initial_errors = None
    while True:
        result = snapshot(args.online, args.scan and samples == 0)
        if samples == 0:
            initial_errors = result['boot_driver_error_lines']
        if args.iperf_server and samples == 0 and healthy(result):
            result['throughput_mbps'] = throughput(args.iperf_server)
        samples += 1
        failures += not healthy(result, args.online)
        elapsed = time.monotonic() - start
        result.update(elapsed_seconds=round(elapsed, 1), samples=samples, failed_samples=failures)
        result['sustained_stability_verified'] = (args.online and elapsed >= 1800 and failures == 0
                                                 and initial_errors is not None
                                                 and result['boot_driver_error_lines'] == initial_errors)
        print(json.dumps(result, sort_keys=True), flush=True)
        if elapsed >= args.stability:
            return int(failures != 0)
        time.sleep(min(30, args.stability - elapsed))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        # Avoid echoing arbitrary external data from exceptions.
        print(json.dumps({'verification_error': type(error).__name__, 'verified': False}))
        raise SystemExit(1)
