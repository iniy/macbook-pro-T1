#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Repeatable device-bound measurements; no radio/configuration writes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time

import check


def distribution(values):
    values = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    if not values:
        return None
    return dict(count=len(values), median=statistics.median(values), min=min(values),
                max=max(values), stdev=round(statistics.pstdev(values), 3))


def station(iface):
    rc, text = check.command('iw', 'dev', iface, 'station', 'dump')
    result = {}
    for name in ['tx failed', 'tx retries', 'tx packets', 'rx packets']:
        match = re.search(r'^\s*' + name + r':\s*(\d+)', text, re.M)
        result[name.replace(' ', '_')] = int(match[1]) if match and not rc else None
    return result


def counters(iface):
    return {name: int((Path('/sys/class/net') / iface / 'statistics' / name).read_text())
            for name in ['rx_bytes', 'tx_bytes', 'rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped']}


def ipv4_sources(iface):
    rc, text = check.command('ip', '-j', '-4', 'address', 'show', 'dev', iface)
    return tuple(sorted(a['local'] for d in json.loads(text or '[]') for a in d.get('addr_info', [])
                        if a.get('scope') == 'global')) if rc == 0 else ()


def delta(before, after):
    return {k: after[k] - v if v is not None and after.get(k) is not None and after[k] >= v else None
            for k, v in before.items()}


def transfers(iface, server, repeats, delay):
    # Wait for an idle latency period before adding traffic.
    time.sleep(delay)
    address = ipaddress.IPv4Address(server)
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ValueError('Use an explicit private LAN IPv4 endpoint')
    _, text = check.command('ip', '-j', '-4', 'address')
    devices = json.loads(text)
    if any(a['local'] == str(address) for d in devices for a in d.get('addr_info', [])):
        raise ValueError('Endpoint is local to the client namespace; this would bypass Wi-Fi')
    sources = [a['local'] for d in devices if d['ifname'] == iface
               for a in d.get('addr_info', []) if a.get('scope') == 'global']
    if len(sources) != 1:
        raise ValueError('Expected one Wi-Fi IPv4 source')
    results = []
    for _ in range(repeats):
        for direction, extra in [('upload', []), ('download', ['--reverse'])]:
            before = counters(iface)
            rc, text = check.command('iperf3', '--client', str(address), '--bind-dev', iface,
                                     '--bind', sources[0], '--connect-timeout', '3000', '--time', '10',
                                     '--json', *extra, timeout=25)
            after = counters(iface)
            data = json.loads(text or '{}')
            received = data.get('end', {}).get('sum_received', {})
            size = received.get('bytes', 0)
            moved = delta(before, after)['tx_bytes' if direction == 'upload' else 'rx_bytes']
            # Device binding plus interface counters guard against accidental loopback/Ethernet tests.
            stable_source = ipv4_sources(iface) == tuple(sources)
            valid = (rc == 0 and not data.get('error') and size > 0 and moved is not None and
                     moved >= size * .95 and stable_source)
            results.append({'direction': direction, 'valid': valid,
                            'mbps': received.get('bits_per_second', 0) / 1e6 if valid else None,
                            'received_bytes': size, 'wifi_bytes': moved,
                            'source_address_stable': stable_source,
                            'tcp_retransmits': data.get('end', {}).get('sum_sent', {}).get('retransmits')})
    return results


