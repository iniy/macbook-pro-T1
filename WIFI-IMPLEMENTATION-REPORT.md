# Wi-Fi implementation report — 2026-10-19

## Outcome

**PARTIAL / NOT FIXED: integration and recovery tooling implemented; reliable
built-in Wi-Fi, normal reception and dual-band operation are not established.**
No measured internet throughput or 30-minute connected stability is claimed.

| Milestone | Actual evidence |
|---|---|
| Driver detected | Yes: stock brcmfmac binds the exact Apple BCM43602 |
| Firmware loaded | Yes: packaged 7.35.177.61, FWID 01-ea662a8c |
| Network visible | Yes: direct 2.4 GHz scans succeed after Wi-Fi-only recovery |
| Network association successful | No verified success on original AP or nearby phone hotspot |
| IP address assigned | No Wi-Fi lease verified |
| Internet connectivity established | No Wi-Fi-bound DNS/HTTPS pass; Ethernet remains working |
| Sustained stability verified | No; association is a prerequisite |
| 5 GHz available | No 5 GHz band exposed by this firmware/board state |

## 1. Hardware and software

MacBookPro13,2 (13-inch Late 2016), BCM43602 rev 02, **14e4:43ba**,
Apple subsystem **106b:0157**. Ubuntu **26.10**, stock kernel
**7.3.0-9-generic**, matching source **7.3.0-9.9**. NetworkManager
**1.58.1-1ubuntu3**, wpa_supplicant **2:2.11-2ubuntu2**, linux-firmware
**20260915.git1522c78a.1ubuntu**, wireless-regdb **2026.05.30-0ubuntu1**.
This is evidence for one machine, not universal MacBook/Ubuntu support.

## 2. Original problems and baseline

See [reports/wifi-baseline.md](reports/wifi-baseline.md). Scanning existed but
association repeatedly failed with status 16; the card exposed only 2.4 GHz and
had abnormally weak reception. The user confirmed the original router was
beside the machine. The running firmware used its generic fallback address.
There was no conflicting Wi-Fi driver or missing required firmware binary.

## 3. Root-cause findings

**Confirmed:** the firmware/driver combination exposes no 5 GHz band, reports
very weak receive signal, fails association on two independent saved networks,
and can develop firmware command timeouts followed by commonring exhaustion.
The exact defective calibration field or firmware operation is **not proven**.

Missing/inappropriate board configuration is a strong candidate because the
generic firmware supplies fallback identity/board defaults and community reports
show large radio differences with board data. It is not sufficient evidence to
copy unverified PA/gain/antenna tables into this unit.

Independent checks:

| Hypothesis | Finding |
|---|---|
| Missing binary / wrong filename | Required Ubuntu `.bin.zst` loads and verifies against package metadata |
| Missing board NVRAM | No matching `.txt`; compatible unit-specific calibration not established |
| Missing CLM / TXCAP | Requests are optional in installed PCIe source; absence alone does not identify the fix |
| Regulatory data / country | Signed regdb present. IN accepted by firmware as IN/0; channels 12–13 enabled, no association/5 GHz repair |
| WPA2/WPA3 / PMF | Both tested profiles use WPA-PSK with default PMF; no demonstrated need to weaken security |
| Firmware handshake offload | 0x82000 trials failed, including an isolated hotspot trial under the original world domain |
| Power saving | Per-profile disable did not establish association; restored |
| MAC address | Per-profile generated stable address did not establish association; restored |
| Roaming | No successful link to roam from; roamoff not justified |
| Radio calibration / reception | Original AP around −81 dBm even when adjacent; unresolved |
| Firmware resets | Timeouts/commonring errors occurred during work; stock driver reload restores fresh scanning temporarily |
| Suspend/resume | No controlled suspend test; these errors cannot be attributed to resume |
| Driver conflicts | No wl/b43 replacement or competing Wi-Fi DKMS found |

Status 16 is not necessarily an AP rejection: `brcmf_bss_connect_done` can return
`WLAN_STATUS_AUTH_TIMEOUT` for a firmware connect failure. It is not proof of a
wrong password or mesh incompatibility.

