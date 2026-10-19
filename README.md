# MacBookPro13,2 Touch Bar, Audio and Camera — Ubuntu 26.10

Prepared for **Ubuntu 26.10 (Stonking Stingray)**, the latest stable release on
2026-10-18. Target: Intel **MacBookPro13,2**, Apple T1 USB **05ac:8600**,
Ubuntu **7.3.0-*-generic** kernels. Both modules compile against **7.3.0-9-generic**.

**Physical Ubuntu operation is partially verified as of 2026-10-19.** On this
MacBookPro13,2, both modules load and the repository verifier passes. Real
brightness, volume and Fn-switched function-key events were captured; the user
confirmed the lit display, Esc and F10. Individual mute/media delivery, reboot
and sleep/wake remain unverified. See [UBUNTU-INSTALL-RESULT.md](UBUNTU-INSTALL-RESULT.md)
for the hardware evidence and [BUILD-REPORT.md](BUILD-REPORT.md) for build validation.

## Unified installation

```bash
git clone https://github.com/iniy/macbook-pro-T1.git
cd macbook-pro-T1
sudo ./install-ubuntu.sh --all --install-deps
# Save work and reboot for boot-persistence validation:
sudo reboot
```

After login:

```bash
./verify-ubuntu.sh --all
./verify-camera.sh --capture   # briefly uses the camera; retains no frames
```

`--touchbar`, `--audio` and `--camera` select independent components; selectors
can be combined. `--verify` and `--uninstall` are also accepted by the unified
installer. The legacy no-selector invocation remains Touch Bar-only.
Matching completed installations are idempotent and preserve live drivers.
The camera uses shared T1 initialization, so install Touch Bar first or use
`--all`. A camera-only verification/removal never resets iBridge.

| Component | Ubuntu 26.10 / 7.3.0-9-generic evidence |
|---|---|
| Touch Bar | Existing working driver retained; binding/guard regression checks pass |
| Internal speakers | Left/right speech confirmed correct and clean; user confirmed normal application playback is usable |
| 3.5 mm headphones | Supported upstream path and jack controls present; no wired headphones available for physical test |
| Internal microphone | Actual signal captured; user confirmed browser recording; input level corrected to independent unity software gain |
| FaceTime HD camera | Stock `uvcvideo`; MJPEG capture/decode and Firefox 1280×720 preview passed |
| Reboot / suspend | Persistence configured; post-reboot and suspend behavior remain unverified |

See [AUDIO-CAMERA-IMPLEMENTATION-REPORT.md](AUDIO-CAMERA-IMPLEMENTATION-REPORT.md)
for the precise evidence and remaining gaps. The post-login verifier installed
by `--all` records read-only checks under
`~/.local/state/macbook-t1/verify-<boot-id>.log`; it never records audio/video.

### Audio safety and testing

This model's CS8409 (`1013:8409`, subsystem `106b:3600`) uses upstream's
SSM3515 configuration and CS42L83 headphone path. Driver source and exact
Ubuntu HDA source are bundled under `audio/`. Build preparation rejects
mismatched kernel-source versions instead of falling back to another kernel.

Playback uses PipeWire's software mixer. **Do not play directly through ALSA
`hw:` or `plughw:`**: those bypass the required volume path. Start quietly;
stop if distortion, clipping or unexpected heating occurs. No speculative
amplifier-register or speaker-tuning changes are included. All four individual
tweeter/woofer paths and maximum acoustic output have not been validated.

Optional attended tests (ordinary desktop user):

```bash
python3 audio/safe-playback.py --volume-percent 10
python3 audio/microphone-test.py --seconds 8
python3 audio/browser-test.py --fresh-profile
python3 camera/browser-test.py
```

Browser microphone recordings remain in memory and support Record/Replay/
Confirm. Test replay is deliberately attenuated (default 5% peak); this is
separate from normal application volume. Diagnostic playback returns the sink
to mute at 2%. The browser test's temporary profile is removed afterward.

If normal playback is unexpectedly quiet, inspect `PCM Playback Volume` on the
discovered HDA card: Ubuntu's `front` PCM adds a second **software** volume
layer. The hardware session found and removed a stale −26.6 dB setting while
PipeWire was muted. Keep PipeWire software mixing enabled; avoid amplifier
register changes or indiscriminate gain boosts.

## Install after migrating to Ubuntu

Copy `dist/macbook-t1-ubuntu-1.0.0.tar.gz` and its `.sha256` file to Ubuntu:

```bash
sha256sum -c macbook-t1-ubuntu-1.0.0.tar.gz.sha256
tar -xzf macbook-t1-ubuntu-1.0.0.tar.gz
cd macbook-t1-ubuntu
sudo ./install-ubuntu.sh --install-deps
```

