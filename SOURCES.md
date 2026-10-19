# Source audit and provenance — 2026-10-18

## 5 GHz implementation and credits — 2026-10-19

The current optional 5 GHz port is documented in
[WIFI-5GHZ-IMPLEMENTATION.md](WIFI-5GHZ-IMPLEMENTATION.md).
[CREDITS.md](CREDITS.md) consolidates the authors, projects, research and toolchain
acknowledgments. [LICENSE](LICENSE) maps the applicable component licenses.

Bogdan Korolyov / Bogdan7c's implementation at
`35dd57c5b2b0fc8f76af5c6c2a45ead010692421` is the primary reference. Its
ISC-licensed country patch informed the scoped Ubuntu patches, while its
model-matched NVRAM and GB/3 findings were physically tested and adapted here.
The upstream MIT notice is retained in `LICENSES/Bogdan7c-MIT.txt`; its global
authentication-conversion service and original installer are not installed.

The pinned NVRAM source has SHA256
`9f757ace460a40c80a32202e09d507351a8c497f2dee22ba0f8a0a5cb1aebaf7` and traces
to MikeRatcliffe's gist `9614c16a8ea09731a9d5e91685bd8c80`, history revision
`38180b6a0ce552e1a3a2826ffea2bf1f52d05e9f`, and kernel bug 193121. Its source
attribution is preserved without asserting a redistribution license for the
data. The installer fetches it separately; no calibration file or proprietary
firmware binary is included in the repository/source archive.

The full Broadcom firmware license is reproduced from Ubuntu's
`linux-firmware-broadcom-wireless` copyright file in
`LICENSES/Broadcom-firmware.txt`. Original driver copyright/SPDX headers and
the existing GPL/ISC texts remain intact. Exact kernel source is still Ubuntu
**7.3.0-9.9**. No Touch Bar or audio source was replaced by this Wi-Fi port.

The following earlier investigation entries retain their historical context.

## Wi-Fi extension — 2026-10-19

The focused follow-up is in `WIFI-2.4GHZ-ROOT-CAUSE.md`. The installed image is
owned by Ubuntu `linux-firmware-broadcom-wireless` **20260915.git1522c78a-0ubuntu1**;
the `linux-firmware` metapackage version alone is not its file provenance.
The firmware hash matched both that package's manifest and the extracted initramfs.

The follow-up re-read the four research checkouts' implementation/history and
current DeyAgrO/Bogdan7c issues and Dunedan issue 47 comments. Particularly,
Broadcom's public [`bcmdevs.h`](https://android.googlesource.com/kernel/common/+/bcmdhd-3.10/drivers/net/wireless/bcmdhd/include/bcmdevs.h)
defines `boardflags3` low bits as `FEMCTRL_SUB`, `0x100` as `FEMTBL_FROM_NVRAM`,
and `0x200` as `AGC_CFG_2G`; the community's band-switch shorthand is inaccurate.
The corresponding `wlioctl.h`/`devctrl_if/wlioctl_defs.h` document the GET-only
SROM/CIS requests used for the unsuccessful private calibration-recovery attempt.
These headers are research references, not imported RF configuration.
The inspected Android common branch resolves to
`4f750cefc34ed7fc0ba4ef8b72d28b7924c24c6e`. Downloaded source SHA256s:
`bcmdevs.h` `e98f4ba4ec58ea988bdeb6f7a8d249a2e9eab7e0b17b5085a846cf45bfaab1ce`,
`wlioctl.h` `0c9209e81265635b815d11743403e384cc1370eb51fce8b54ca37e2db70a0fc9`,
`wlioctl_defs.h` `88543776640e89938230529ecb95c80d689673190ef3bd6262b99a7230580b3c`.

