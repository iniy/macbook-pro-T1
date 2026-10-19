# BCM43602 Wi-Fi component

**Experimental integration; reliable dual-band operation is not yet established.**
See [the current root-cause report](../WIFI-ROOT-CAUSE-REPORT.md) and
[benchmarks](../WIFI-BENCHMARKS.md). The earlier implementation report is
historical evidence from before the DMA fix.

Validated detection target: MacBookPro13,2, Apple BCM43602 revision 2,
PCI `14e4:43ba`, subsystem `106b:0157`, Ubuntu 26.10, stock
`7.3.0-9-generic` brcmfmac. Other models/releases are not claimed supported.

The optional `--dma-fix` builds a minimal RX mapping-direction quirk for this
exact PCI identity/revision from matching Ubuntu source. It restored traffic
after traced IOMMU read faults; it does not correct radio calibration or expose
5 GHz. Install with `sudo ./install-wifi.sh --dma-fix --install-deps --update`.
See [DKMS source provenance](dkms/README.md) and
[disk-only rollback](../WIFI-RECOVERY.md). Installation never unloads the live
driver. The default suite invocation below still installs diagnostics only.

## Install and verify

```bash
sudo ./install-ubuntu.sh --wifi --install-deps
./verify-wifi.sh --scan
./verify-wifi.sh --online
```

The default installer registers diagnostics and post-boot verification, checks
hardware and the Ubuntu firmware, and preserves existing radio settings. It
does not claim that installing tools fixes the firmware's missing 5 GHz band.
Use Ubuntu's Wi-Fi menu to save network credentials; do not put passwords in
commands, reports or issues. Existing profiles retain their security and
autoconnect settings. The installer neither restarts networking nor unloads
drivers. Ethernet can remain the default route during all tests.

`./verify-wifi.sh` exits nonzero unless brcmfmac, loaded firmware,
association, NetworkManager activation and an IP address are all present.
`--online` additionally requires device-bound DNS, HTTPS and zero-loss gateway
ping. A successful
Ethernet request cannot count as a Wi-Fi pass. The JSON output is allowlisted:
no MAC/BSSID, SSID, IP address, UUID, hostname, serial or password is printed.
Ordinary scan output may be cached; `--scan` waits for NM's `LastScan` timestamp
to advance and reports `fresh_scan_completed` separately.

`sudo ./verify-wifi.sh --radio` optionally adds allowlisted firmware GETs for
per-antenna RSSI, noise, chain masks, board revision and bands. Unsupported
queries are null. It performs no firmware writes. When Ethernet and Wi-Fi share
a LAN, verify return routing before interpreting device-bound failures as RF
loss; this session encountered replies returning on the wrong interface.

```bash
./verify-wifi.sh --online --stability 1800
# Only with an available, explicitly selected LAN iperf3 server:
./verify-wifi.sh --online --iperf-server LAN_SERVER_IPV4
```

The stability sampler checks every approximately 30 seconds. A stability pass
requires 30 minutes, every sample connected with working Wi-Fi DNS/HTTPS, no gateway ping loss, and
no increase in accessible kernel driver error or device-specific DMA fault
counts. It also reports the loaded module's srcversion. These are sampled checks,
not proof that no interruption occurred between samples. Failed pings and
unavailable throughput remain failures/null, never fabricated zero loss or speed.
Link rates are distinguished from two optional 10-second iperf3 measurements.
Install `iperf3` separately for that optional test. No public speed-test server
or automatic throughput traffic is used.

## Explicit options, after diagnosis

Use `install-wifi.sh` directly for Wi-Fi-specific options:

* `--country IN`: request India only while physically in India; substitute your
  actual ISO country. The stock regulatory notifier and firmware limits remain
  authoritative. There is no unrestricted domain, country-revision selection,
  country-fixing driver patch, or transmit-power override. On this machine the
  India trial did not fix association or expose 5 GHz; verify the effect before
  making it persistent.
* `--profile UUID --powersave off`: set just this saved Wi-Fi profile to NM power
  saving `2`. Useful only after evidence of power-saving-related drops/latency;
  may increase battery consumption. `--powersave on` selects `3`.
* `--profile UUID --stable-mac`: NM generates a local, stable address for this
  profile. No address from a community NVRAM file is copied. Check AP access
  policies first; this is not a universal association fix.
* `--disable-offload`: opt-in `feature_disable=0x82000`, audited against Ubuntu's
  7.3.0 source. It masks **FWSUP (bit 13)** and **SAE (bit 19)**. FWAUTH is bit 20,
  **not** bit 19. Masking SAE can remove WPA3 capability rather than implement a
  host-side replacement; use only for a justified compatibility trial. It never
  rewrites profile security. The actual trial on this system did not fix Wi-Fi.
