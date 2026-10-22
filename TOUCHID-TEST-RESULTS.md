# Touch ID test results — 22 October 2026

**Physical enrollment, correct-finger matching and wrong-finger rejection passed
in the one-boot trial. System authentication is not yet accepted.** At the user's
request, the one-shot installer now enables persistent Touch ID for the exact
recorded model/OS/kernel. The ordinary boot image, module tree and
password-authentication configuration remain the baseline, with normal Ubuntu
available in the boot menu. Installation is separate from full physical acceptance.

## Build and automated evidence

Host: MacBookPro13,2, Ubuntu 26.10 x86_64, kernel `7.3.0-9-generic`, exact matching
headers, GCC 15.3.0, Rust 1.97.1, systemd 261. Upstream:
`81cbdf81026a16e02f0bea74735c6b029a8ffae2`.

| Check | Observed result |
| --- | --- |
| Repository baseline | Clean `ffa6df7`; dedicated development branch created |
| T1 USB discovery | One 05ac:8600; configuration 1, legacy Touch Bar and stock UVC active before reboot |
| EFI FDRData | Present; privately backed up. Same-sensor automatic import passed in the corrected trial |
| T1Bridge runtime binaries | Built successfully with locked sources and GNU-linker patch |
| Runtime Rust tests | 1,046 passed; 3 upstream firmware-asset tests ignored |
| Native C boundary, SEP, storage, UVC parser and DRM protocol/resume tests | Passed selected upstream Make targets |
| Upstream unit/udev configuration verification | Passed `make SHELL=/bin/bash packaging` |
| Four kernel modules | Compiled directly and through DKMS for 7.3.0-9-generic; DKMS build only, no replacement of normal installed modules |
| Restricted libfprint test build | 98 passed; 33 hardware emulation cases skipped because those unrelated drivers are excluded |
| Matched fprintd/PAM tests | All 560 passed on synthetic devices/private test buses; no physical fingerprint claim |
| Integration policy/lifecycle tests | Full top-level project discovery: 95 passed, including 37 Touch ID tests and 9 one-shot tests |
| Private bundle install, verification, uninstall, reinstall | Passed on this host; system fingerprint libraries and PAM unchanged |
| Pinned source reconstruction | 919 files match an independent reconstruction from verified archives; a repeated network fetch timed out, so the checksum-verified cache was used |
| Earlier baseline one-shot repeat | `sudo ./install.sh --no-install-deps` returned 0 when Touch ID was still report-only; this does not validate the new complete installation path |
| Persistent boot configuration | Installed locally after the user's request; generated menu checked, original kernel/initramfs and PAM preserved. First persistent boot not yet observed |
| Default one-shot orchestration | Command-plan and failure-path tests pass: target preflight, unprivileged source build, existing bundle reuse, persistent selection, scoped rollback and opt-out |
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

The first physical trial boot on 22 October failed Touch Bar availability. Kernel
logs show configuration 2 and `appletbdrm` at 13:28:52 IST, then configuration 1
at 13:28:53. The unchanged legacy udev rule forced configuration 1; the trial flag
also suppressed the old Touch Bar service, leaving neither stack usable. The
replacement service timed out waiting for `/dev/dri/touchbar`, and the machine-data
importer reported an unavailable sensor. A source correction now guards the
legacy rule during trial boots and includes it in the trial initramfs. The user
confirmed the visible Touch Bar returned after the next normal reboot on
22 October. Diagnostics confirmed configuration 1, the two legacy modules,
Touch Bar input/control interfaces, and a successful boot service.

After that recovery, failed-trial rollback and corrected restaging succeeded on
22 October. The updated integration suite passed 26 tests, the one-shot suite
passed 6, and the installed udev guard passed `udevadm verify`. Staging verified
the exact guard bytes inside the replacement trial initramfs before arming GRUB.
The normal kernel, initramfs and `grub.cfg` matched the original saved hashes,
and all 31 current PAM files matched their pre-restaging hashes. The live normal
Touch Bar remained active in configuration 1 during staging.

A subsequent corrected trial kept USB configuration 2 and started the display
service, but the automatic desktop account lacked renderer access and the
machine-data importer ran before the private NCM/xART storage service was ready.
That boot ended in a session-requested clean reboot; the normal boot afterward
was the expected one-time fallback, not evidence of a kernel crash. Staging now
orders the importer after the ready xART service and enables redacted upstream
diagnostics for trial services. The intended account was used for the next boot.

The current corrected trial boot began at approximately 14:12 IST. The trial
command-line flag and USB configuration 2 were confirmed. Automatic same-sensor
import completed at 14:12:40, including hardware association and durable commit.
The Touch Bar hardware service and session renderer are active.

