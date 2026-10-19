# BCM43602 2.4 GHz reception investigation — 2026-10-19

**The RF reception fault is not yet identified or repaired.** The existing DMA
repair restores association; it does not supply Apple board calibration. This
report distinguishes that confirmed defect from the remaining radio hypothesis.
See [measurements](WIFI-2.4GHZ-BENCHMARKS.md),
[implementation](WIFI-2.4GHZ-IMPLEMENTATION.md) and
[recovery](WIFI-2.4GHZ-RECOVERY.md).

## Authoritative baseline

Work started from the clean local branch `codex/bcm43602-root-cause`, commit
`117774d16b23162907b8500d79698ef11ca0aa0a`. The new branch is
`feature/bcm43602-2g-reception`; no checkout from GitHub replaced local work.

* Actual model: MacBookPro13,2; PCI BCM43602 `14e4:43ba`, revision 02,
  Apple subsystem `106b:0157`.
* Ubuntu 26.10, running `7.3.0-9-generic`, exact source `7.3.0-9.9`.
* Loaded driver: `macbook-t1-wifi-dma/1.0.0` brcmfmac, srcversion
  `D80CC87A0FC605EFE9AD5E6`. Original Ubuntu brcmfmac remains on disk.
* Firmware: `7.35.177.61`, FWID `01-ea662a8c`; owning package
  `linux-firmware-broadcom-wireless` **20260915.git1522c78a-0ubuntu1**.
  `linux-firmware` itself is a metapackage, not the firmware file owner.
* Firmware `.bin.zst` SHA256:
  `1116763aa893bc065586c3a6a83f1d5ea9ca485961a78a777da61af88ed683b6`.
  Uncompressed SHA256:
  `bf4cfc23ee952a3d82ef33a0f5f87853201c98f1bed034876a910f354f37862d`.
  Installed compressed MD5 `4cf6db2c13a9d150351b7c017fe51d0d` matches the
  owning Ubuntu package manifest. Extracted initramfs firmware has the same SHA256.
* Touch Bar/audio DKMS versions are both 1.0.0; camera is stock `uvcvideo`.

Initial link: **−87 dBm**, TX 81 Mbps, RX 2 Mbps, 2432 MHz/channel 5,
40 MHz width; NetworkManager quality 34%. These are instantaneous values,
not a controlled-series median or actual throughput. The profile already had
`band=bg`, no BSSID pin, autoconnect enabled, and default power saving (on).
Ethernet was absent initially and became available before controlled experiments.

## Answers to the root-cause questions

1. **What was wrong originally?** An earlier, traced RX DMA access-direction
   defect prevented association. The existing narrow DMA quirk repairs that.
   Current weak RSSI is a separate unresolved problem. No DMA faults or firmware
   timeouts were present in this boot's starting log.
2. **Did earlier attempts interfere?** No remaining custom firmware/NVRAM,
   offload/roaming overrides, TX-power dispatcher, or regulatory-bypass patch was
   found. Both the root filesystem and extracted initramfs were inspected.
   The Wi-Fi installer did introduce root-only module indexes and misrecognized
   DKMS's `installed (Original modules exist)` status; these are tooling defects,
   not an explanation for lost RF sensitivity. Its early India request also did
   not remain the last country hint after association.
3. **Was correct Apple NVRAM loaded?** No matching external text calibration file
   exists in the installed firmware or initramfs. The source requests
   `brcmfmac43602-pcie.Apple Inc.-MacBookPro13,2.txt`, then the generic `.txt`.
   Firmware GET_REVINFO reports generic board ID `0x061b`, revision `0x1421`,
   vendor `0x14e4`, matching embedded defaults. This supports a board-data
   hypothesis but cannot prove that every OTP-derived calibration field is absent.
4. **Was the binary appropriate?** It is the unmodified Ubuntu BCM43602 station
   image and loads correctly. That does not validate its generic fallback data
   against Apple's RF front end. The `.ap.bin` is not a station-mode substitute.
5. **Were antenna chains correct?** Read-only firmware queries returned TX/RX
   masks 7 (all three enabled). Initial per-chain RSSI was [−85, −87, −84] dBm.
   `iw phy`'s `Available Antennas: TX 0 RX 0` means the driver does not expose the
   nl80211 antenna-selection capability; it does not mean zero active antennas.
   Mask 7 does not establish correct RF routing or healthy antenna cables.
6. **Is reception software-limited?** Suspected, not established. The prior
   session records the owner's report of good macOS reception and approximately
   −81 dBm in Linux at 1–2 metres. No quantitative same-position macOS/reference
   comparison was available in this session. A precise defective RF field is
   still unverified.
7. **Interference?** The AP uses overlapping channel 5 at 40 MHz and other APs
   are visible. Firmware noise readings vary substantially and are not calibrated
   measurements. Interference can affect throughput/latency but does not alone
   explain or prove the reported large near-router RSSI deficit. The earlier
   USB-Ethernet removal test changed mean RSSI only about 0.5 dB.
8. **Did a 5 GHz modification damage 2.4 GHz?** No such active modification was
   found. Generic embedded `boardflags3=0x00000003` differs from the community
   5 GHz files. The existing profile restriction simply selects 2.4 GHz and does
   not change RF calibration. Firmware itself currently exposes only 2.4 GHz.
