# Touch ID portability

Status: persistent installation enabled for the exact development target below;
full physical acceptance remains incomplete.

The core T1 implementation is upstream C/Rust. Package commands live in
`touchid/adapters.py`; discovery in `probe.py`; source building in `build.py`;
private bundle installation/removal in `deploy.py`; one-shot orchestration in
`setup.py`; persistent boot selection in `persistent.py`; and acceptance reporting
in `manage.py`. No package manager is invoked by T1 protocol code. Systemd service,
udev, USB, DRM, D-Bus and fingerprint contracts remain upstream-owned.

| Distribution | Implemented adapter | Evidence / limit |
| --- | --- | --- |
| Ubuntu 26.10 x86_64 | apt dependencies, exact headers, private source bundle, local DEB and persistent one-shot installation | MacBookPro13,2 / 7.3.0-9-generic only. Builds, enrollment and positive/negative matching passed; full physical acceptance pending. See test report. |
| Debian | apt dependency command | Synthetic command tests only; runtime requirements may exclude older releases. |
| Linux Mint | apt dependency command | Synthetic command tests only; no physical or full build validation. |
| Fedora | dnf dependency command, exact kernel-devel name | Synthetic command tests only; RPM generation and installation not implemented. |
| Arch / recognized derivatives | pacman dependency command | Upstream has its own Arch support. This project's migration is not validated. Exact running-kernel headers must already be supplied. |
| openSUSE | Explicit recognition and refusal | Dependency recipe, RPM packaging and migration not implemented; does not reuse Fedora packages blindly. |
| Other distributions / non-systemd | Explicit refusal | No validated adapter. |

Requirements: x86_64, Python >=3.12 for safe archive extraction, Rust >=1.88,
C17 compiler, matching Kbuild headers, libudev, systemd >=256 and the native
libraries listed by the dependency adapter. Installed systemd is checked; the
upstream service restrictions are not weakened for older releases. The running
host uses Rust 1.97.1, GCC 15.3.0 and systemd 261.

Only kernel `7.3.0-9-generic` has been compiled locally for this integration.
Generated DKMS source restricts `BUILD_EXCLUSIVE_KERNEL` to the build's exact
release; there is no precompiled universal module. Kernel-update acceptance is
pending. Unsupported ABIs must fail rather than silently losing existing hardware.

The private fingerprint stack uses a matched, pinned pair and a private library
search path. Production libfprint contains only the T1Bridge driver; virtual
fingerprint devices exist solely in a separate test build. The private bundle
has no package scripts and activates no kernel driver, service or PAM setting.
A source build and an inert DEB are implemented. RPM/Arch binary packaging and
authentication migration beyond Ubuntu's existing GNOME fingerprint service
remain unfinished. Ubuntu installation uses a separate initramfs and journaled
GRUB configuration, with either a persistent default or an attended one-boot
trial. The normal image and password PAM rules remain unchanged.

`compatibility.json` deliberately has no validated rows. A complete physical and
installer acceptance record must match model, distro, version, kernel, architecture
and upstream commit. At the user's request, installation is enabled independently
of that acceptance matrix, with an exact target check in `setup.py`; editing
`compatibility.json` cannot broaden installation support. Other kernels or targets
must use `--no-touchid`. The unified hardware installer remains Ubuntu-specific;
this project does not claim to have ported audio, Wi-Fi or sleep to other distros.
