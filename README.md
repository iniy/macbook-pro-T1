# MacBookPro13,2 Linux hardware support — Ubuntu 26.10

One project for the **Touch Bar, internal audio, FaceTime HD camera and experimental Wi-Fi integration** on the
Intel **MacBookPro13,2** (13-inch, Late 2016, Apple T1 USB **05ac:8600**).
Tested on **Ubuntu 26.10 (Stonking Stingray)** with **7.3.0-9-generic** and
matching **7.3.0-9.9** headers/source. DKMS builds the two Touch Bar modules and
the custom CS8409 audio module; the camera uses Ubuntu's standard `uvcvideo`.

**Current result: PARTIAL — working components with remaining hardware tests.**
Touch Bar controls, internal stereo speakers, microphone recording and the
FaceTime HD camera have actual hardware evidence. Headphone playback/jack
switching, post-reboot operation and suspend/resume remain unverified.
See [AUDIO-CAMERA-IMPLEMENTATION-REPORT.md](AUDIO-CAMERA-IMPLEMENTATION-REPORT.md)
for the complete results, [UBUNTU-INSTALL-RESULT.md](UBUNTU-INSTALL-RESULT.md)
for the original Touch Bar installation, and [BUILD-REPORT.md](BUILD-REPORT.md)
for build validation.

**Wi-Fi: optional 5 GHz implementation.** The exact-source Ubuntu DKMS driver
and model-matched board data have connected this BCM43602 (`14e4:43ba`, Apple
`106b:0157`, revision 02) at **80 MHz on channel 48**. See
[implementation](WIFI-5GHZ-IMPLEMENTATION.md), [measured performance](WIFI-5GHZ-BENCHMARKS.md)
and [recovery](WIFI-5GHZ-RECOVERY.md) for the actual acceptance status.
The older [2.4 GHz investigation](WIFI-2.4GHZ-ROOT-CAUSE.md) is preserved.

```bash
# Exact supported Ubuntu/kernel/hardware; --activate requires independent Ethernet:
sudo ./wifi/install-5ghz.sh --activate
sudo ./wifi/verify-5ghz.sh
```

The new profile prefers 5 GHz. The original 2.4 GHz profile is retained, but its
fallback association test did not pass with the reference board data.

```bash
sudo ./install-wifi.sh --dma-fix --install-deps --update
sudo ./verify-wifi.sh --scan --online
# Optional explicit physical country, e.g. only while in India:
sudo ./install-wifi.sh --update --country IN
```

The base Wi-Fi diagnostics/DMA installer preserves firmware. The optional
5 GHz component fetches pinned board data into an isolated directory and leaves
the Ubuntu firmware binary unchanged. Successful installation alone is not
proof of wireless throughput or stability.

## Licensing and credits

See [LICENSE](LICENSE) for the MIT/GPL/ISC and firmware license boundaries, and
[CREDITS.md](CREDITS.md) for the upstream authors, reference implementations,
research acknowledgments and build tools. Original copyright notices are
retained; additional upstream notices are in [LICENSES/](LICENSES/).

## Install all components

```bash
git clone https://github.com/iniy/macbook-pro-T1.git
cd macbook-pro-T1
sudo ./install.sh
```

For an existing checkout, update it and install the complete suite:

```bash
cd ~/macbook-pro-T1
git pull --ff-only
sudo ./install.sh
```

The one-shot installer covers **Touch Bar, speakers/headphones/microphone,
camera, 5 GHz Wi-Fi and GNOME keyboard preferences**. It reuses the independent
component installers, keeps matching working installations, and installs needed
Ubuntu dependencies. New kernel drivers are staged for reboot by default.

Use an existing saved WPA2 Wi-Fi profile; the installer discovers the active
profile or the only saved wireless profile. When several saved profiles exist
and none is active, specify `--wifi-profile UUID`. The 5 GHz installer preserves
the original profile and creates a higher-priority 5 GHz profile.

```bash
./install.sh --plan                         # inspect the actions without changes
sudo ./install.sh --activate-wifi           # immediate Wi-Fi activation; Ethernet required
sudo ./install.sh --no-install-deps         # dependencies already installed
sudo ./install.sh --no-wifi                  # Touch Bar, audio, camera and desktop
sudo ./install.sh --no-desktop               # hardware setup without a desktop session
```

The desktop step reports the three requested touchpad values and enables
**Bounce Keys with a 100 ms delay** in the invoking user's GNOME session. It
backs up the original values and supports restoration; see [desktop/README.md](desktop/README.md).

After any required reboot/login:

```bash
./verify-ubuntu.sh --all
./verify-camera.sh --capture   # briefly uses the camera; retains no frames
sudo ./wifi/verify-5ghz.sh
```

`--touchbar`, `--audio`, `--camera` and `--wifi` select independent components; selectors
can be combined. `--verify` and `--uninstall` are also accepted by the unified
installer. The legacy no-selector invocation remains Touch Bar-only.
Matching completed installations are idempotent and preserve live drivers.
The camera uses shared T1 initialization, so install Touch Bar first or use
`--all`. A camera-only verification/removal never resets iBridge.