## 4. Solutions evaluated and selected implementation

All four requested repositories were cloned and actual code/scripts/issues read.
Exact revisions and decisions are in [SOURCES.md](SOURCES.md).
The selected component uses stock brcmfmac and Ubuntu firmware, strict hardware
detection, reversible opt-in settings, private write-ahead backups, allowlisted
diagnostics, device-bound connectivity/optional LAN-throughput tests, and a
read-only post-boot verification timer.

Community NVRAM, binary country patches, foreign-country tables, patched
regulatory notifiers, wl/b43 drivers, mandatory roamoff, WPA3-to-WPA2 conversion
and PMF disabling were not adopted. No new Wi-Fi module or kernel was built.

## 5. Firmware and driver changes

**No firmware binary/calibration installation or permanent driver option change.**
Temporary brcmfmac offload trials were reversed. Wi-Fi-only module reloads
restored firmware operation after timeouts; unrelated modules were not unloaded.

The Mac's own APFS installation was inspected read-only, including its sealed
system snapshot. Its original AirPortBrcmNIC binary was recovered privately from
`IO80211FamilyLegacy.kext`. BCM43602 firmware names identify **BMAC** builds,
incompatible with Linux's **FullMAC** image/interface. The accessible Apple
text firmware resources target other chipsets. None was installed or committed.
The FileVault data volume stayed locked; no EFI/macOS/T1 setting was modified.

Read-only snapshot tool: apfs-fuse
`66b86bd525e8cb90f9012543be89b1f092b75cf3`, with a local GCC-15 include fix.
It was built only as a research userspace tool, not installed as an APFS kernel
driver. The snapshot was unmounted after inspection.

## 6. Configuration changes

Persistent installed files:

* `/usr/local/libexec/macbook-t1-wifi/check.py`
* `/usr/local/libexec/macbook-t1-wifi/country.py`
* `/etc/systemd/system/macbook-t1-wifi-country.service` — confirmed India hint
* `/etc/systemd/system/macbook-t1-wifi-verify.service`
* `/etc/systemd/system/macbook-t1-wifi-verify.timer`

Private state: `/var/lib/macbook-t1-wifi` (0700), network archive (0600).
No profile security field, shared NM file, firmware file, transmit-power override
or brcmfmac modprobe setting is installed. Temporary original-profile power,
stable-address and autoconnect edits were restored. The phone profile created
by the user through Ubuntu's UI is preserved. Correct India selection is
persistent, but does not by itself repair the radio.

## 7. Installation/lifecycle results

Actual root install, repeated install, update, uninstall and reinstall completed
successfully. Final installation selected `--country IN`; the country service
returned success and both country service and verification timer are enabled.
Backups and installed tool permissions were checked. No global networking
restart or kernel replacement was needed. Installation success is distinct
from the failed connectivity milestone.

## 8. Connectivity and band results

| Trial | Result |
|---|---|
| Original saved network, baseline | Repeated association failure; no Wi-Fi lease |
| India hint | Channels 12–13 exposed; no 5 GHz/association |
| Offload disabled (0x82000) | No association; temporary setting removed |
| Temporary 10 dBm lower transmit cap | No association; normal driver state restored by reload after automatic-reset ioctl failed |
| Stable local profile address | No association; original value restored |
| Profile power saving disabled | No association; original value restored |
| Nearby trusted 2.4 GHz phone hotspot | Visible and saved by user; checks still showed configuring/no association/no IP |
| Isolated hotspot + clean offload trial | Failed; original module parameters restored |
| Stock Wi-Fi-only recovery | Actual `iw scan` exit 0; reception/association defect persists |

No security downgrade was applied. Some later trials encountered a wedged
firmware queue, limiting their diagnostic strength; they are not proof that
each candidate could never help on different firmware/hardware.

## 9. Signal, link rate, throughput, latency and packet loss

