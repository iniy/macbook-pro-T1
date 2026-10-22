# Touch ID test results — 22 October 2026

**Touch ID authentication is not yet validated. Default activation: NO.**
A separate one-boot hardware trial has been prepared; the ordinary boot image,
module tree and password-authentication configuration remain the baseline.

## Build and automated evidence

Host: MacBookPro13,2, Ubuntu 26.10 x86_64, kernel `7.3.0-9-generic`, exact matching
headers, GCC 15.3.0, Rust 1.97.1, systemd 261. Upstream:
`81cbdf81026a16e02f0bea74735c6b029a8ffae2`.

| Check | Observed result |
| --- | --- |
| Repository baseline | Clean `ffa6df7`; dedicated development branch created |
| T1 USB discovery | One 05ac:8600; configuration 1, legacy Touch Bar and stock UVC active before reboot |
| EFI FDRData | Present; privately backed up. Same-sensor import not yet tested |
| T1Bridge runtime binaries | Built successfully with locked sources and GNU-linker patch |
| Runtime Rust tests | 1,046 passed; 3 upstream firmware-asset tests ignored |
| Native C boundary, SEP, storage, UVC parser and DRM protocol/resume tests | Passed selected upstream Make targets |
| Upstream unit/udev configuration verification | Passed `make SHELL=/bin/bash packaging` |
| Four kernel modules | Compiled directly and through DKMS for 7.3.0-9-generic; DKMS build only, no replacement of normal installed modules |
| Restricted libfprint test build | 98 passed; 33 hardware emulation cases skipped because those unrelated drivers are excluded |
| Matched fprintd/PAM tests | All 560 passed on synthetic devices/private test buses; no physical fingerprint claim |
| Integration policy/lifecycle tests | 23 passed; full top-level project discovery: 78 passed |
| Private bundle install, verification, uninstall, reinstall | Passed on this host; system fingerprint libraries and PAM unchanged |
| Pinned source reconstruction | 919 files match an independent reconstruction from verified archives; a repeated network fetch timed out, so the checksum-verified cache was used |
| Existing baseline one-shot repeat | `sudo ./install.sh --no-install-deps` returned 0; Touch ID reported unvalidated, as intended |
| Runtime library isolation | `ldd` resolves the installed private fprintd to the bundled libfprint |
| Local DEB | Built and inspected; native runtime dependencies computed with dpkg-shlibdeps; not released |
| Desktop provider | Live read-only volume/mute/display-power status succeeded; action contract tested with mocks |
| Trial staging / rollback / restaging | Succeeded on the real host before boot; normal kernel, normal initramfs and grub.cfg hashes remained unchanged |
| Baseline preservation | All 30 PAM files, 6,958 original module binaries, normal kernel/initramfs and grub.cfg matched their pre-trial copies/hashes |
| CI | Workflows added; CI execution/results are not yet claimed |

Upstream's complete `make quality` is **not** recorded as passing. The release
publication tool requires Arch repository utilities, and the obsolete direct PAM
adapter test assumes regular `/usr/bin/true` and `/usr/bin/false` binaries;
Ubuntu uses multicall symlinks, which its trust check correctly rejects. Neither
tool is shipped or used here. Runtime tests exclude only `t1-release`; the actual
pam_fprintd suite is included. A host-umask failure was corrected in the build
runner without weakening protected-directory checks.

Local build/debug logs are in ignored `logs/touchid/`. Private installation and
rollback logs are in the root-only baseline backup directory described in
TOUCHID-RECOVERY.md. They are not uploaded. Earlier failed attempts remain
available and are not counted as passes.

## Physical and security acceptance

| Requirement | Status |
| --- | --- |
| A. Sensor usable through the SEP transport | Pending configuration-2 boot; USB presence alone is insufficient |
| B. Enrollment | Not attempted |
| C. Correct-finger verification | Not attempted |
| D. Incorrect-finger rejection | Not attempted |
| E. sudo fingerprint authentication | Not enabled/tested |
| F. GNOME unlock | Not enabled/tested by this integration |
| G. Password fallback, including unavailable fingerprint service/module | Original PAM preserved; failure-injection acceptance pending |
| GDM login | Not enabled/tested by this integration |
| H. Fingerprints persist after reboot | Not tested |
| I. Touch Bar under replacement stack | Not tested; old stack remains active before reboot |
| J. Camera under replacement UVC driver | Not tested |
| K. Speakers/headphones/microphone | Baseline previously working; replacement-stack regression pending |
| L. Wi-Fi | Baseline previously working; trial regression pending |
| M. Keyboard and trackpad | Baseline previously working; trial regression pending |
| N. Suspend/resume, including audio recovery | User confirmed baseline on 21 October; new-stack test pending |
| O. Live-stack uninstall/rollback | Pre-boot staged rollback passed; rollback after hardware use remains pending |
| Fresh one-shot installation | Not tested |
| Existing-installation upgrade and repeated complete Touch ID installation | Not accepted |
| Kernel update | Not tested; generated DKMS metadata restricts the exact compiled kernel |

A passing service start, compile, mock match or staged rollback does not promote
these rows. `compatibility.json` has no validated entries. Promotion requires all
mandatory physical, authentication, persistence, fallback, regression, upgrade,
recovery and complete one-shot installation checks, plus a permanent installation
path. The one-boot trial is not that release acceptance.