The first terminal enrollment attempt failed before capture at 14:17:57 with
`enroll-unknown-error`; diagnostics reported device-keybag preparation failure
and SEP operation code `-111`. Its cause remains unproven. The user subsequently
enrolled through GNOME Settings successfully: broker enrollment completed at
14:21:10 and fprintd listed `left-index-finger`. No driver reset, keybag deletion,
firewall change or code change was made between those attempts. A Settings match
operation was cancelled; it is not counted as a rejection test.

The user confirmed that the enrolled physical finger was the left index finger.
Separate attended tests using the private `fprintd-verify` then produced:

- Left index finger: `verify-match (done)`, exit 0, completed at 14:25:11.
- Unenrolled right index finger: `verify-no-match (done)`, exit 1, completed at
  14:25:52. The expected nonzero exit is a successful rejection test.

Both tests selected the stored `left-index-finger` record. These are one positive
and one negative physical sample, not a statistical accuracy assessment.
Afterward USB configuration remained 2, and the Touch Bar hardware service,
renderer and keybag relay were active with zero restarts. No PAM configuration
was changed. Redacted diagnostic events are retained only in ignored local logs;
no fingerprint templates or Apple machine-data payloads are included here.

### Volume indicator follow-up

The user confirmed that the replacement Touch Bar changes the actual volume
and mute state, but GNOME's on-screen indicator was absent. The provider uses
`wpctl` directly, and a live `org.gnome.Shell.ShowOSD` call was denied by the
Shell's caller restrictions. An optional GNOME 51 user extension now observes
output volume/mute changes and displays the native OSD during trial boots.
Its module syntax and installed bytes were checked; a read-only Gvc probe
confirmed the current output's volume/mute properties and volume limits.
The extension loaded in the subsequent normal session and remained inert because
that boot did not select T1Bridge. Visual acceptance on a T1Bridge boot remains
pending. The one-shot installer now installs it for the selected desktop account.

### Persistent installation follow-up

The next reboot returned to normal Ubuntu as expected for a one-time trial, so
the distribution fingerprint daemon exposed no T1 reader and Settings hid its
fingerprint menu. After the user requested persistent activation without repeating
physical tests, the existing isolated image was selected as the GRUB default.
The normal Ubuntu entry remains available in a five-second menu. Generated boot
configuration, original kernel/initramfs and PAM hashes were checked; the saved
fingerprint record was present without reading its biometric content. GDM's
existing fingerprint policy was enabled and its fingerprint PAM service was
already installed. Actual GDM login and the next persistent boot remain unobserved.

The tracked one-shot path now supports the same activation, fresh source builds,
and verified reuse of existing installations. Synthetic tests cover an unenrolled
fresh setup, repeat installation, changed boot files, failed menu generation,
missing normal fallback and preservation of unrelated pending boot choices.
No physical fingerprint tests were repeated for this installer change.

| Requirement | Status |
| --- | --- |
| A. Sensor usable through the SEP transport | Passed in corrected trial: same-sensor import, enrollment and matching completed |
| B. Enrollment | Passed through GNOME Settings, left index finger; earlier terminal bootstrap failure retained above |
| C. Correct-finger verification | Passed: left index finger produced `verify-match` |
| D. Incorrect-finger rejection | Passed: unenrolled right index finger produced `verify-no-match` |
| E. sudo fingerprint authentication | Not enabled/tested |
| F. GNOME unlock | Existing distro fingerprint service retained; actual unlock not yet tested |
| G. Password fallback, including unavailable fingerprint service/module | Original PAM preserved; failure-injection acceptance pending |
| GDM login | Existing distro fingerprint policy enabled; actual login not yet tested |
| H. Fingerprints persist after reboot | Not tested |
| I. Touch Bar under replacement stack | Visible; services stable after fingerprint tests. User confirms volume and mute work. GNOME OSD fix loaded on normal boot; T1Bridge-boot visual confirmation and other control regression tests pending |
| J. Camera under replacement UVC driver | Not tested |
| K. Speakers/headphones/microphone | Baseline previously working; replacement-stack regression pending |
| L. Wi-Fi | Baseline previously working; trial regression pending |
| M. Keyboard and trackpad | Baseline previously working; trial regression pending |
| N. Suspend/resume, including audio recovery | User confirmed baseline on 21 October; new-stack test pending |
| O. Live-stack uninstall/rollback | Rollback after the failed hardware trial passed; removal after a working Touch ID session remains pending |
| Fresh one-shot installation | Not tested |
| Existing-installation upgrade and repeated complete Touch ID installation | Synthetic reuse and failure-path tests pass; complete physical acceptance pending |
| Kernel update | Not tested; generated DKMS metadata restricts the exact compiled kernel |

A passing service start, compile, mock match or staged rollback does not promote
these rows. `compatibility.json` has no validated entries. Promotion requires all
mandatory physical, authentication, persistence, fallback, regression, upgrade,
recovery and complete one-shot installation checks. Persistent installation is
implemented and enabled at the user's request; it does not mark untested rows as
passed.
