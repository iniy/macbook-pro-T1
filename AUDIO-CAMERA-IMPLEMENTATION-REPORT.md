# Audio and camera implementation report

Date: **2026-10-19**. Overall result: **PARTIAL — working components installed;
headphone, reboot and suspend acceptance remain incomplete.**

## 1. Hardware/software baseline

- MacBookPro13,2; Intel i5-6267U, nominal 8 GB RAM; Ubuntu 26.10 amd64.
- Running/retained kernel **7.3.0-9-generic**, headers/source package **7.3.0-9.9**.
- HDA controller **8086:9d70**; CS8409 codec **1013:8409**, codec subsystem
  **106b:3600**, revision **00100100**.
- This subsystem selects davidjo's **SSM3515** amplifier path and **CS42L83**
  headphone/jack path. This is model/subsystem and source evidence; no separate
  physical chip-ID probing or speculative amplifier-register experiment was done.
- Initial stock codec exposed analog playback/capture, but lacked Apple's
  amplifier/sub-codec initialization and meaningful headphone detection.
- PipeWire **1.6.8**, WirePlumber **0.5.17**, dracut **112-7**, DKMS **3.2.2**.
- T1 USB **05ac:8600**, existing USB configuration 1, two UVC and two HID
  interfaces. Camera capture and metadata nodes already existed with `uvcvideo`.
- Existing `macbook-t1-touchbar/1.0.0` and both Touch Bar modules were working;
  the baseline repository verifier passed. Its C source was preserved.
- Apple EFI has no Secure Boot support; kernel signature enforcement is off.
  New module signatures were still cryptographically verified before loading.

The baseline is local and redacted. Public reports contain no serials, host
identifiers, network addresses, account paths, recordings or credentials.

## 2. Implementations and pinned provenance

| Input | Exact revision |
|---|---|
| Existing project base | `36f31c8592c90b88aab1175e89d29f64eb9c3695` |
| davidjo/snd_hda_macbookpro | `89b22ff90b86468b186706861dd18663562defa7` |
| xtocdra/macbookpro13-2 | `177bd2d947adf8ecc95c3c72fd2fcd6f3748abbd` |
| moabdrabou/macbook-pro-2017-linux-guide | `e8d3131abf520745673d5244dd018eb99e697c47` |
| standardagents/t1bridge | `81cbdf81026a16e02f0bea74735c6b029a8ffae2` |
| Ubuntu kernel source | `linux-source-7.3.0=7.3.0-9.9`, authenticated Ubuntu apt package |

Only davidjo's required GPL source and the exact Ubuntu HDA source subset were
vendored. T1Bridge's H.264/configuration-2 override was reviewed but unnecessary:
configuration 1's MJPEG path works through the stock UVC module. The old PCIe
FaceTime driver, replacement T1 stacks, Arch packages and replacement kernels
were not installed. Licenses and detailed issue review are in `SOURCES.md`.

## 3. Code and configuration changes

- Added `audio/` with pinned driver inputs, per-file hashes, exact-source build
  preparation, scoped DKMS/signing, software-mixer policy, verification and
  bounded playback/microphone/browser diagnostics.
- Adapted the Apple CS8409 probe/header additions to Ubuntu 7.3. The initial
  upstream header patch rejected changed context; the adaptation preserves
  current kernel fields and uses the exact shared HDA structure definitions.
  Amplifier registers, gain sequence and channel mapping are unchanged.
- Enabled upstream `INTERNAL_MIKE_ONLY` for its output-only-headphone capture
  path. This does not establish headset-mic or hot-jack capture reliability.
- Added `camera/` for dynamic T1 USB ancestry/capture-node discovery, metadata
  checks, memory-only frame decoding and an attended Firefox preview test.
- Added independent `install-*`, `verify-*`, `uninstall-*` audio/camera scripts.
- Added unified selectors `--touchbar`, `--audio`, `--camera`, `--all`,
  `--verify`, `--uninstall`, retaining legacy Touch Bar-only invocation and
  `--install-deps`. Repeated matching installs preserve live modules.
- Shared file transactions gained an opt-out for usbmuxd-rule handling so
  audio and verification deployment cannot rewrite shared T1 rules.
- Added a read-only post-login verification unit/runtime for `--all`.
- Updated documentation, regression tests and the portable source package.

Installed audio paths include `/usr/src/macbook-t1-audio-1.0.0/`,
`/var/lib/dkms/macbook-t1-audio/1.0.0/`, the kernel's `updates/dkms` module,
`/etc/wireplumber/wireplumber.conf.d/51-macbook-t1-audio.conf` and
`/etc/dkms/framework.conf.d/zz-macbook-t1-audio.conf`.
Audio ownership/backups are in `/var/lib/macbook-t1-audio/` and signing material
in root-only `/var/lib/macbook-t1-audio-signing/`.
Camera registration is in `/var/lib/macbook-t1-camera/`; no camera module is
replaced. Shared verification ownership is `/var/lib/macbook-t1-suite/`.

## 4. Commands and compilation

