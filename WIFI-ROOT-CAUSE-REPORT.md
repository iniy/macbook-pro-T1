# BCM43602 investigation — 19 October 2026

**Historical DMA-repair investigation.** The subsequent
[2.4 GHz-only follow-up](WIFI-2.4GHZ-ROOT-CAUSE.md) records the current deployment,
controlled comparisons and remaining RF limitation. 5 GHz is no longer an
acceptance requirement. The evidence below is retained in its original context.

**Outcome: PARTIAL.** A traced DMA-permission failure was repaired and real
2.4 GHz connectivity restored on the physical Mac. Weak reception and missing
5 GHz remain unresolved. The patch does not supply missing board calibration.
See [measurements](WIFI-BENCHMARKS.md) and [rollback](WIFI-RECOVERY.md).

## Hardware and baseline

The starting repository commit was `ff8bfb3`, on `feature/bcm43602-wifi`;
the worktree was clean. Work continues on `codex/bcm43602-root-cause`.

| Item | Observed value |
|---|---|
| Model / board | MacBookPro13,2 / Mac-66E35819EE2D0D05 |
| PCI adapter | BCM43602, `14e4:43ba`, revision `02`, subsystem `106b:0157` |
| OS / kernel | Ubuntu 26.10 / `7.3.0-9-generic` |
| Exact Ubuntu source | `7.3.0-9.9` |
| Original module | In-tree brcmfmac, WCC firmware vendor; no wl or b43 |
| Original srcversion | `4099E805E1C894131DAFA0B` |
| Firmware package | `20260915.git1522c78a.1ubuntu` |
| Firmware | `7.35.177.61`, FWID `01-ea662a8c` |
| Baseline failure | Association timeouts, DMA read faults, then ioctl/commonring failures |
| Radio exposure | 2.4 GHz only; no 5 GHz channels in the wiphy |

Ethernet provided independent access during the driver reload tests. Only the
user-selected network was used for association and traffic. Other
saved Wi-Fi profiles were retained with autoconnect disabled, as requested.
Passwords, network identities, raw journals and memory dumps are not published.
Initial configuration, firmware inventory and logs are backed up root-only
under `/var/backups/macbook-t1-wifi-investigation`.

## Confirmed association failure: RX DMA direction

The stock driver's kernel log reported `DMA Read NO_PASID` faults from this
PCI device with reason `0x06`, meaning the IOMMU PTE lacked read access.
The device-filtered `dma: dma_map_phys` trace tied fault pages `ff4be000`,
`ff774000` and `ff778000` to live 2048-byte receive mappings at `ff4be5c0`,
`ff774f40` and `ff7788c0`. Those mappings used `DMA_FROM_DEVICE`, which grants
the device write access. The firmware also read them. Page alignment, current
mapping lifetime and matching device were checked; this was not inferred from
the presence of an unrelated IOMMU warning.

The patch in `wifi/patches/0001-apple-43602-rx-dma-direction.patch` uses
`DMA_BIDIRECTIONAL` for RX packet IDs **only** on PCI `14e4:43ba`, subsystem
`106b:0157`, revision 02. The existing packet-ID map/unmap paths use the same
stored direction. TX remains `DMA_TO_DEVICE`; other devices retain their
original behavior. IOMMU translation remains enabled. This grants access only
to driver-owned buffers, without disabling IOMMU protection globally.

A first trial keyed the quirk on `bus->chip`, which was not populated at this
initialization point. Its trace still showed FROM_DEVICE and it was ineffective.
The corrected PCI identity check produced BIDIRECTIONAL mappings, successful
authentication/DHCP, gateway replies and Wi-Fi-bound external HTTP traffic.
The source was built against exact running headers with `W=1`. The running
trial module has srcversion `F3E0B68D0C239003CC2B159`; the DKMS build may have a
different srcversion because the build inputs include different source paths.
The trial and packaged driver source are identical; their `.text` sections
also compare byte-for-byte equal.