9. **Is another custom driver required?** No new kernel-code defect explaining
   weak reception was demonstrated. The already-required DMA quirk is retained.
   No new driver, full kernel, or speculative register-write patch was installed.
10. **Physical antenna damage?** Not established. All three paths are weak, and
    the owner's previous macOS observation weighs against a permanently broken
    antenna. A same-AP/same-position comparison on the working Apple driver is
    needed before deciding whether physical RF/antenna inspection is justified.

Firmware-reported RSSI can itself be affected by calibration. The measurements
establish weak **reported** signal and variable real traffic, not a laboratory
measurement of receiver sensitivity. The receiver's absolute gain/error and
the amount attributable to interference remain unverified.

## Newly observed connectivity contributor: roaming

Two repeated short trials roamed between BSSIDs on the same SSID/channel;
the alternative AP had substantially lower scan quality. NetworkManager then
restarted DHCP and changed the Wi-Fi IPv4 address. This disrupted the local
test route and confirms association/address instability beyond the weak RSSI.
It does not establish an authentication or encryption defect.

A controlled per-profile BSSID pin retained the nearer AP in both subsequent
short series. Power saving off did not consistently improve latency/loss and
was reverted to the original policy. The pin and repeated India request are
connectivity controls, not RF calibration repairs. This is the specific testing
justification for the otherwise-optional pin; its mobility tradeoff is documented
in the component README and recovery instructions.

## Router-side recommendation

The observed AP uses channel 5 with 40 MHz width. Use **20 MHz** on 2.4 GHz and
compare **channels 1, 6 and 11** using the router's airtime/interference survey.
The scan showed neighboring BSSs on channels 1 and 5; multiple virtual SSIDs on
one radio must not be counted as independent interferers. `iw survey dump`
returned no survey data, so no measured channel-utilization/noise-floor ranking
is claimed. Router administration was not accessed, and no channel/security
setting was changed. This can improve contention behavior; it is not evidence
that router settings alone explain the near-router RSSI deficit.

## Calibration-source audit

The DeyAgrO file was reviewed along with its installer and history. It supplies
board `0x073e`/revision `0x1101`, `boardflags3=0x40000100`, antenna gains and RF
switch data without unit-specific provenance, then rewrites firmware country
bytes and changes global network policy. Matching the model in its README does
not establish compatibility of those calibration values with this board.

Bogdan7c supplies mixed board data with `boardflags3=0x300`, GB revision 3,
and a driver patch that ignores regulatory notifications. Its own report says
2.4 GHz is broken. None of these changes is installed here.

Broadcom's published `bcmdevs.h` identifies the low three `boardflags3` bits as
`BFL3_FEMCTRL_SUB`, bit `0x100` as `BFL3_FEMTBL_FROM_NVRAM`, and bit `0x200` as
`BFL3_AGC_CFG_2G`. They are RF front-end/gain-control settings, not universal
band-enable switches. Knowing their names does not establish the correct Apple
switch table or validate firmware-specific semantics. No bit brute-force is justified.

The stock binary contains `aa2g=7`, `aa5g=7`, `femctrl=2`, generic `pa2ga*`
coefficients and `maxp2ga*=76`. These are not recovered measurements of this
unit. No `boardflags4` assignment was found in the embedded defaults; this alone
does not prove the parameter unsupported. PA coefficients, antenna gains,
receiver gain and coexistence tables were not rewritten. The reported 31 dBm
TX value is not measured radiated power; the driver reports the firmware's
quarter-dBm value, including its automatic-power value, without a physical RF
measurement. Increasing it is not a receiver fix.

Previous legitimate Apple/macOS and signed model-compatible Boot Camp extraction
attempts are preserved in the older root-cause report. They located BMAC images,
not a verified FullMAC calibration file. The published VFIO/MMIO extraction
procedure targets MacBookPro14,3 and requires running the vendor driver on the
actual device. Its donor output must not be copied into this 13,2. No
redistributable, board-verified replacement has been established.

A new read-only recovery attempt used the public `WLC_GET_SROM` (79),
`cisdump` and `nvram_dump` GET interfaces with their documented structures.
SROM/CIS reads returned `Invalid exchange (-52)`; NVRAM dump returned
`Invalid argument (-22)`. No calibration bytes were recovered. These rejected
queries do not prove the physical OTP empty. No write command or MMIO register
access was used. The actual upstream/Ubuntu PCIe OTP parser supports newer
chips but has no BCM43602 case; blindly adding another chip's offsets would
not establish a valid extraction procedure.

Exact external repository revisions remain in [SOURCES.md](SOURCES.md). Their
scripts, patches, relevant issues and historical comments were inspected; no
third-party installer was executed. Optional missing CLM/TXCAP warnings were not
treated as evidence to install another chipset's artifacts.

## Evidence preservation

Protected baseline, boot image, firmware, configuration archives, module/source
hashes and journals are in `/var/backups/macbook-t1-wifi-2g/20261019-164539`.
Additional initramfs audit and experiment data are under the same parent.
Earlier protected backups remain intact. The accessible shell history had no
Wi-Fi-related commands; repository commits and saved investigation logs supply
the useful history. No credentials or proprietary board data are published.