Principal installation/build commands (administrative authentication omitted):

```bash
git switch -c feature/ubuntu-audio-camera
sudo apt-get install --no-remove -y v4l-utils ffmpeg pulseaudio-utils linux-source-7.3.0=7.3.0-9.9
make -C audio KVERSION=7.3.0-9-generic -j2
sudo ./install-audio.sh --install-deps
sudo ./install-camera.sh --install-deps
./verify-ubuntu.sh
./verify-audio.sh
./verify-camera.sh --capture
python3 audio/safe-playback.py --muted
python3 audio/safe-playback.py --volume-percent 10
python3 audio/microphone-test.py --seconds 8
python3 camera/browser-test.py
python3 audio/browser-test.py --fresh-profile
```

Both CS8409 compilation units compiled; modpost/link succeeded. Vermagic is
`7.3.0-9-generic SMP preempt mod_unload modversions`.
Installed/loaded audio `srcversion`: **`0319A4246601B03B6D98361`**.
Optional BTF generation was skipped because the header environment lacks
vmlinux/pahole. DKMS built/signed/installed **macbook-t1-audio/1.0.0** and
archived the stock codec for uninstall. The installed compressed module's
PKCS#7 signature passed verification against its package-scoped certificate.
No firmware enrollment was requested. Dracut rebuilt the existing initramfs.

Activation stopped desktop audio and unbound only the identified HDA codec,
then unloaded the stock CS8409 module and loaded the signed custom module.
ALSA changed from `CS8409 Analog` to `CS8409/CS42L83 Analog`. Desktop audio
was restarted and muted before any playback. T1 USB and its drivers were not
unbound, reset, replaced or reloaded.

## 5. Hardware evidence

| Component/test | Actual result |
|---|---|
| Internal speakers | Brief left/right speech through PipeWire was confirmed by the user as **both correct and clean** |
| Volume/mute path | Actual card/node software-mixer settings verified; muted volume changes changed `softVolumes` while ALSA mixer controls stayed unchanged; muted playback transport completed |
| Normal playback attenuation | Found stale **−26.6 dB** in Ubuntu's separate ALSA `PCM Playback Volume` software layer; normalized it to **0 dB while PipeWire was muted** |
| Headphone output/switching | CS42L83 path and jack/port enumeration present; **not physically tested**, because the user had no wired headphones |
| Internal microphone | PipeWire captured real samples; correcting its accidental 2% software level removed about 102 dB attenuation. A spoken-test capture peaked at **−25.67 dBFS**, RMS **−45.31 dBFS**, with **zero clipped samples** |
| Browser microphone | Existing Firefox initially returned `NotFoundError` after audio reload; audio-record permission and default source were correct. The isolated process provided user-controlled recording/replay; the user stated **the recording is fine**, but replay was too quiet |
| Camera formats | Stock UVC advertises MJPEG 640×480 and 1280×720 with 1–30 fps intervals |
| Camera actual capture | Initial 30-frame MJPEG capture decoded successfully; final reopen tests decoded 30 frames each at 640×480 and 1280×720, with 30 and 25 distinct reduced frames respectively. No image/recording was retained |
| Firefox camera | `getUserMedia` produced **30 presented frames at 1280×720**; user confirmed a live preview |
| Touch Bar regression | Repository checks passed after audio installation/activation/policy correction and camera captures. User's final confirmation covered illumination, Esc, Fn/function, brightness and volume controls |
| Keyboard/trackpad/USB | User confirmed keyboard/trackpad still work; existing registrations and USB bindings preserved; no whole-iBridge operation performed |
| Normal application playback | After removal of stale PCM attenuation, user selected **Controls and playback work**; ordinary application audio was confirmed usable |

The microphone page's explicit Confirm callback was not received before its
timeout; the voice result above is the user's direct observation, not a
fabricated browser callback. The initial CLI record/replay timing was difficult
for the user, motivating the click-to-start browser tool.

Diagnostic replays intentionally normalize signal peak to **5%** (about
−26 dB), and initial output tests use low software volume. The user found this
replay feeble even with the desktop at maximum. Inspection confirmed ALSA,
PipeWire and Firefox at unity; the test-page attenuation remained. A bounded
2.5–10% peak replay control was added. Maximum normal-application loudness and
individual tweeter/woofer output are **not** established by these quiet tests.
Normal application playback was separately confirmed usable at the end of the
session. Handoff set ordinary output to 50% unmuted, input to 100%, and the
extra ALSA software PCM layer to 0 dB; diagnostic attenuation does not apply to
ordinary applications.

## 6. Corrections and remaining limitations

**Working with hardware evidence:** internal stereo speakers and usable normal
playback, microphone recording, FaceTime HD capture/Firefox preview, and the
preserved Touch Bar/keyboard/trackpad controls.

**Partially verified:** headphone/jack support is installed and enumerated;
startup persistence is configured and its checker is tested within this boot.
Neither has completed its physical post-reboot/jack acceptance tests.