This local result is consistent with the independent BCM43602/IOMMU reports in
[Ubuntu bug 2169339](https://bugs.launchpad.net/ubuntu/+source/linux/+bug/2169339).
That report includes other Mac models; it does not establish that this narrow
quirk is sufficient for all BCM43602 hardware. Upstream brcmfmac source was
inspected and still used FROM_DEVICE at the relevant allocation. This patch
has not been accepted upstream.

## Weak signal and missing 5 GHz: evidence and limits

The driver tries the board-qualified
`brcmfmac43602-pcie.Apple Inc.-MacBookPro13,2` names and then generic files.
Ubuntu provides the generic station binary. No matching `.txt`, `.clm_blob`
or `.txcap_blob` was present. These auxiliary requests are optional in this
driver; their absence alone does not prove a fatal firmware-loading error.

Read-only firmware GET_REVINFO returned board vendor `0x14e4`, board ID
`0x061b` and revision `0x1421`, matching generic defaults embedded in the
station binary rather than independently validated Apple board data. The
firmware GET_BANDLIST returned one band, value 2 (2.4 GHz). The missing 5 GHz
problem therefore occurs before scanning/authentication, rather than being
an inability to join a visible 5 GHz AP. No 802.11ac/80 MHz test was possible.

Generic defaults are strong evidence of a board-configuration problem, but
they do **not** identify the exact wrong RF parameter or prove that all device
calibration is absent. GET_REVINFO includes defaults unrelated to the PCI ID;
it is not a replacement hardware identity. The NVRAM dump query was unsupported.
No matching EFI NVRAM variable was found. Earlier read-only macOS inspection
found Apple BMAC images, not a validated Linux FullMAC calibration file.

Parameters such as `boardflags3`, `aa2g`, `aa5g`, antenna gains, FEM maps and PA
tables interact with the board's RF design. In particular, community use of
`boardflags3` bit `0x100` concerns an RF front-end selection; it is not a
universal 5 GHz-enable switch. No antenna-chain, PA or board-flag values were
invented or installed. No MAC address or firmware country string was changed.
Read-only firmware queries returned `rxchain=7`, `txchain=7`, `nmode=1`,
`vhtmode=1` and `sromrev=11`. Thus the configured chain masks already include
all three chains and VHT is enabled, despite the absent 5 GHz band. These
values do not prove physical antenna health or correct RF routing.

India was requested through normal `iw reg set IN` handling. Association to
the test AP also introduced an IE country hint, and firmware/global domains
did not remain a simple literal IN. A subsequent India hint produced an
intersection (`98`, with PHY `99`), 13 enabled 2.4 GHz channels and no 5 GHz
band. This is not evidence that the whole missing band is a DFS restriction.
Regulatory notifiers, firmware limits and the regulatory database remain active.

The DMA repair did not normalize RSSI. The user moved the Mac to 1–2 metres
from the router and confirmed that reception on this same Mac is good in
macOS. Linux still measured approximately -81 dBm. This favors a Linux
radio-configuration explanation; a simultaneous quantitative macOS comparison
was not available. Hardware damage has **not** been established.

Broadcom's read-only `phy_rssi_ant` query reported all three receive chains
weak, for example [-88, -80, -85] dBm, with GET_PHY_NOISE reporting -92 dBm.
Power saving off did not improve RSSI and was reverted. Removing the USB 3
Ethernet adapter changed mean RSSI from -81.3 to -80.8 dBm, not a meaningful
recovery. The recorded USB device remained absent through the end of sampling.
Neither test establishes a calibrated noise-floor or chamber measurement.

The user subsequently prioritized 2.4 GHz reception; 5 GHz testing was deferred.
No guessed FEM tables, donor PA values or transmit-power overrides were applied.

## Separating reception from the traffic-test path

Both Ethernet and Wi-Fi used the same LAN during early benchmarks. A scoped
packet capture found 34 Wi-Fi-bound DNS requests, with 33 replies arriving on
Ethernet instead. The Wi-Fi connected-subnet route was also missing from the
main routing table. Those failed bound requests cannot be attributed to RF.

Temporary per-interface ARP settings and an output-interface policy route
corrected the test path. DNS and verified HTTPS then passed, and local iperf3
measured 5.45 Mbps download / 5.21 Mbps upload. RSSI remained -82 dBm. These
network-path controls did not fix reception and are not installer defaults.
They were removed after the test, along with the temporary benchmark namespace.
The selected Wi-Fi profile was restricted to 2.4 GHz and autoconnect enabled;
other saved Wi-Fi profiles remain excluded from automatic use.

## Research comparison

Actual source and historical discussion were inspected, not only project claims.

| Source | Implementation / applicability |
|---|---|
| [DeyAgrO](https://github.com/DeyAgrO/macbook-pro-13-2-linux), `1d52273baa4d86f71113b4e65a181c839fce94fb` | Reports physical 13,2 signal improvement. Installer supplies generic board values, rewrites firmware country bytes and changes global networking/power policy. Its NVRAM provenance does not establish correct per-board calibration here; not installed. |
| [Bogdan7c](https://github.com/Bogdan7c/macbook-bcm43602-wifi-fix), `35dd57c5b2b0fc8f76af5c6c2a45ead010692421` | Patched driver ignores regulatory hints with fixed_regdom; default GB revision 3 and mixed board settings reportedly yield 5 GHz while breaking 2.4 GHz. Incorrect-country/regulatory suppression is unsuitable here. Read-only vendor query format was inspected. |
| [xeeban](https://github.com/xeeban/macbook-t1-linux), `982d97a61a0c834d03e7cf7af5203b11ad7bae44` | `feature_disable=0x82000` masks FWSUP and SAE in this kernel, not FWAUTH. Prior trial did not cure association; the DMA-corrected driver connects without this override. No blanket PMF or WPA3 downgrade is justified. |
| [Dunedan](https://github.com/Dunedan/mbp-2016-linux), `3da5e3f586ecd835c12d2c6a3021e66ca0934d96` | Issue 47 documents mixed community results and NVRAM derived from other boards. This is useful provenance research, not a verified calibration source for this unit. |
| [bgausden investigation](https://gist.github.com/bgausden/c7f8a3737c1e52a260dfcdb1fb2e90b2) | Describes separate suspend-related failures and requires valid original board data. Its sleep/platform changes do not explain the traced RX DMA fault; EFI, NVMe and T1 power configuration were not altered. |

Legitimate next calibration sources are an original manufacturer-provided file
for this board, or a reproducible extraction from this owner's licensed Apple/
Boot Camp installation with verified FullMAC compatibility. The documented
[Windows MMIO tracing approach](https://github.com/sonals/macbookpro14-3/blob/master/doc/MMIOTrace.rst)
requires a separate environment and was developed on a different model; it
does not provide a ready-to-install 13,2 file. Redistributability must be
established separately. No proprietary calibration is included in this project.

The final targeted attempt downloaded Apple's Boot Camp product `041-88734`,
whose distribution explicitly lists MacBookPro13,2. Its XAR RSA signature and
signed payload digests were verified, and the certificate chain was verified
against the root downloaded from Apple's official PKI page. The downloaded
package's SHA1 did not match the catalog's SHA1, so that check is not claimed
successful; independent signature verification was used for provenance.
Package SHA256:
`ace1cc6dd3bbd12e32fcf953b0f1d0ab74f4a77075fbd4733352468c5aa36f34`.

`BroadcomWirelessWin8x64.exe` was extracted without executing it. The INF
supports PCI `14e4:43ba`; both driver binaries contain BCM43602 **BMAC** images
version `7.35.118.64`. The located `boardtype=` and `boardflags=` strings are
printf format strings, not a populated calibration file. No ready-to-use
FullMAC NVRAM was identified in this package. None of these proprietary files
was installed or committed. Runtime extraction from a working vendor driver
may still be useful, but has not been implemented or validated here. The
remaining reception cause must therefore stay an unresolved hypothesis.

## Unexpected reboots during investigation

Two live unload attempts initiated by the investigation caused kernel oopses
and automatic restarts. The user confirmed these were not intentional reboots.
Both saved dumps show `_cfg80211_unregister_wdev` through P2P removal,
`brcmf_detach` and WCC module exit. A poisoned list pointer indicates a teardown
race: NetworkManager's unmanaged transition returns before supplicant finishes
deleting its P2P wireless device, while module removal can delete it again.

The corresponding proposed upstream locking fix is
[Michele Dionisio's September 24 patch](https://lists.openwall.net/linux-kernel/2026/09/24/1542).
It was reviewed as a separate issue and was not folded into this DMA patch.
The later successful unload waited until both `iw dev` showed no P2P device
and supplicant's D-Bus interface list was empty, and checked again before
unloading. The installer and uninstaller perform **no live unload**; recovery
defaults to staging on disk and using a normal reboot. No repeated reload
timer or sleep reset hook was left installed.

## Deployment and remaining acceptance gaps

`sudo ./install-wifi.sh --dma-fix --install-deps --update` integrates the repair
with the existing project. DKMS preserves the packaged stock driver, checks
exact source/header versions, rebuilds module dependencies and the current
initramfs, and retains private rollback state. Only this Wi-Fi module is
installed. No Touch Bar/audio/camera module was replaced or rebuilt.

Kernel upgrades are conditional on exact source availability within the audited
7.3.0 generic family; mismatches fail explicitly. Other kernel families and
enforced module signatures are rejected by this installer; an enrolled-key
deployment workflow is not implemented here.
Cold-boot and suspend/resume acceptance remain unverified for the new module.
The installed post-boot timer is diagnostic only.

The following are still required for full SUCCESS: trusted compatible board
data or another demonstrated RF correction, normal reception, real 5 GHz
association/802.11ac throughput, low-loss sustained service, and controlled
cold-boot/suspend validation. This partial repair must not be advertised as a
dual-band or signal-strength fix.
