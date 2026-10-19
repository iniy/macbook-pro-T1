# 5 GHz-only rebuild from the original Wi-Fi baseline

Date: 2026-10-19. Branch: `feature/wifi-5ghz-only-rebuild`.

## Requested undo

The owner explicitly selected **restore the original Wi-Fi baseline**, then
rebuild for 5 GHz only. Before changing anything, the later repository history
and uncommitted changes were archived in the invoking user's
`wifi-baseline-restore/`; current network state and module hashes were backed up
under `/var/backups/macbook-t1-wifi-original-restore/` (root-only).

The previous DMA DKMS deployment, country service, diagnostics timer and owned
profile settings were removed. Two stale rollback records referenced a profile
already deleted by later work; these records were archived, not recreated over
current saved networks. An old saved regulatory value of `98` is a derived
intersection, not a valid country request; the original baseline `00` was used.
Stock brcmfmac was restored **both on disk and live**, and its loaded srcversion
was verified against the packaged module before starting this rebuild.
Touch Bar, audio and camera module hashes matched the pre-undo backup.

Newer non-Wi-Fi project work was preserved. No Git history was force-rewritten.

## Hardware and selected repair

* MacBookPro13,2; BCM43602 revision 02, PCI `14e4:43ba`, subsystem `106b:0157`.
* Ubuntu 26.10; kernel `7.3.0-9-generic`, exact source/header package `7.3.0-9.9`.
* Original firmware `7.35.177.61`, FWID `01-ea662a8c`.
* New DKMS package: `macbook-t1-wifi-5ghz/1.1.0`.
* Installed/loaded srcversion at activation: `140946324F62E6D0A4EA753`.

The rebuild uses the matching Ubuntu source with the narrow RX-buffer DMA
direction repair independently reviewed from the later investigation. Apple's
BCM43602 firmware reads posted RX buffers; a write-only IOMMU mapping can produce
DMA read faults and command timeouts. Only this exact PCI/subsystem/revision
uses `DMA_BIDIRECTIONAL`; mapping and unmapping use the same recorded direction.
IOMMU protection remains enabled. The only other source patch logs successful
board-file loading without logging calibration or hardware addresses.

The previous custom regulatory guards and GB/3 80 MHz table override were
removed. No feature-disable mask, roamoff option, country-table substitution,
power override, WPA downgrade or PMF disable is installed.

## Firmware and board provenance

Ubuntu station binary SHA256 (uncompressed):
`bf4cfc23ee952a3d82ef33a0f5f87853201c98f1bed034876a910f354f37862d`.

Model-matched community NVRAM reference:
[Bogdan7c/macbook-bcm43602-wifi-fix](https://github.com/Bogdan7c/macbook-bcm43602-wifi-fix),
commit `35dd57c5b2b0fc8f76af5c6c2a45ead010692421`, file
`files/brcmfmac43602-pcie.txt`, source SHA256
`9f757ace460a40c80a32202e09d507351a8c497f2dee22ba0f8a0a5cb1aebaf7`.
Its upstream lineage is MikeRatcliffe's gist/kernel bug 193121.

The source was reviewed and had prior successful measurements on this same
physical model/PCI subsystem; the fresh rebuild independently verifies 5 GHz
association and traffic. It is **not proven unit-specific factory calibration**.
No PA, gain, chain or boardflag value was invented or altered. Only the
device-reported address and `ccode=IN, regrev=0` are substituted. The reported
address's factory provenance remains unverified; no external person's address
is hardcoded. The board file and proprietary binary are fetched/installed
locally, not committed or packaged as project source.

Files use `alternative_fw_path=macbook-t1-5ghz`; Ubuntu's default firmware files
remain byte-for-byte intact. Missing optional CLM/TXCAP is not filled with files
from other chips.

## 5 GHz-only policy and country

The project creates a band-`a` profile bound to the onboard interface, priority
100, with autoconnect enabled. Applicable preexisting wireless profiles retain
their credentials, but autoconnect is disabled with reversible per-profile
records. A connection loss cannot automatically select those old 2.4 GHz
profiles. Wired networking and profiles bound to another Wi-Fi interface are
not changed. Manually created future profiles are outside this saved policy.

India was explicitly confirmed by the owner. An early country service and an
adapter-scoped NM `up` dispatcher request India through normal cfg80211 handling.
The AP advertises US; the host can show intersection `98`. Fresh firmware GETs
show **IN/0**, and association remains **channel 48 / 80 MHz** through normal
negotiation, including a deliberate reconnect. This supersedes the older claim
that 80 MHz necessarily requires a foreign firmware table. No such table is
forced by this rebuild.

## Boot initialization repair

Inspection of the previous failed boot found:

```text
brcmf_fwvid_request_module: mod=wcc: failed 256
brcmf_attach: brcmf_fwvid_attach failed
brcmf_pcie_setup: Dongle setup failed
```

The fresh dracut configuration explicitly includes `brcmfmac`, `brcmfmac_wcc`,
`brcmutil`, `cfg80211`, and both selected firmware files. The rebuilt image was
inspected and contains the vendor helper as **`brcmfmac-wcc.ko.zst`** (the disk
filename uses a hyphen), the custom module, the station binary and board file.
The first inspection incorrectly searched for an underscore filename; checking
the actual archive listing confirmed the helper is present.

Post-boot verification reports success/failure without silently reverting to
2.4 GHz or rebooting. Missing AP/internet availability is not treated as a
reason to reboot the user's machine. An actual reboot remains a separate test.

## Deployment and recovery

```bash
sudo ./install-wifi.sh --profile SAVED_WIFI_UUID --activate
./verify-wifi.sh --online
sudo ./uninstall-wifi.sh
```

Live activation checks independent Ethernet and waits for supplicant/P2P
quiescence before a Wi-Fi-only module reload. A 45-minute runtime rollback timer
protects initial deployment; it was cancelled after successful association,
Wi-Fi-bound traffic and reconnect verification. Removal restores the stock
module, original initramfs and original saved-profile autoconnect flags.
No automatic 2.4 GHz reconnect is performed by the live rollback helper.

Private deployment state: `/var/lib/macbook-t1-wifi-5ghz/`.
Recovery details: [WIFI-5GHZ-RECOVERY.md](WIFI-5GHZ-RECOVERY.md).
Actual results: [WIFI-5GHZ-BENCHMARKS.md](WIFI-5GHZ-BENCHMARKS.md).
