# Touch ID portability

Status: development integration, not a supported Touch ID release.

The core T1 implementation is upstream C/Rust. Package commands live in
`touchid/adapters.py`; discovery in `probe.py`; source building in `build.py`;
private installation/removal in `deploy.py`; and acceptance reporting in
`manage.py`. No package manager is invoked by T1 protocol code. Systemd service,
udev, USB, DRM, D-Bus and fingerprint contracts remain upstream-owned.

| Distribution | Implemented adapter | Evidence / limit |
| --- | --- | --- |
| Ubuntu 26.10 x86_64 | apt dependencies, exact headers, private source bundle and local DEB | Runtime and kernel compilation on 7.3.0-9-generic; physical T1Bridge operation not accepted. See test report. |
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
permanent distribution-specific authentication migration remain unfinished.
An attended one-boot Ubuntu trial is implemented using a separate initramfs; it
has not yet passed physical acceptance.

`compatibility.json` deliberately has no validated rows. A complete physical and
installer acceptance record must match model, distro, version, kernel, architecture
and upstream commit. Editing this file alone cannot bypass the still-closed live
migration gate. The existing unified hardware installer remains Ubuntu-specific;
this branch does not claim to have ported audio, Wi-Fi or sleep to other distros.