If you copied the complete project into your home directory instead:

```bash
cd ~/macbook-t1-ubuntu
sudo ./install-ubuntu.sh --install-deps
```

Internet access is needed only for Ubuntu build dependencies and **headers matching
`uname -r`**. Driver source and patches are bundled; no GitHub download is required.
With dependencies already installed, omit `--install-deps` for an offline install.

Then reboot normally and run:

```bash
sudo ./verify-ubuntu.sh
```

The installer refuses other hardware/releases/kernel families, competing Touch Bar
packages, mismatched headers, and unresolved signature requirements. It builds for
the running kernel; it does not substitute unrelated generic headers or load a
module during installation. A completed matching installation is preserved on
repeated invocation. Incomplete transactions require rollback first.
Read [RECOVERY.md](RECOVERY.md) if it stops.

## Expected functionality

- Firmware-drawn Esc, brightness, media and volume keys.
- Hold **Fn** for F1–F12; release Fn for the special-key strip (`fnmode=1`).
- Linux input keycodes, normally handled by Ubuntu GNOME. Volume key events do
  not establish that the machine's audio hardware works.
- Webcam remains on the standard `uvcvideo` interfaces in USB configuration 1.
- Late-boot service claims only the T1 HID devices from `hid-generic` or
  `hid-sensor-hub`, and refuses unexpected owners.
- DKMS rebuilds for subsequent **7.3.0-*-generic** ABI updates with matching headers.

**Limitations:** this fork's T1 display-brightness function is a no-op. Automatic
Touch Bar dim/off is unavailable; defaults are explicitly `idle_timeout=-1` and
`dim_timeout=-1`. Laptop screen-brightness key events are separate and supported.
USB autosuspend is disabled only for the T1, with a possible battery-life cost.
Touch ID and arbitrary app-specific graphics are outside this package. Audio is
provided by the independent optional component described above.

The included upstream resume patch restores ordinary HID resume and mode state,
but S3 wake can still leave a T1 dark. Reliable sleep recovery on **this** firmware
must be tested. **`skip_acpi_power=1` is mandatory**, including at suspend/resume;
this build rejects other values. Recovery never calls `SOCW` or an ACPI reset.

## Verify physically

After the script reports healthy bindings, test:

1. Esc and every special key; hold/release Fn and test F1–F12.
2. An optional `sudo evtest /dev/input/eventN`, using the Touch Bar event path
   printed by verification (`sudo apt install evtest` if needed).
3. Webcam preview while using the Touch Bar, then a normal reboot.
4. Sleep/wake first on AC and then on battery; repeat and record any dark bar,
   stuck key or camera regression. Read `cat /sys/power/mem_sleep` to identify
   the tested sleep type. Save work before testing sleep.

Verification is read-only and excludes raw logs, serials and UUIDs. Exit 0 means
binding checks passed, not that physical controls or suspend passed.

Fn mode can be changed for the current session:

```bash
for d in /sys/bus/hid/devices/0003:1D6B:0301.*; do
    [ ! -f "$d/fnmode" ] || echo 2 | sudo tee "$d/fnmode"
done
```

Modes: `0` always F-keys, `1` special/Fn→F-keys, `2` inverse, `3` always special,
`4` Esc only. Persistent settings are in `/etc/modprobe.d/macbook-t1-touchbar.conf`.
Later edits to owned configuration are preserved during uninstall for review.

## Updates and removal

Remove only audio or camera while retaining the working Touch Bar:

```bash
sudo ./uninstall-ubuntu.sh --audio
sudo ./uninstall-ubuntu.sh --camera
```

Remove the complete suite with `sudo ./uninstall-ubuntu.sh --all`. Camera
registration is removed before shared Touch Bar initialization. The legacy
no-selector removal remains Touch Bar-only and refuses while the camera
component depends on it.

After any kernel update, confirm headers are installed and run verification after
booting it. New major/minor kernel families are deliberately excluded pending a
fresh compile audit; do not assume DKMS built them. Keep a previous bootable kernel.

```bash
sudo ./uninstall-ubuntu.sh
```

Then reboot. This also serves as rollback. Backups and transaction logs are retained
under `/var/lib/macbook-t1-ubuntu*`. Existing competing services are reported for
resolution rather than automatically removed. A matching usbmuxd rule is given a
backed-up, T1-only exclusion; iPhone/iPad handling is retained. Recheck that rule
snapshot after usbmuxd upgrades.

Preserve the working Apple firmware/EFI resources when planning migration; this
package contains no T1 firmware. No macOS boot/security configuration was changed.

Driver provenance, review and patches: [SOURCES.md](SOURCES.md).
Driver: GPL-2.0; new packaging: MIT. Repackage with `python3 tools/package.py`.
