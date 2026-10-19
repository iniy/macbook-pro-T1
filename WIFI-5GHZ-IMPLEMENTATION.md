# BCM43602 5 GHz Ubuntu implementation

Target: MacBookPro13,2, BCM43602 `14e4:43ba`, revision 02, Apple subsystem
`106b:0157`; Ubuntu 26.10, kernel `7.3.0-9-generic`, exact source `7.3.0-9.9`.
Branch: `feature/bcm43602-5ghz-ubuntu`, based on `1fa0fc8`.

## Reference and adaptation

Reference: Bogdan7c/macbook-bcm43602-wifi-fix commit
`35dd57c5b2b0fc8f76af5c6c2a45ead010692421`. Its scripts, DKMS configuration,
country patch, NVRAM, vendor-query tool and authentication service were reviewed.
Its installer was not executed. Its performance figures describe a different
machine/router and are not our benchmarks.

The Ubuntu build preserves the already-required, hardware-scoped RX DMA fix
from `117774d16b23162907b8500d79698ef11ca0aa0a`. It uses the bundled matching
Ubuntu source and headers rather than deriving a mainline tag from `uname`.
Only brcmfmac is installed; stock brcmutil/vendor modules remain in place.

The optional patches in `wifi/5ghz/patches/` implement:

1. A default-off, exact-device country-hint guard. Unlike the reference's
   unconditional return, explicit user country requests retain their normal path.
2. An opt-in legacy 80 MHz mode. This firmware's tested `IN/0`–`IN/6` selections
   supplied no 80 MHz chanspecs, despite `bw_cap=7` and `vhtmode=1`. The mode uses
   the reference GB/3 capability table while cfg80211 uses physical country IN.
   The firmware normalizes its returned country abbreviation to GB; this is
   recorded honestly rather than misreported as a literal IN firmware table.
   Conflicting AP country hints are ignored, explicit user requests are handled,
   channels are limited to the non-DFS **36–48** block, and a **17 dBm conducted
   power request** is applied without Broadcom's power-override bit. This is a
   firmware control/readback, not a measurement of radiated power.
3. A PCIe diagnostic reporting the selected board-data filename and byte count.
   Calibration contents and hardware addresses are not logged.

All these options default off. The DMA repair remains narrowly gated to this
PCI/subsystem/revision. No whole kernel, EFI, T1, audio or camera replacement is
part of this component. The legacy mode does not provide all possible 5 GHz
channels; the tested router uses channel 48.

## Firmware and board data

The Ubuntu station binary is unchanged: **7.35.177.61**, FWID **01-ea662a8c**.
Uncompressed SHA256:
`bf4cfc23ee952a3d82ef33a0f5f87853201c98f1bed034876a910f354f37862d`.
Its owning package is `linux-firmware-broadcom-wireless`.

The model-matched reference NVRAM was actually tested on this physical board.
Its source SHA256 is
`9f757ace460a40c80a32202e09d507351a8c497f2dee22ba0f8a0a5cb1aebaf7`.
The source traces to MikeRatcliffe's gist and kernel bug 193121. It is community
board data, **not a recovered unit-specific factory calibration**. Its exact RF
tables are retained; no PA, gain, chain or boardflag values are fabricated.
The file's `boardflags3=0x300` selects front-end/gain behavior, not a universal
band-enable register. Reusing the earlier generic defaults alone exposed no
5 GHz band on this machine.

The installer fetches the pinned file (or accepts a checksum-matching offline
copy), preserves the current device-reported MAC, and writes `ccode=IN, regrev=0`.
The opt-in driver mode selects the legacy capability table at initialization.
The genuine factory MAC remains unverified; no replacement address is invented.
No proprietary firmware/calibration file is committed to Git. No unrelated
CLM/TXCAP file is installed. Ubuntu's default firmware filenames remain intact;
the new component uses an isolated `alternative_fw_path`.

## Deployment interface

```bash
sudo ./wifi/install-5ghz.sh --activate
sudo ./wifi/verify-5ghz.sh
sudo ./wifi/benchmark.sh --band 5 --seconds 180 --iperf-server LAN_SERVER_IPV4 --output /var/tmp/wifi-5g.json
```