| Source / exact revision | Review and decision |
|---|---|
| [DeyAgrO/macbook-pro-13-2-linux](https://github.com/DeyAgrO/macbook-pro-13-2-linux), `1d52273baa4d86f71113b4e65a181c839fce94fb` | Read README, installation/packaging scripts, NVRAM and firmware-country patch; issue #1 concerns compressed firmware. Its board calibration is not validated for this unit; binary country rewriting and transmit-power dispatcher are not adopted. |
| [xeeban/macbook-t1-linux](https://github.com/xeeban/macbook-t1-linux), `982d97a61a0c834d03e7cf7af5203b11ad7bae44` | Read Wi-Fi and sleep/resume implementation. Evaluated the stock `feature_disable=0x82000` workaround live. Corrected its bit interpretation using installed kernel source: bit 19 is SAE, not FWAUTH. Its mesh-specific and suspend conclusions are external observations, not proof about this machine. |
| [Bogdan7c/macbook-bcm43602-wifi-fix](https://github.com/Bogdan7c/macbook-bcm43602-wifi-fix), `35dd57c5b2b0fc8f76af5c6c2a45ead010692421` | Initially researched during the 2.4 GHz investigation; later became the primary 5 GHz reference after the owner changed priorities. The board data, GB/3 findings and country-patch concept were adapted and tested; the global SAE-to-PSK conversion service was not adopted. See the current section above for licensing and deployment. |
| [Dunedan/mbp-2016-linux](https://github.com/Dunedan/mbp-2016-linux), `3da5e3f586ecd835c12d2c6a3021e66ca0934d96` | Hardware compatibility context; read Wi-Fi issues #47, #131, #172, #196, #201, #212 and #213 and relevant comments via GitHub API. Reports explicitly conflict on dual-band support and board calibration provenance. |
| Ubuntu `linux-source-7.3.0` **7.3.0-9.9** | Examined actual `brcmfmac/{pcie,firmware,feature,common,dmi,cfg80211,vendor}.c` and `feature.h`. Subsequently traced the RX DMA fault, developed a narrow quirk and compiled/deployed an exact-source DKMS module; see WIFI-ROOT-CAUSE-REPORT.md. PCIe NVRAM/CLM/TXCAP requests are optional; `feature_disable` has no readable sysfs file; the driver can synthesize association status 16 on failure. |
| Ubuntu `linux-firmware` **20260915.git1522c78a.1ubuntu** | Installed compressed BCM43602 firmware verified against package metadata. Binary **7.35.177.61**, FWID **01-ea662a8c**; no binary changes or firmware redistribution. Upstream [WHENCE](https://gitlab.com/kernel-firmware/linux-firmware/-/blob/main/WHENCE) identifies `LICENCE.broadcom_bcm43xx`. |

Authoritative references reviewed:

- Apple's Software Update catalog, using the model-distribution selection
  described in [Brigadier](https://github.com/timsutton/brigadier), selected
  Boot Camp `041-88734` for this Mac. Its extracted wireless payload was
  inspected privately, never executed or redistributed. XAR signature and
  signed payload hashes were verified using the official
  [Apple PKI root](https://www.apple.com/certificateauthority/); see the
  root-cause report for the catalog-hash discrepancy and firmware findings.

- [Broadcom public wlioctl structures](https://android.googlesource.com/kernel/common/+/c4651bd65550ab73d9027935acec7a25515263ff/drivers/net/wireless/bcmdhd/include/wlioctl.h)
  define the versioned per-antenna RSSI response used by `wifi/radio.py`.
  [Command definitions](https://android.googlesource.com/kernel/common/+/bcmdhd-3.10/drivers/net/wireless/bcmdhd/include/devctrl_if/wlioctl_defs.h)
  identify GET_REVINFO (98), GET_PHY_NOISE (135) and GET_BANDLIST (140).
  This component sends only allowlisted GETs through the existing vendor API.
- [Linux IP sysctl documentation](https://docs.kernel.org/networking/ip-sysctl.html):
  temporary `arp_ignore=1` / `arp_announce=2` constrained the dual-interface
  benchmark path. These settings were reverted and are not installer defaults.
- [Apple wireless interference guidance](https://support.apple.com/en-us/102319)
  and [Intel's USB 3 interference paper](https://www.usb.org/sites/default/files/327216.pdf)
  motivated the brief physical adapter-removal comparison. It did not restore
  reception on this Mac.

- [Linux wireless brcm80211 documentation](https://wireless.docs.kernel.org/en/latest/en/users/drivers/brcm80211.html): BCM43602 is supported by brcmfmac; some historical EFI-NVRAM guidance is superseded by the actual current source.
- [NetworkManager wireless settings](https://networkmanager.dev/docs/api/latest/settings-802-11-wireless.html): power saving `0/1/2/3`, stable MACs, band/BSSID locks, and the distinction between advertised rates and actual throughput.
- [NetworkManager wireless security](https://networkmanager.dev/docs/api/latest/settings-802-11-wireless-security.html): PMF and WPA/WPA3 semantics. No security fields are modified.
- [Kernel bug 193121](https://bugzilla.kernel.org/show_bug.cgi?id=193121): direct access returned an anti-bot page; its content was **not** independently read. Related quoted evidence was read in the GitHub issues above and is identified as secondary evidence.

Research checkouts/raw journals stay outside the repository. No community
calibration data, Apple firmware, saved network credentials or machine identifiers
are committed to the repository or portable archive. The optional 5 GHz installer
fetches its pinned board data separately. New Wi-Fi packaging/documentation is
MIT. The bundled exact Ubuntu brcmfmac source retains ISC licensing; see
wifi/dkms/README.md and wifi/dkms/LICENSE.ISC.

For original-board-data research, Ubuntu libfsapfs **20240429-2ubuntu2** inspected
the APFS container read-only. A locally built read-only `sgan81/apfs-fuse` then
accessed the sealed system snapshot at revision
`66b86bd525e8cb90f9012543be89b1f092b75cf3` (lzfse submodule
`e634ca58b4821d9f3d560cdc6df5dec02ffc93fd`). One missing `<cstdint>` include
was added locally for GCC 15. No APFS
kernel module or write-capable mount was used. Recovered Apple resources remain
root-only outside Git. BCM43602 strings in the original AirPortBrcmNIC identify
BMAC builds; they were not installed as Linux FullMAC firmware.

## Audio and camera extension — 2026-10-19

| Source / pinned revision | Use and review |
|---|---|
| [davidjo/snd_hda_macbookpro](https://github.com/davidjo/snd_hda_macbookpro), `89b22ff90b86468b186706861dd18663562defa7` | Selected GPL audio implementation. Six required Apple CS8409 headers, license and documentation are vendored in `audio/upstream/`. Model subsystem `106b:3600` selects the existing SSM3515 sequence and CS42L83 jack path. `INTERNAL_MIKE_ONLY` enables upstream's capture fix for output-only headphones; it is not a claim of tested headset-mic support. |
| Ubuntu `linux-source-7.3.0`, package **7.3.0-9.9** | Exact source corresponding to the running `7.3.0-9-generic` headers. The required HDA C/header subset and GPL license files are bundled in `audio/kernel-source/7.3.0-9.9/`. Obtained through authenticated Ubuntu apt metadata. No mainline or older-kernel substitute is used. |
| [xtocdra/macbookpro13-2](https://github.com/xtocdra/macbookpro13-2), `177bd2d947adf8ecc95c3c72fd2fcd6f3748abbd` | Model-specific context for davidjo audio and standard `uvcvideo` on T1. Its whole-device rebind and Arch-specific setup were not adopted. |
| [moabdrabou/macbook-pro-2017-linux-guide](https://github.com/moabdrabou/macbook-pro-2017-linux-guide), `e8d3131abf520745673d5244dd018eb99e697c47` | Reviewed duplex-profile guidance. Its unrelated-kernel source substitutions, replacement kernel and PCIe FaceTime driver instructions do not fit this machine/evidence and were not used. |
| [standardagents/t1bridge](https://github.com/standardagents/t1bridge), `81cbdf81026a16e02f0bea74735c6b029a8ffae2` | Reviewed UVC H.264 descriptor implementation, package boundaries and camera issue #20. That work handles USB configuration 2. This project's existing configuration 1 provides MJPEG through stock UVC and passed capture/Firefox testing, so no T1Bridge code or Arch packages were installed or vendored. |

`audio/SOURCE-SHA256.json` records the pinned vendored inputs and patch.
`audio/patches/0001-apple-cs8409-ubuntu-7.3.patch` adapts davidjo's probe hook,
Apple auxiliary structures and per-codec fields to the actual Ubuntu 7.3 header.
It preserves new upstream fields, including `speaker_muted` and side-codec
component state, and leaves shared HDA structures untouched. Amplifier gain,
register sequences and channel mapping remain the selected upstream code.
The existing Touch Bar C source is unchanged.

Relevant reviewed upstream evidence:

- davidjo issues [#193](https://github.com/davidjo/snd_hda_macbookpro/issues/193)
  and [#205](https://github.com/davidjo/snd_hda_macbookpro/issues/205): compiling
  against mismatched HDA structure layouts can build successfully and then
  crash during probe/mixer operations. Exact source selection is mandatory.
- [#206](https://github.com/davidjo/snd_hda_macbookpro/issues/206): the live
  subsystem check supports `106b:3600`; a commented historical quirk is not the
  active hardware gate.
- [#211](https://github.com/davidjo/snd_hda_macbookpro/issues/211): unresolved
  individual SSM3515 speaker/TDM behavior on 13-inch models. This integration
  does not introduce speculative slot/register changes or claim four-driver
  acoustic validation.
- [#29](https://github.com/davidjo/snd_hda_macbookpro/issues/29), PRs #218/#219,
  and the selected commit: microphone/jack concurrency remains an upstream
  concern. Wired insertion/removal was not tested locally because headphones
  were unavailable. Unreviewed PR code was not merged wholesale.
- T1Bridge [#20](https://github.com/standardagents/t1bridge/issues/20): H.264
  enumeration alone does not establish browser compatibility. Local camera
  acceptance here uses actual MJPEG decoding and Firefox frame presentation.

The kernel-derived code remains GPL-2.0/GPL-2.0-or-later as marked in its
original headers; davidjo's GPL license is retained. New integration and
diagnostic code follows the root MIT license. No Apple firmware, calibration
data, proprietary binaries, raw recordings or machine identifiers are shipped.

All four requested repositories were cloned with history into `sources/` on
Monterey and inspected without running their installers. Those audit checkouts
remain local; the portable archive contains the selected source and patches.

| Repository / pinned revision | Findings and selection |
|---|---|
| [AJ-dev-i60/t1-touchbar](https://github.com/AJ-dev-i60/t1-touchbar), `20d65c7b0fe6d05ea9734f869b27384a62de5109` | Selected roadrunner2/t2linux-derived T1 fork. Actual code fixes HID child descriptor parsing, bounds collection slots by child ID, supports mode-only T1 activation and SPI Fn input, and guards probe/suspend/resume SOCW calls. June 30 commits introduce the firmware-driver package and strengthen the guard (`894fe5e`); July 1 splits experimental userspace rendering out. README reports Ubuntu 26.04/7.0.0-27 on 14,3. Issue #2 reports working controls and webcam on **13,2**, Ubuntu-24.04-based Mint/7.0.0-38. This is external evidence, not validation of our machine. |
| [Phennova/apple-touchbar-driver](https://github.com/Phennova/apple-touchbar-driver), `d6e40d1f2f8ce1fc999cffd3513a8c5af27d0555` | Different older MFD/ACPI subdriver architecture (`apple-ib-tb`, ALS). April functional work targets Arch 6.18/6.19 and 13,3; September commits mostly copyright/headers. README explicitly says other models are unverified. Actual probe, suspend and resume invoke SOCW unconditionally; no `skip_acpi_power` safeguard. Installer removes older packages, edits mkinitcpio, and rebinds the entire USB device. Not selected. No open issues at audit time is not evidence of reliability. |
| [DeyAgrO/macbook-pro-13-2-linux](https://github.com/DeyAgrO/macbook-pro-13-2-linux), `1d52273baa4d86f71113b4e65a181c839fce94fb` | Two June 10 commits; predominantly Wi-Fi packaging. Touch Bar extra fetches moving HEAD of `parport0/mbp-t1-touchbar-driver`, not pinned vendored source. Attachment script hardcodes interfaces `:1.2`/`:1.3`, suppresses errors, and rebuilds initramfs. Open issue #1 concerns Wi-Fi compression, not Touch Bar. Useful model-specific context; insufficient reproducibility/freeze protection for this package. |
| [t2linux/apple-ib-drv](https://github.com/t2linux/apple-ib-drv), branch `mbp15`, `4afd30950a7364b06b8cef8a34d6cc6653ca3120` | Upstream lineage, primarily advertised for T2/2018+. Last branch update January 2025 adds newer Touch Bar/API handling. Actual T1 code still indexes a two-element `sub_hdevs` array by raw collection index and executes SOCW unconditionally. Open PR #11 documents resulting T1 teardown memory corruption, tested externally on 13,2/7.0.10. AJ already includes bounded slot indexing. PR #10 proposes upstream cleanup; #8 install instructions; #4 keyboard lighting; #3 ALS warning. Not used directly. |

## Relevant open AJ issues/PR

- [PR #1](https://github.com/AJ-dev-i60/t1-touchbar/pull/1), pinned head
  `a33c7eb27777339c047b8f532d1e6baebaec46bd`: included verbatim as patch 0001.
  Submitted by Eugene Ray, with investigation/implementation attributed to OpenAI Codex.
  Normalizes a one-byte USB transfer success to zero, registers ordinary resume,
  accepts absent optional interfaces on resume, and avoids suppressing T1 keys
  based on the no-op display cache. External hardware test: 13,3, Arch 7.2.3,
  s2idle and controlled reset-resume; not 13,2/Ubuntu 26.10.
- [Issue #2](https://github.com/AJ-dev-i60/t1-touchbar/issues/2): 13,2 dimming/idle
  settings ineffective. Confirmed source-level reason: `appletb_set_tb_disp()`
  returns success without issuing a display command for T1. We explicitly disable
  these timers; no speculative display protocol was added.
- [Issue #4](https://github.com/AJ-dev-i60/t1-touchbar/issues/4): dark after S3 on
  14,3 with the guard enabled. Proposed independent SOCW sleep/wake path is not
  included because it bypasses the required safeguard. Boot and sleep reliability
  therefore cannot be promised for this Mac before physical testing.

Closed [report #3](https://github.com/AJ-dev-i60/t1-touchbar/issues/3) additionally
confirms 14,3 / Ubuntu 26.04.1 / 7.0.0-38 after a cold boot. It reports firmware
loss after an Ubuntu installer removed `EFI/APPLE/EMBEDDEDOS`, Fn interception by
keyd, and usbmuxd rules using `ENV{PRODUCT}=="5ac/...|5ac/8600/*"`. Our full-rule
override guard also handles that spelling; no firmware-revival tools are run.

## Local patches

Applied in numerical order to the selected upstream checkout:

1. `0001-upstream-t1-resume.patch`: reviewed upstream PR, byte-identical resultant
   `apple-touchbar.c` to the pinned PR head.
2. `0002-guard-and-hid-slots.patch`: default `skip_acpi_power=1` and reject other
   values before ACPI lookup; retain guarding at all three SOCW sites. Fix
   `appleib_set_open()` to use the assigned child vendor/product slot rather than
   the first vacant slot. ALS can be created in slot 1 before Touch Bar slot 0;
   the old heuristic marks slot 0 open and can dereference a NULL child. Raw-event
   forwarding now checks the published child pointer. Ignore expected nested
   non-application collections when producing unknown-collection warnings.
3. `0003-dkms-package.patch`: unique package `macbook-t1-touchbar/1.0.0`, explicit
   Ubuntu compiler command, and tested kernel-family restriction.

Upstream already contains the 6.11 platform-remove and 6.12 const report-fixup API
guards and virtual HID descriptor fix. Compilation against Ubuntu **7.3.0-9**
required **no additional guessed kernel API changes**.

The native sanitizer test extracts the actual changed C functions and exercises
ALS-first discovery, the interval before publication, normal close/forwarding and
unknown IDs. It is not a substitute for kernel concurrency/hardware testing.

## Binding, firmware and licensing

`apple_ibridge` binds platform ACPI **APP7777**, registers physical HID handling
for **05ac:8600**, and exposes virtual **1d6b:0301** Touch Bar and **0302** ALS
children. Only the iBridge and Touch Bar modules are built. Touch Bar mode uses
the T1 vendor USB control transfer; input is standard Linux key events. SPI
keyboard matching observes `KEY_FN` from the existing `applespi` driver.

USB configuration 1 includes UVC webcam interfaces. Packaging sets that
configuration at device addition, avoids whole-device resets, and limits late
binding to matching physical HID nodes. This behavior still needs physical
webcam coexistence validation. Apple firmware is neither downloaded nor shipped.

Driver source and included driver changes: **GPL-2.0**, copyright retained in
source and `driver/LICENSE`. Resume patch credits remain in its upstream commit.
New installer, diagnostics, tests and documentation: **MIT**, see root `LICENSE`.
Upstream driver source is provided in full; no unsigned prebuilt module is used
as a substitute for building the installed kernel's ABI.

## Ubuntu target evidence

- [Official stable images](https://releases.ubuntu.com/26.10/)
- [Desktop manifest](https://releases.ubuntu.com/26.10/ubuntu-26.10-desktop-amd64.manifest)
  retained in `reports/research/ubuntu-26.10-desktop.manifest`:
  `linux-image-7.3.0-9-generic` / headers **7.3.0-9.9**.
- [Released cloud image](https://cloud-images.ubuntu.com/releases/stonking/release/)
  used for the isolated Ubuntu 26.10 build guest; official SHA256SUMS checked over
  HTTPS. The older 24.04 image initially downloaded was not used for target tests.
