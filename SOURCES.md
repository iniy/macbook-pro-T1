# Source audit and provenance — 2026-10-18

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