`--activate` requires and verifies independent Ethernet, waits for supplicant's
interface list and the P2P wireless device to disappear before a Wi-Fi-only
driver unload, and checks the loaded DKMS srcversion. Without it, installation
stages files for reboot. This avoids the P2P teardown race observed in earlier
investigations. An installed original DMA provider is retired before installing
the combined provider; two DKMS packages do not compete for brcmfmac.

The new saved profile is **5 GHz-only**, autoconnect priority **100**. The
existing 2.4 GHz profile is retained as a lower-priority fallback. Priority
applies when NetworkManager selects a connection; it is not an uninterrupted
cross-band handoff guarantee. Advertising 2.4 GHz does not establish successful
2.4 GHz authentication with this reference board data.

No global WPA3-to-WPA2 service is installed. The selected existing WPA2 profile
is cloned without changing its encryption fields. A WPA3-only profile is rejected
rather than silently downgraded. `feature_disable=0x82000` and `roamoff=1` are not
blanket defaults: the successful trials did not require them.

## Ownership, updates and recovery

The physical deployment completed successfully. The installed and loaded
brcmfmac srcversions both read `F5DC7E010E1E84F8F1F1231`. The kernel reports:
`board data macbook-t1-5ghz/brcm/brcmfmac43602-pcie.txt (6048 bytes)`.
The active connection is channel 48, 80 MHz, with a 17 dBm power-control
readback and approximately −58 dBm RSSI at the post-install check.
Gateway ping, device-bound DNS and HTTPS passed. The existing audio and Touch
Bar DKMS registrations remain installed; only the old Wi-Fi DMA registration
was replaced by the combined provider.

* DKMS: `macbook-t1-wifi-5ghz/1.0.0`.
* Source: `/usr/src/macbook-t1-wifi-5ghz-1.0.0`.
* Firmware directory: `/usr/lib/firmware/macbook-t1-5ghz/brcm/`.
* Module options: `/etc/modprobe.d/macbook-t1-wifi-5ghz.conf`.
* Early-boot firmware inclusion: `/etc/dracut.conf.d/90-macbook-t1-wifi-5ghz.conf`.
* Helpers: `/usr/local/libexec/macbook-t1-wifi-5ghz/`.
* Country/verification units: `/etc/systemd/system/macbook-t1-wifi-5ghz-*`.
* Private journal/backups: `/var/lib/macbook-t1-wifi-5ghz/` (0700).

DKMS rebuilds within the audited Ubuntu 7.3.0 generic family using matching
source/header versions. Other families or source mismatches fail explicitly.
Signature enforcement is never disabled. Enforced Secure Boot requires an
enrolled-key deployment; this machine's unenforced configuration was preserved.

Installation is repeatable, checks file/source ownership, preserves the old
module and initramfs, and arms independent timed and first-boot recovery.
See [recovery](WIFI-5GHZ-RECOVERY.md) and
[actual measurements](WIFI-5GHZ-BENCHMARKS.md).

The preserved 2.4 GHz profile was tried once under a timed 5 GHz restoration
watchdog. It failed to associate within the bounded test and reported status 16;
the 5 GHz connection was restored immediately. Thus profile fallback is
configured, but **working 2.4 GHz fallback is not established** with this NVRAM.
No password or encryption downgrade was attempted.

## Finalization and licensing

The owner accepted the working 5 GHz connection and stopped further experiments.
The runtime rollback timer was cancelled after live verification. The original
boot image/module backups and first-boot recovery were retained. Because module
firmware metadata does not name a custom `alternative_fw_path`, an owned dracut
configuration explicitly includes both the station binary and NVRAM in the
initramfs. Their presence in the rebuilt boot image was verified without a
driver reload or reboot.

38 Wi-Fi regression/unit checks passed, including compiled tests of the actual
country guards, normalized firmware-country readback, channel/power limits and
edit-aware recovery. Exact-source DKMS compilation, live activation and the
installed/loaded module match were verified. Extended 30-minute and boot/resume
acceptance remain untested at the owner's request.

Complete upstream credits and license boundaries are in [CREDITS.md](CREDITS.md)
and [LICENSE](LICENSE). Original GPL/ISC source notices are retained, and the
Bogdan7c MIT and Broadcom firmware notices are included in `LICENSES/`.

`sudo ./install.sh` is the complete suite entry point for Touch Bar, audio,
camera, this 5 GHz component, and the requested GNOME desktop preferences.
Its repeat run on this machine preserved the working driver installations.