**Demonstrated nonworking after corrections:** none of the tested hardware
components. The original Firefox process failed microphone enumeration after
the audio reload, and the isolated diagnostic's confirmation callback timed
out; these application/test limitations are distinguished from the user's
successful microphone-recording observation.

1. Rebased the CS8409 header additions rather than forcing a mismatched patch
   or substituting a different kernel source.
2. Corrected WirePlumber matching: `alsa.components` is available on nodes
   after creation; the card rule now matches the actual PCI hardware IDs so
   `api.alsa.soft-mixer=true` applies before ACP opens it.
3. Corrected verification: pipewire-pulse's `HW_VOLUME_CTRL` flag is not proof
   of amplifier control. Verification now checks the actual card/node mixer
   properties, corroborated by observed software-gain changes.
4. Excluded sink-monitor sources from microphone verification.
5. Set an independent unity input default. WirePlumber otherwise fell back to
   the quiet output default for the microphone, causing the initial nearly
   silent capture. No additional hardware microphone gain was programmed.
6. Removed the stale second software output attenuation with the sink muted.

Headphone insertion/removal, capture during jack changes, sleep/wake, cold boot,
reboot persistence and all-four-speaker acoustic behavior remain unverified.
Upstream explicitly has microphone/jack and suspend limitations; no speculative
power-management or amplifier patch was introduced. The standard UVC camera
needs no H.264 override in the retained USB configuration.

## 7. Reboot, kernel updates and recovery

The current kernel is preserved. Pre-audio configuration and boot-image backups
are in `/var/lib/macbook-t1-audio-camera-baseline-20261019/`; audio transactions
retain owned-file restore records. A normal reboot has not been initiated
because automatic continuation of the working desktop session is not reliable.

After saving work, use `sudo reboot`. The unified read-only user service is
installed, enabled globally and smoke-tested successfully for the current user
(`Result=success`, `ExecMainStatus=0`). It runs at next login and saves
`~/.local/state/macbook-t1/verify-<boot-id>.log`. It performs no media capture.
Physical post-boot speaker/headphone/microphone/camera/Touch Bar checks remain
necessary. Suspend should be tested only after a stable reboot and with work
saved; suspend reliability is not claimed.
The earlier local Touch Bar-only diagnostic unit was disabled after the unified
verifier passed. The actual Touch Bar activation service remains enabled.

Audio DKMS rebuilds only within `7.3.0-*-generic`. The matching target-header
source version selects the bundled initial HDA subset or requires the exact
installed Ubuntu `linux-source-7.3.0` version. Missing/mismatched source or a
strict patch failure stops the build instead of loading an unverified module.

Component rollback:

```bash
sudo ./uninstall-audio.sh    # restores stock codec/config; reboot afterward
sudo ./uninstall-camera.sh  # unregisters diagnostics; preserves stock UVC/T1
sudo ./uninstall-ubuntu.sh --all
```

If audio prevents boot, append `module_blacklist=snd_hda_codec_cs8409` to the
GRUB linux line for one boot, then uninstall audio and reboot normally. This
preserves the Touch Bar. If Touch Bar itself requires recovery, retain the
existing documented `module_blacklist=apple_ibridge,apple_touchbar
t1_touchbar.disable=1` recovery parameters. Full instructions: `RECOVERY.md`.

No EFI/T1 firmware, identity/calibration data, partitions, PAM configuration,
global USB/HID blacklists or unrelated Wi-Fi drivers were changed.

## 8. Source tests, packaging and Git

Feature branch: **`feature/ubuntu-audio-camera`**. Main remains at the recorded
base until the owner separately requests a merge. Exact upstream inputs are
pinned above and in the source checksum manifest.

The containing Git revision can be identified with
`git log -1 --format=%H -- AUDIO-CAMERA-IMPLEMENTATION-REPORT.md`; the final
commit and remote branch are also reported in the delivery message.

### Completion

- `install-ubuntu.sh --all --install-deps` succeeded on the working machine.
- A second `install-ubuntu.sh --all` succeeded as an idempotent operation;
  it preserved the running Touch Bar/audio modules and existing configuration.
- `verify-ubuntu.sh --all` passed all component software checks.
- Post-login verification unit installation, enablement and a current-session
  run passed. Boot-image backup checksums passed; the installed kernel image
  is byte-identical to the pre-audio backup.
- All nine repository Python test programs passed, including ACPI/HID native
  ASan/UBSan harnesses, transactions, installer-policy cases, component removal
  isolation, monitor-source exclusion and dynamic camera ancestry.
- Shell/Python syntax and authored-code Git whitespace checks passed. Pinned
  upstream files retain their original whitespace, and patch context retains
  the whitespace needed for exact application. The destructive QEMU
  lifecycle test was updated for idempotence but intentionally not run on the
  physical Mac. No live uninstall/reinstall cycle was used as a substitute for
  isolated rollback tests.
- The portable package includes required source, patches, licenses, diagnostics
  and reports. Build outputs, audit clones, raw logs, browser profiles,
  recordings and credentials are excluded. Package/archive checksum validation
  and extracted-package regression checks passed before feature-branch publication.
