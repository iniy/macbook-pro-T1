#!/usr/bin/env python3
"""Exercise actual country-guard C logic and decode observed Broadcom wire structures."""
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import importlib.util
import hashlib
import json
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'wifi'))
import radio
spec = importlib.util.spec_from_file_location('fiveg_deploy', ROOT / 'wifi/5ghz/deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class FiveGHz(unittest.TestCase):
    def test_legacy_channel_mask_and_normalized_firmware_country(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'brcmfmac').mkdir()
            for name in ['cfg80211.c', 'pcie.c']:
                shutil.copy2(ROOT / 'wifi/dkms/kernel-source/7.3.0-9.9/brcmfmac' / name, base / 'brcmfmac' / name)
            for p in sorted((ROOT / 'wifi/5ghz/patches').glob('*.patch')):
                subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(p)], cwd=base, check=True)
            text = (base / 'brcmfmac/cfg80211.c').read_text()
            start = text.index('static void brcmf_legacy_80_channels(')
            helper = text[start:text.index('\n}\n', start) + 3]
            start = text.index('if ((!memcmp(ccreq.country_abbrev')
            condition = text[start:text.index('\n\t\t\treturn;', start)][4:-1]
            code = '''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#define NL80211_BAND_5GHZ 1
#define IEEE80211_CHAN_DISABLED 1
#define min(a,b) ((a)<(b)?(a):(b))
#define le32_to_cpu(v) (v)
struct ieee80211_channel { int hw_value,flags,orig_flags,max_power; };
struct ieee80211_supported_band { int n_channels; struct ieee80211_channel *channels; };
struct wiphy { struct ieee80211_supported_band *bands[2]; };
struct country { char country_abbrev[4]; int rev; char ccode[4]; };
''' + helper + '\nstatic bool same_table(struct country ccreq) { return ' + condition + '; }\n' + '''
int main(void) {
 struct ieee80211_channel five[]={{36,0,0,20},{48,0,0,14},{52,0,0,23},{149,0,0,30}};
 struct ieee80211_channel two[]={{1,0,0,20}};
 struct ieee80211_supported_band b5={4,five}, b2={1,two};
 struct wiphy w={{&b2,&b5}};
 brcmf_legacy_80_channels(&w);
 assert(!five[0].flags && five[0].max_power==17);
 assert(!five[1].flags && five[1].max_power==14);
 assert((five[2].flags & 1) && (five[2].orig_flags & 1));
 assert((five[3].flags & 1) && (five[3].orig_flags & 1));
 assert(two[0].max_power==20 && !two[0].flags);
 struct country c={"GB",3,"GB"}; assert(same_table(c));
 memcpy(c.country_abbrev,"IN",3); assert(same_table(c));
 c.rev=0; assert(!same_table(c));
 c.rev=3; memcpy(c.ccode,"IN",3); assert(!same_table(c));
}
'''
            (base / 'legacy.c').write_text(code)
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(base / 'legacy.c'), '-o', str(base / 'legacy')], check=True)
            subprocess.run([str(base / 'legacy')], check=True)

    def test_active_channel_width_and_country(self):
        self.assertEqual(radio.decode('active_chanspec', struct.pack('<4I', 0xd92e, 0, 0, 0)),
                         dict(raw=0xd92e, width_mhz=40, center_channel=46, control_channel=48))
        self.assertEqual(radio.decode('active_chanspec', struct.pack('<4I', 0xe32a, 0, 0, 0))['width_mhz'], 80)
        self.assertEqual(radio.decode('firmware_country', b'IN\0\0' + struct.pack('<i', 0) + b'IN\0\0' + bytes(4)),
                         dict(abbreviation='IN', revision=0, table='IN'))

    def test_country_guard_keeps_user_requests_and_other_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'brcmfmac').mkdir()
            shutil.copy2(ROOT / 'wifi/dkms/kernel-source/7.3.0-9.9/brcmfmac/cfg80211.c', base / 'brcmfmac/cfg80211.c')
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                            str(ROOT / 'wifi/5ghz/patches/0002-apple-43602-india-country-hints.patch')], cwd=base, check=True)
            text = (base / 'brcmfmac/cfg80211.c').read_text()
            start = text.index('static bool brcmf_keep_india_country(')
            helper = text[start:text.index('\n}\n', start) + 3]
            harness = '''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#define PCI_VENDOR_ID_BROADCOM 0x14e4
#define PCI_VENDOR_ID_APPLE 0x106b
#define NL80211_REGDOM_SET_BY_COUNTRY_IE 3
struct device { unsigned vendor, device, subsystem_vendor, subsystem_device, revision; bool pci; };
#define pci_dev device
#define dev_is_pci(d) ((d)->pci)
#define to_pci_dev(d) (d)
struct brcmf_bus { struct device *dev; };
struct brcmf_pub { struct brcmf_bus *bus_if; };
struct regulatory_request { unsigned initiator; };
struct brcmf_fil_country_le { char country_abbrev[4]; int rev; char ccode[4]; };
static bool brcmf_fixed_regdom;
''' + helper + '''
int main(void) {
 struct device good = {0x14e4,0x43ba,0x106b,0x0157,2,true};
 struct brcmf_bus bus = {&good}; struct brcmf_pub pub = {&bus};
 struct regulatory_request req = {3};
 struct brcmf_fil_country_le in = {"IN",0,"IN"};
 assert(!brcmf_keep_india_country(&pub,&req,&in));
 brcmf_fixed_regdom=true;
 assert(brcmf_keep_india_country(&pub,&req,&in));
 for(unsigned i=0;i<3;i++){ req.initiator=i; assert(!brcmf_keep_india_country(&pub,&req,&in)); }
 req.initiator=3;
 for(int i=0;i<6;i++) {
  struct device other=good;
  switch(i){case 0:other.vendor++;break;case 1:other.device++;break;
   case 2:other.subsystem_vendor++;break;case 3:other.subsystem_device++;break;
   case 4:other.revision++;break;case 5:other.pci=false;break;}
  bus.dev=&other; assert(!brcmf_keep_india_country(&pub,&req,&in));
 }
 bus.dev=&good; memcpy(in.ccode,"GB",3);
 assert(!brcmf_keep_india_country(&pub,&req,&in));
}
'''
            (base / 'guard.c').write_text(harness)
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(base / 'guard.c'), '-o', str(base / 'guard')], check=True)
            subprocess.run([str(base / 'guard')], check=True)


