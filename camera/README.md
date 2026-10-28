# FaceTime HD camera on Touch ID boots

The normal T1 USB configuration exposes MJPEG. The Touch ID boot selects USB
configuration 2 and its UVC driver exposes only H.264. On this MacBookPro13,2,
FFmpeg can decode that stream, but Firefox fails to capture it with
`NotReadableError: Starting videoinput failed`. Meet may then show missing
camera, microphone and speaker together, even when audio works independently.

The adapter publishes **FaceTime HD (Browser)** at `/dev/video10` as
1280×720 YUV420 at 30 fps. Select that camera in Firefox's permission popup and
Meet's video settings. Select **Built-in Audio Analog Stereo** for microphone
and speakers. The original **iBridge** camera remains available for applications
that support H.264 directly.

## Installation

The default one-shot installer includes this adapter for the selected desktop
account, before staging the Touch ID boot image:

```bash
sudo ./install.sh
```

It follows `--touchid-user ACCOUNT`, or the sudo/pkexec account by default.
`--no-desktop`, `--no-touchid`, and the development-only `--touchid-trial` skip
this step. `--no-install-deps` requires the dependencies to be installed already.
The recorded target is Ubuntu 26.10 / MacBookPro13,2 / Touch ID boot. Dependencies
are `cc`, FFmpeg, `v4l2-ctl`, user systemd support and matching `v4l2loopback`
version 0.15.3 or later. If absent, the installer requests Ubuntu's signed
`linux-main-modules-v4l2loopback-$(uname -r)` package; it does not replace the
physical camera driver or build an additional kernel module.

For an existing Touch ID installation, install just the camera integration:

```bash
sudo python3 camera/browser-setup.py --install --install-deps
# Optional: --account ACCOUNT
```

The separate system and user entry points remain available:

```bash
sudo python3 camera/browser-setup.py --system
python3 camera/browser-setup.py --user
```

The system step reserves `/dev/video10`, refuses conflicting devices or local
configuration, and installs two narrowly scoped module configuration files.
The user step builds a private adapter without root and enables its user service.
Fresh installations in an active Touch ID session refresh WirePlumber once,
briefly interrupting audio. On future
logins the adapter signals readiness before WirePlumber scans camera devices.
Normal boots without `t1bridge.trial=1` skip the service.

Repeat installation verifies the files and leaves unchanged services running.
The earlier manual setup is adopted when its files match exactly. A saved hash
record permits later managed updates while refusing to overwrite local edits;
disabled services remain disabled. Interrupted activation can be retried. An
account without a live session is configured for its next login without starting
a private D-Bus session or running the camera as root. Other accounts can use
the same explicit `--account` installation command.

The adapter watches v4l2loopback's capture-client events. Merely listing cameras
does not activate the physical camera. When an app starts capture, FFmpeg opens
the T1 camera and decodes directly into memory. When capture stops, the decoder
exits and buffered frames are replaced with black. No audio, recordings or
network connections are involved. Touch ID, Touch Bar, USB configuration and
boot images are not changed.

## Checks and observed results

```bash
./verify-camera.sh --capture
systemctl --user status macbook-t1-camera-browser.service
wpctl status
python3 -m unittest discover -s tests/camera -v
./install.sh --plan
```

On 28 October 2026, native H.264 capture decoded successfully at 640×480 and
1280×720. Repeated adapter capture produced changing 720p frames, the PipeWire
capture path completed, and the physical camera stopped between requests. The
user confirmed the **FaceTime HD (Browser)** preview in Firefox; their screencast
also showed that preview. Firefox independently captured the internal microphone
and enumerated the speakers. A completed Meet call and physical reboot/resume
with this adapter have not been verified.

## Removal

```bash
sudo python3 camera/browser-setup.py --install --remove
# Or remove each scope separately:
python3 camera/browser-setup.py --user --remove
sudo python3 camera/browser-setup.py --system --remove
```

The combined removal targets the selected account and shared module startup
configuration; remove any other configured user adapters separately. The
existing loopback module stays loaded until restart; removal does not unload
other video devices. Any saved browser camera choice can be changed in that
browser's camera settings. Installation directories containing other local
files are retained.

References: [T1Bridge camera format support](https://github.com/standardagents/t1bridge#t1-function-support),
[v4l2loopback client-usage events](https://github.com/v4l2loopback/v4l2loopback/blob/v0.15.3/v4l2loopback.c).