Direct fresh scans measured the original network's strongest observed BSS at
**−81 dBm on 2432 MHz**, with other BSSs at −93 to −97 dBm. A nearby phone
hotspot was measured at **−63 dBm on 2437 MHz** in an earlier recovered scan.
These are scan RSSI values, not connected-link measurements.

After restoring the stock driver, `iw` reported **31.00 dBm transmit power**.
This is the firmware-reported value, **not measured RF output or proof that such
power is legally emitted**. No fixed/high-power setting was applied. Received
signal bars cannot be repaired by increasing the host's transmit setting.

Negotiated link speed, actual throughput, Wi-Fi latency and packet loss remain
**unavailable**, because no stable association/IP was established. No suitable
local iperf3 endpoint was identified and no external bandwidth test was run.
Ethernet internet success was never counted as Wi-Fi success.

## 10. Stability and power management

Thirty minutes of continuous connectivity could not be started: association
failed. Multiple connection attempts and post-change checks were performed.
Boot error counters are historical; a successful reload does not erase them.
The verifier counts both `brcmfmac:` and `ieee80211 phyN: brcmf_*` error forms.
An early development version missed the latter; that bug was corrected and
regression-tested before packaging. Earlier zero error counts are not relied on.

Original NM power-saving policy remains active. No battery-consumption result,
suspend/resume success, reboot reconnection or firmware-roaming result is claimed.
No unrelated ACPI/NVMe/T1 power-management changes or sleep hooks were installed.

## 11. Existing hardware impact

Touch Bar modules/service, HID bindings, Fn configuration and `skip_acpi_power=1`
passed software regression checks. Audio DKMS/module ABI, actual loaded custom
CS8409, ALSA forced software mixer and PipeWire speaker/microphone nodes pass.
Camera capture/decode passed at **640×480 and 1280×720**, 30 decoded frames each;
no recordings were retained. Apple SPI keyboard/trackpad, Bluetooth and USB
availability were checked separately. Physical key presses, listening, headphone
jack transitions and voice capture were not repeated in this Wi-Fi session.
No regression was observed in the checked functions; full physical validation
is not substituted by enumeration. Existing drivers/configurations were preserved.

## 12. Reboot and automatic startup

The post-boot timer performs read-only verification approximately two minutes
after boot. brcmfmac remains PCI-autoloaded by Ubuntu; NM saved profiles retain
autoconnect. A reboot/suspend was not initiated because no working Wi-Fi solution
was established. Boot persistence is configured, not verified after an actual
reboot. Keep Ethernet available for the next validation.

## 13. Repository and remaining limitations

Repository: existing `iniy/macbook-pro-T1`.
Baseline: `10f013d2759a945cde6a02c20e895d7f79b590ed` (clean).
Branch: **`feature/bcm43602-wifi`**. Implementation revision is recorded in the
final validation entry below. HTTPS authentication was unavailable, but the
existing SSH key authenticated successfully to GitHub after verifying host keys
against GitHub's HTTPS metadata API. The feature branch can therefore be pushed;
main is not changed or force-pushed.

The remaining blocker is a validated BCM43602 FullMAC firmware/board-data
combination for this exact Apple board, or an upstream driver/firmware repair.
Normal reception, both bands, authentication, throughput, battery impact and
post-suspend/post-reboot stability are unresolved. Broadcom manufacture or a
matching PCI ID does not make arbitrary calibration or alternative drivers valid.

Final allowlisted machine snapshot: [reports/wifi-final.json](reports/wifi-final.json).

## 14. Rollback and recovery

Run `sudo ./uninstall-wifi.sh` to remove the integration and restore unchanged
owned configuration. Retain private backups. Saved profiles and shared Ubuntu
firmware/packages are preserved. See [RECOVERY.md](RECOVERY.md) for attended
Wi-Fi-only recovery with independent Ethernet, and [wifi/README.md](wifi/README.md)
for installation, updates, diagnostic stages and optional settings.

## Final validation entry

Static, routing, transaction/privacy and hardware results are recorded in
[BUILD-REPORT.md](BUILD-REPORT.md). Commit identifiers will be recorded after
the verified implementation commit is created.