class Recovery(unittest.TestCase):
    def test_boot_verification_uses_current_kernel_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'state.json').write_text(json.dumps({'boot_id': 'earlier-boot', 'installed_srcversion': 'old-source'}))
            (state / 'boot-armed').touch()
            def output(*args):
                if args[0] == 'dkms':
                    return 'macbook-t1-wifi-5ghz/1.0.0: installed'
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

    def test_missing_provider_reaches_armed_boot_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'state.json').write_text(json.dumps({'boot_id': 'earlier-boot'}))
            (state / 'boot-armed').touch()
            def output(*args):
                if args[0] == 'dkms':
                    raise RuntimeError('missing provider')
                return ''
            snap = {'link': {'frequency_mhz': 5240}, 'loaded_driver_srcversion': 'wrong-source'}
            with patch.object(deploy, 'STATE', state), patch.object(deploy, 'run', side_effect=output) as run, \
                 patch.object(deploy.check, 'snapshot', return_value=snap), \
                 patch.object(deploy.check, 'healthy', return_value=True), \
                 patch.object(deploy.time, 'sleep'), patch.object(deploy, 'remove') as remove:
                with self.assertRaisesRegex(RuntimeError, 'verification failed'):
                    deploy.boot_check()
                remove.assert_called_once()
                self.assertIn(('systemctl', 'reboot'), [c.args for c in run.call_args_list])

    def test_later_config_edit_blocks_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            config = state / 'owned.conf'
            config.write_text('later user edit')
            (state / 'state.json').write_text('{}')
            (state / 'files.json').write_text(json.dumps({str(config): hashlib.sha256(b'original').hexdigest()}))
            with patch.object(deploy, 'STATE', state), patch.object(deploy, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'Later edit'):
                    deploy.remove()
                run.assert_not_called()
            self.assertEqual(config.read_text(), 'later user edit')

    def test_retired_firmware_cleanup_requires_owned_matching_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = base / 'state'
            fw = base / 'firmware/brcm'
            fw.mkdir(parents=True)
            data = fw / 'board.txt'
            data.write_text('retained')
            archive = base / 'state-removed-1'
            archive.mkdir()
            (archive / 'files.json').write_text(json.dumps({str(data): deploy.digest(data)}))
            # Replace only the privileged live-parameter read with an inert fixture.
            real_path = Path
            def paths(value):
                return base / 'no-live-path' if str(value).startswith('/sys/module/') else real_path(value)
            with patch.object(deploy, 'STATE', state), patch.object(deploy, 'FW', fw), patch.object(deploy, 'Path', side_effect=paths):
                data.write_text('edited')
                with self.assertRaisesRegex(RuntimeError, 'Unowned or edited'):
                    deploy.cleanup_retired_firmware()
                self.assertTrue(data.exists())
                data.write_text('retained')
                deploy.cleanup_retired_firmware()
                self.assertFalse(fw.parent.exists())


if __name__ == '__main__':
    unittest.main()
