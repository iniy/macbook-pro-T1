#!/usr/bin/env python3
"""Exercise the actual C quirk, audited-source preparation, and safe removal."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'wifi'))
import manage  # Establishes shared library path used by the installer.
import driver
import check

spec = importlib.util.spec_from_file_location('wifi_prepare', ROOT / 'wifi/dkms/prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class Source(unittest.TestCase):
    def staged(self, directory):
        target = Path(directory) / 'dkms'
        shutil.copytree(ROOT / 'wifi/dkms', target, ignore=shutil.ignore_patterns('build', '__pycache__'))
        shutil.copytree(ROOT / 'wifi/patches', target / 'patches')
        return target

    def test_actual_patch_is_hardware_scoped_and_compiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = self.staged(tmp)
            with patch.object(prepare, 'ROOT', staged), patch.object(prepare, 'source_version', return_value='7.3.0-9.9'):
                prepare.prepare('7.3.0-9-generic')
            text = (staged / 'build/brcmfmac/msgbuf.c').read_text()
            start = text.index('static enum dma_data_direction\nbrcmf_msgbuf_rx_direction')
            helper = text[start:text.index('\n}\n', start) + 3]
            harness = '''
#include <assert.h>
#include <stdbool.h>
#define PCI_VENDOR_ID_BROADCOM 0x14e4
#define PCI_VENDOR_ID_APPLE 0x106b
enum dma_data_direction { DMA_BIDIRECTIONAL, DMA_TO_DEVICE, DMA_FROM_DEVICE };
struct pci_dev { unsigned vendor, device, subsystem_vendor, subsystem_device, revision; bool pci; };
struct brcmf_bus { struct pci_dev *dev; };
#define dev_is_pci(d) ((d)->pci)
#define to_pci_dev(d) (d)
''' + helper + '''
int main(void) {
 struct pci_dev good = {0x14e4, 0x43ba, 0x106b, 0x0157, 2, true};
 struct brcmf_bus bus = { &good };
 assert(brcmf_msgbuf_rx_direction(&bus) == DMA_BIDIRECTIONAL);
 for (int i=0; i<6; ++i) {
  struct pci_dev other = good;
  switch(i) {
   case 0: other.vendor++; break;
   case 1: other.device++; break;
   case 2: other.subsystem_vendor++; break;
   case 3: other.subsystem_device++; break;
   case 4: other.revision++; break;
   case 5: other.pci=false; break;
  }
  bus.dev=&other;
  assert(brcmf_msgbuf_rx_direction(&bus) == DMA_FROM_DEVICE);
 }
}
'''
            source = Path(tmp) / 'scope.c'
            source.write_text(harness)
            binary = Path(tmp) / 'scope'
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
            self.assertIn('brcmf_msgbuf_rx_direction(drvr->bus_if)', text)
            self.assertIn('DMA_TO_DEVICE', text)

    def test_tampered_and_extra_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = self.staged(tmp)
            with patch.object(prepare, 'ROOT', staged):
                prepare.verify_sources()
                path = staged / 'kernel-source/7.3.0-9.9/brcmfmac/msgbuf.c'
                path.write_text(path.read_text() + '\n/* changed */\n')
                with self.assertRaisesRegex(RuntimeError, 'integrity'):
                    prepare.verify_sources()
                (staged / 'kernel-source/unreviewed.c').touch()
                with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
                    prepare.verify_sources()

    def test_unsupported_kernel_is_rejected_before_filesystem_access(self):
        with self.assertRaisesRegex(RuntimeError, 'audited'):
            prepare.source_version('7.4.0-1-generic')


class Removal(unittest.TestCase):
    def test_built_but_uninstalled_module_is_not_owned(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'complete').touch()
            prefix = 'macbook-t1-wifi-dma/1.0.0, 7.3.0-9-generic, x86_64: '
            with patch.object(driver, 'STATE', state), patch.object(driver, 'module_path', return_value=Path('/lib/modules/updates/dkms/brcmfmac.ko')), patch.object(driver, 'run') as run:
                run.return_value = prefix + 'built'
                self.assertFalse(driver.owned('7.3.0-9-generic'))
                run.return_value = prefix + 'installed'
                self.assertTrue(driver.owned('7.3.0-9-generic'))
                run.return_value = prefix + 'installed (Original modules exist)'
                self.assertTrue(driver.owned('7.3.0-9-generic'))

    def test_private_parent_umask_does_not_hide_module_indexes(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'modules.dep'
            old = os.umask(0o077)
            try:
                driver.run(sys.executable, '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).touch()', str(target))
                self.assertEqual(target.stat().st_mode & 0o777, 0o644)
                self.assertEqual(os.umask(0o077), 0o077)
            finally:
                os.umask(old)

    def test_later_source_edits_block_destructive_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, source = Path(tmp) / 'state', Path(tmp) / 'source'
            state.mkdir()
            source.mkdir()
            (state / 'source.json').write_text('{}')
            (source / 'edited').write_text('retain me')
            with patch.object(driver, 'STATE', state), patch.object(driver, 'SOURCE', source), patch.object(driver, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'edited'):
                    driver.remove()
                run.assert_not_called()
            self.assertEqual((source / 'edited').read_text(), 'retain me')

    def test_uninstall_restores_disk_without_live_unload(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, source = Path(tmp) / 'state', Path(tmp) / 'source'
            state.mkdir()
            source.mkdir()
            (state / 'source.json').write_text('{}')
            (state / 'kernels.json').write_text('["7.3.0-9-generic"]')
            def output(*args):
                if args[:2] == ('dkms', 'status'):
                    return 'macbook-t1-wifi-dma/1.0.0, 7.3.0-9-generic, x86_64: installed'
                return ''
            with patch.object(driver, 'STATE', state), patch.object(driver, 'SOURCE', source), patch.object(driver, 'run', side_effect=output) as run, patch.object(driver, 'module_path', return_value=Path('/lib/modules/stock.ko')):
                driver.remove()
                calls = [call.args for call in run.call_args_list]
                self.assertIn(('update-initramfs', '-u', '-k', '7.3.0-9-generic'), calls)
                self.assertFalse(any(c[0] in ('modprobe', 'rmmod', 'nmcli', 'reboot') for c in calls))
            self.assertFalse(state.exists())
            self.assertTrue(list(Path(tmp).glob('state-removed-*/retired-source')))


class Faults(unittest.TestCase):
    def test_only_this_adapters_iommu_faults_count(self):
        text = ('DMAR: [DMA Read NO_PASID] Request device [02:00.0] fault addr 0xff4be000 '
                '[fault reason 0x06] PTE Read access is not set\n'
                'DMAR: [DMA Read NO_PASID] Request device [03:00.0] fault addr 0xaa00\n'
                'DMAR: IOMMU enabled\n')
        self.assertEqual(check.dma_errors(text, '0000:02:00.0'), 1)


if __name__ == '__main__':
    unittest.main()