Examples of component selection and the unified action aliases:

```bash
sudo ./install-ubuntu.sh --audio --install-deps
sudo ./install-ubuntu.sh --touchbar --camera --install-deps
./install-ubuntu.sh --verify --all
```

## Tested functionality

| Component | Ubuntu 26.10 / 7.3.0-9-generic evidence |
|---|---|
| Touch Bar | Existing driver preserved; software checks and user-confirmed control regressions pass |
| Internal speakers | Left/right speech confirmed correct and clean; user confirmed normal application playback is usable |
| 3.5 mm headphones | Supported upstream path and jack controls present; no wired headphones available for physical test |
| Internal microphone | Actual signal captured; user confirmed browser recording; input level corrected to independent unity software gain |
| FaceTime HD camera | Stock `uvcvideo`; MJPEG capture/decode and Firefox 1280×720 preview passed |
| Built-in Wi-Fi | Working 5 GHz / 80 MHz; measured 316.55 Mbps down / 84.68 Mbps up with 0% gateway loss in the selected-AP short test; 2.4 GHz fallback test failed |
| Reboot / suspend | Persistence configured; post-reboot and suspend behavior remain unverified |

See [AUDIO-CAMERA-IMPLEMENTATION-REPORT.md](AUDIO-CAMERA-IMPLEMENTATION-REPORT.md)
for the precise evidence and remaining gaps. The post-login verifier installed
by `--all` records read-only checks under
`~/.local/state/macbook-t1/verify-<boot-id>.log`; it never records audio/video.
Wi-Fi also installs an independent read-only post-boot timer; inspect
`journalctl -b -u macbook-t1-wifi-verify.service`. `--all` verification correctly
returns failure while Wi-Fi is not associated; check individual components to
see their separate results.

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

## Install from the portable archive

Copy `dist/macbook-t1-ubuntu-1.0.0.tar.gz` and its `.sha256` file to Ubuntu:

```bash
sha256sum -c macbook-t1-ubuntu-1.0.0.tar.gz.sha256
tar -xzf macbook-t1-ubuntu-1.0.0.tar.gz
cd macbook-t1-ubuntu
sudo ./install.sh
```

Internet access is used for Ubuntu dependencies, **headers matching `uname -r`**
and the separately licensed, pinned Wi-Fi board-data download. Driver source
and patches are bundled. The Wi-Fi component also accepts a checksum-matching
offline reference file through its independent installer.
Audio's initial Ubuntu HDA source subset is included; a later supported kernel
ABI also requires its exact matching Ubuntu kernel source package.
With dependencies already installed, omit `--install-deps` for an offline install.

Then reboot normally and run:

```bash
./verify-ubuntu.sh --all
```

The installers refuse other hardware/releases/kernel families, competing driver
packages, mismatched headers, and unresolved signature requirements. They build for
the running kernel; they do not substitute unrelated generic headers or load a
module during installation. A completed matching installation is preserved on
repeated invocation. Incomplete transactions require rollback first.
Read [RECOVERY.md](RECOVERY.md) if it stops.

## Touch Bar behavior

- Firmware-drawn Esc, brightness, media and volume keys.
- Hold **Fn** for F1–F12; release Fn for the special-key strip (`fnmode=1`).
- Linux input keycodes, normally handled by Ubuntu GNOME. Volume key events do
  not establish that the machine's audio hardware works.
- Webcam remains on the standard `uvcvideo` interfaces in USB configuration 1.
- Late-boot service claims only the T1 HID devices from `hid-generic` or
  `hid-sensor-hub`, and refuses unexpected owners.
- Touch Bar DKMS rebuilds for subsequent **7.3.0-*-generic** ABI updates with matching headers.

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

## Touch Bar physical checks

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
sudo ./uninstall-ubuntu.sh --wifi
```

Remove the complete suite with `sudo ./uninstall-ubuntu.sh --all`. Camera
registration is removed before shared Touch Bar initialization. The legacy
no-selector removal remains Touch Bar-only and refuses while the camera
component depends on it.

After any kernel update, confirm headers are installed and run verification after
booting it. Audio also requires exact matching Ubuntu HDA source; see
[RECOVERY.md](RECOVERY.md) for the kernel-update procedure. New major/minor
kernel families are deliberately excluded pending a fresh compile audit;
do not assume DKMS built them. Keep a previous bootable kernel.

```bash
sudo ./uninstall-ubuntu.sh --all
sudo reboot
```

Removal also serves as rollback. Component backups and transaction logs are
retained under `/var/lib/macbook-t1-*`. Existing competing services are reported for
resolution rather than automatically removed. A matching usbmuxd rule is given a
backed-up, T1-only exclusion; iPhone/iPad handling is retained. Recheck that rule
snapshot after usbmuxd upgrades.

Preserve the working Apple firmware/EFI resources when planning migration; this
package contains no T1 firmware. No macOS boot/security configuration was changed.

Driver provenance, review and patches: [SOURCES.md](SOURCES.md).
Driver: GPL-2.0; new packaging: MIT. Repackage with `python3 tools/package.py`.