def measure(duration=120, interval=2, server=None, repeats=3):
    dev = check.hardware()
    iface = check.interface(dev)
    first = check.snapshot(online=True, radio_info=os.geteuid() == 0)
    if not first['link']['associated'] or not 2400 < (first['link']['frequency_mhz'] or 0) < 2500:
        raise RuntimeError('Benchmark requires an associated 2.4 GHz link')
    _, routes = check.command('ip', '-j', '-4', 'route', 'show', 'default', 'dev', iface)
    gateway = next((r['gateway'] for r in json.loads(routes) if 'gateway' in r), None)
    if not gateway:
        raise RuntimeError('No Wi-Fi gateway')
    stat_before, bytes_before = station(iface), counters(iface)
    start_wall, start = time.time(), time.monotonic()
    # A pipe left undrained during sampling can fill and stall ping. Spool to a
    # private anonymous file and impose ping's own wall-clock deadline as well.
    ping_output = tempfile.TemporaryFile(mode='w+')
    ping = subprocess.Popen(['ping', '-n', '-I', iface, '-i', '1', '-c', str(max(2, int(duration))),
                             '-w', str(int(duration) + 5), '-W', '2', gateway],
                            stdout=ping_output, stderr=subprocess.DEVNULL, text=True)
    samples, access_points, source_addresses = [], set(), set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(transfers, iface, server, repeats, 25) if server else None
        try:
            while True:
                rc, text = check.command('iw', 'dev', iface, 'link')
                row = check.link_metrics(text)
                row['query_ok'] = rc == 0
                row['elapsed_seconds'] = round(time.monotonic() - start, 3)
                m = re.match(r'Connected to (\S+)', text)
                if m:
                    access_points.add(m[1])
                samples.append(row)
                source_addresses.add(ipv4_sources(iface))
                if time.monotonic() - start >= duration:
                    break
                time.sleep(min(interval, duration - (time.monotonic() - start)))
            traffic = future.result() if future else []
            ping.wait(timeout=10)
            ping_output.seek(0)
            ping_text = ping_output.read()
        finally:
            if ping.poll() is None:
                ping.terminate()
                ping.wait(timeout=5)
            ping_output.close()
    last = check.snapshot(online=True, radio_info=os.geteuid() == 0)
    log_rc, logs = check.command('journalctl', '-k', '-b', '--no-pager', '-o', 'cat',
                                '--since', '@' + str(int(start_wall)))
    logs_known = log_rc == 0 and first['kernel_log_access'] and last['kernel_log_access']
    idle_rtt = [float(rtt) for seq, rtt in re.findall(r'icmp_seq=(\d+).*time=([\d.]+)', ping_text)
                if int(seq) <= 20]
    ping_result = check.ping_metrics(ping_text)
    summary = {
        'duration_seconds': round(time.monotonic() - start, 2), 'samples': len(samples),
        'associated_samples': sum(s['associated'] and s['query_ok'] for s in samples),
        'distinct_access_points': len(access_points),
        'ipv4_source_changed_or_missing': len(source_addresses) != 1 or () in source_addresses,
        'frequencies_mhz': sorted({s['frequency_mhz'] for s in samples if s['frequency_mhz']}),
        'power_save': first['power_save'], 'final_power_save': last['power_save'],
        'rssi_dbm': distribution([s['signal_dbm'] for s in samples]),
        'tx_link_mbps': distribution([s['tx_link_mbps'] for s in samples]),
        'rx_link_mbps': distribution([s['rx_link_mbps'] for s in samples]),
        'gateway_ping': ping_result, 'idle_rtt_ms': distribution(idle_rtt),
        'throughput_upload_mbps': distribution([r['mbps'] for r in traffic if r['direction'] == 'upload']),
        'throughput_download_mbps': distribution([r['mbps'] for r in traffic if r['direction'] == 'download']),
        'station_delta': (delta(stat_before, station(iface)) if len(access_points) == 1
                          else {k: None for k in stat_before}),
        'interface_delta': delta(bytes_before, counters(iface)),
        'new_driver_error_lines': check.driver_errors(logs) if logs_known else None,
        'new_dma_fault_lines': check.dma_errors(logs, dev.name) if logs_known else None,
        'online_before': check.healthy(first, True), 'online_after': check.healthy(last, True),
    }
    # Compare AP identity within this boot without writing BSSIDs/SSIDs. The
    # boot-specific salt prevents these tokens becoming persistent identifiers.
    salt = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    tokens = sorted(hashlib.sha256((salt + ':' + ap).encode()).hexdigest() for ap in access_points)
    return {'summary': summary, 'before': first, 'after': last, 'samples': samples,
            'transfers': traffic, 'boot_scoped_ap_tokens': tokens}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=120)
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--iperf-server')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True, help='New local JSON file; never overwritten')
    args = parser.parse_args()
    if args.seconds < 30 or args.interval < 1 or not 1 <= args.repeats <= 10:
        parser.error('Use >=30 seconds, >=1 second interval, and 1–10 repeats')
    if args.iperf_server and args.seconds < 25 + args.repeats * 50:
        parser.error('Allow 25 seconds plus 50 seconds per transfer pair (including failure timeouts)')
    os.umask(0o077)
    with args.output.open('x') as stream:
        try:
            result = measure(args.seconds, args.interval, args.iperf_server, args.repeats)
        except Exception as error:
            json.dump({'completed': False, 'error_type': type(error).__name__}, stream)
            raise
        json.dump(result, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