* `--roamoff`: opt-in firmware roaming disable. It can harm mobility between APs;
  no confirmed roaming problem justified it on the tested machine.

The module's `feature_disable` parameter has sysfs permission `0` in this source:
**absence of `/sys/module/brcmfmac/parameters/feature_disable` is expected**.
Check modprobe configuration and advertised capabilities after a controlled
reload/reboot instead. `roamoff` is root-readable. Module-option changes rebuild
only the running kernel's initramfs using the existing provider. They take effect
on the next boot, without replacing the kernel.

No PMF disabling, WPA3-to-WPA2 converter, broadcom-wl/b43 installation, generic
NVRAM, binary firmware patch, roaming hook or sleep hook is a default.

## Firmware provenance and missing files

Ubuntu's `linux-firmware` package provides
`brcm/brcmfmac43602-pcie.bin` (possibly `.zst`/`.xz` compressed).
The session used package `20260915.git1522c78a.1ubuntu`, firmware
`7.35.177.61`, FWID `01-ea662a8c`. Package checksums matched.
Firmware is obtained reproducibly through Ubuntu APT, not bundled here.

The running source requests a board-qualified name first:
`brcmfmac43602-pcie.Apple Inc.-MacBookPro13,2.{bin,txt,clm_blob,txcap_blob}`,
then generic filenames. The binary is required; the PCIe NVRAM, CLM and TXCAP
requests are explicitly optional. A successful fallback can still have inadequate
board configuration. The `.ap.bin` is an AP-mode image, not a replacement STA fix.

Upstream WHENCE lists the BCM43602 binary under `LICENCE.broadcom_bcm43xx`;
it does not supply a matching generic BCM43602 `.txt` or `.clm_blob` in the
inspected package. Missing CLM alone is not proof of a missing required download.
See [SOURCES.md](../SOURCES.md) for exact research commits and rejected recipes.

Community files contain board flags, antenna paths/gains, PA tables and
calibration values, sometimes mixed from different boards. Matching the PCI ID
alone cannot validate that data. No such file is redistributed or installed.
A future board-data installation requires a legitimate dump/vendor source for
this exact board, verified provenance and Linux-firmware compatibility. Never
guess calibration values, copy another machine's address, or patch country
strings in the binary. The macOS partition was only inspected read-only.

## Reinstall, update and rollback

```bash
sudo ./install-wifi.sh            # idempotent; retains selected options
sudo ./install-wifi.sh --update   # refresh owned tools; preserves selected options
sudo ./uninstall-wifi.sh
```

To clear opt-in options, uninstall then install with the desired options.
Updates refuse later user edits. Transactions are write-ahead journaled;
rollback restores only unchanged owned files and individual modified profile
fields. Shared profiles are not replaced wholesale. A failed/incomplete
transaction must be uninstalled before retrying.

Private backups live under `/var/lib/macbook-t1-wifi` (mode 0700), including a
network-configuration archive that may contain secrets. Removed transactions
are archived alongside it. Do not upload these directories. APT-installed
shared firmware/tools remain installed on removal. Current connections are
not disconnected; restored profile fields apply at the next connection and
restored module options at the next boot.

Post-boot results: `journalctl -b -u macbook-t1-wifi-verify.service`.
The read-only timer runs approximately two minutes after boot and may correctly
fail when no saved network is available. It runs with a dynamic unprivileged
user; kernel log access can therefore be unavailable and is reported as such.
It performs no external connectivity probes, radio resets, or secret requests.

## Troubleshooting and recovery

* First distinguish detection, firmware, fresh scanning, association, IP, DNS,
  internet and sustained stability. Do not call a successful install a Wi-Fi pass.
* `status_code=16` is not proof of a bad password or an AP-generated rejection:
  this driver's connect-failure path can synthesize `WLAN_STATUS_AUTH_TIMEOUT`.
* Compare a nearby trusted 2.4 GHz hotspot with the original AP. A missing 5 GHz
  band in `iw phy ... info` cannot be repaired merely by selecting a 5 GHz SSID.
* Firmware command timeouts/commonring exhaustion need separate diagnosis;
  cached NM scans can misleadingly continue showing old networks.
* Keep independent Ethernet connected before any Wi-Fi driver recovery. On SSH,
  check the route to the peer and arrange timed rollback before disrupting it.
* Save logs privately before recovery. Immediate P2P/driver teardown caused
  kernel crashes here; use [WIFI-RECOVERY.md](../WIFI-RECOVERY.md). Do not reset T1, USB,
  audio, camera, NVMe or ACPI to recover Wi-Fi.
* Suspend/reboot are unverified until tested on the physical machine. The
  installed verifier provides a post-boot check without initiating a reboot.
