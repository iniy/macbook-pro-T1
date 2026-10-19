#!/usr/bin/env python3
"""Save only allowlisted hardware fields; never persist raw profiler/IORegistry data."""
import json
import pathlib
import plistlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(*args):
    p = subprocess.run(args, capture_output=True, text=True, check=False)
    return p.stdout.strip() or p.stderr.strip()


def main():
    if run('uname', '-s') != 'Darwin':
        raise SystemExit('This read-only capture is for macOS.')
    report = {'os': run('sw_vers'), 'architecture': run('uname', '-m')}
    for key in ['hw.model', 'hw.memsize', 'machdep.cpu.brand_string']:
        report[key] = run('sysctl', '-n', key)
    allowed = {'boot_rom_version', 'os_loader_version', 'smc_version_system',
               'chip_type', 'model_identifier', 'model_name', 'ibridge_model_name',
               'ibridge_version', 'ibridge_firmware_version', 'ibridge_build'}
    data = json.loads(run('system_profiler', 'SPHardwareDataType',
                          'SPiBridgeDataType', '-json'))
    def fields(obj):
        out = {}
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in allowed and isinstance(value, (str, int)):
                    out[key] = value
                elif isinstance(value, (list, dict)):
                    out.update(fields(value))
        elif isinstance(obj, list):
            for value in obj:
                out.update(fields(value))
        return out
    report['firmware'] = fields(data)
    del data
    usb = plistlib.loads(subprocess.check_output(
        ['ioreg', '-a', '-r', '-c', 'IOUSBHostDevice']))
    devices = []
    def walk(items):
        for item in items:
            if item.get('idVendor') == 0x05ac and item.get('idProduct') == 0x8600:
                keys = ['idVendor', 'idProduct', 'bcdDevice', 'bDeviceClass',
                        'bDeviceSubClass', 'bDeviceProtocol', 'bNumConfigurations',
                        'USB Product Name', 'USB Vendor Name']
                devices.append({k: item[k] for k in keys if k in item})
            walk(item.get('IORegistryEntryChildren', []))
    walk(usb)
    del usb
    report['t1_usb'] = devices
    for name, cmd in [('sip', ['csrutil', 'status']),
                      ('gatekeeper', ['spctl', '--status']),
                      ('filevault', ['fdesetup', 'status'])]:
        report[name] = run(*cmd)
    args = subprocess.run(['nvram', 'boot-args'], capture_output=True, text=True)
    report['boot_args'] = ('present; value deliberately omitted' if args.returncode == 0 else
                           'not set' if 'not found' in args.stderr else 'not readable without elevated privileges')
    report['collection_policy'] = ('Only allowlisted fields saved. No serials, UUIDs, '
                                    'NVRAM dump, user names or disk identities.')
    dest = ROOT / 'reports/macos-hardware.json'
    dest.write_text(json.dumps(report, indent=2) + '\n')
    print(dest.name)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
