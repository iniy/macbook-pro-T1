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


class Faults(unittest.TestCase):
    def test_only_this_adapters_iommu_faults_count(self):
        text = ('DMAR: [DMA Read NO_PASID] Request device [02:00.0] fault addr 0xff4be000 '
                '[fault reason 0x06] PTE Read access is not set\n'
                'DMAR: [DMA Read NO_PASID] Request device [03:00.0] fault addr 0xaa00\n'
                'DMAR: IOMMU enabled\n')
        self.assertEqual(check.dma_errors(text, '0000:02:00.0'), 1)


if __name__ == '__main__':
    unittest.main()
