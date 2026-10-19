# Build and validation report

Audit date: **2026-10-18**. Package: **macbook-t1-touchbar 1.0.0**.
Requested target updated during work to the latest stable **Ubuntu 26.10**.

## Audio/camera integration — 2026-10-19

Feature branch: `feature/ubuntu-audio-camera`, based on `36f31c8592c90b88aab1175e89d29f64eb9c3695`.

- Exact Ubuntu **7.3.0-9.9** HDA sources and **7.3.0-9-generic** headers used.
- Initial davidjo header patch stopped on changed 7.3 context. A minimal
  source-layout adaptation preserved the new kernel fields; both CS8409
  compilation units then compiled, modpost/link passed and vermagic matched.
- Audio DKMS **macbook-t1-audio/1.0.0** built, signed and installed. Its actual
  PKCS#7 signature passed verification before activation. The stock codec was
  archived by DKMS for removal; the pre-audio boot image was backed up.
- The custom audio codec was activated with an audio-only HDA codec reload,
  while desktop audio was stopped. No T1 USB reset/rebind was performed.
- PipeWire/WirePlumber software-mixer policy was checked on the actual card
  and node. Muted volume changes altered `softVolumes` without changing ALSA
  controls. The input's default was separated from the quiet output default.
- Low-level left/right speaker speech was confirmed correct and clean.
  Microphone samples were captured without clipping and the user confirmed
  browser recording. Quiet diagnostic replay is deliberately attenuated.
- Stock UVC captured/decoded MJPEG; Firefox presented 30 frames at 1280×720
  and the user confirmed a live preview. No custom camera driver was needed.
- Touch Bar binding/guard regression checks passed after installation and
  audio activation; existing modules and service remain in place.

Headphone playback/jack transitions, post-reboot operation, suspend/resume,
individual woofer/tweeter behavior and maximum acoustic output are not claimed
as verified. Detailed results and final packaging/test status are maintained in
[AUDIO-CAMERA-IMPLEMENTATION-REPORT.md](AUDIO-CAMERA-IMPLEMENTATION-REPORT.md).

## Physical Ubuntu follow-up — 2026-10-19

The package was installed and activated on the target MacBookPro13,2 with
Ubuntu 26.10 Desktop and kernel/headers 7.3.0-9-generic. Two installer adaptations
retain Desktop's dracut provider and recognize this Apple EFI's unsupported
Secure Boot message while retaining EFI-storage and kernel-enforcement checks.
Regression tests cover both adaptations; driver C source is unchanged.

DKMS build/sign/install, cryptographic module-signature verification, installed
unit/rule validation, live HID binding and `verify-ubuntu.sh` passed.
`skip_acpi_power=1` was verified in sysfs and the kernel log. Real brightness,
volume, keyboard-illumination and Fn-held F1–F9/F11/F12 events were captured;
the user confirmed the lit display, Fn layout switching, Esc and F10.
Individual mute/media delivery, reboot and sleep/wake remain unverified.

Outcome: **PARTIAL**. Full evidence and recovery details are in
[UBUNTU-INSTALL-RESULT.md](UBUNTU-INSTALL-RESULT.md).

The following sections retain the original 2026-10-18 build-audit record;
their physical-test status describes that earlier audit.

## Original results by environment — 2026-10-18

| Category | Result |
|---|---|
| Monterey hardware/firmware inspection | **PASS**, read-only, allowlisted report |
| Monterey source/patch and installer guard checks | **PASS** |
| Native HID and ACPI-guard regressions with ASan/UBSan | **PASS** |
| Backup/restore/fault-injection tests | **PASS**, 4 cases on both macOS and Linux |
| Linux module compilation | **PASS**, both modules, Ubuntu **7.3.0-9-generic** headers |
| Linux static checks | **PASS**, ShellCheck and sparse; no driver C diagnostics |
| Real installer lifecycle in isolated Linux VM | **PASS**, install/build/sign/initramfs/uninstall with simulated DMI/USB |
| PKCS#7 signature validation | **PASS**, actual DKMS signature; tampering and wrong certificate rejected |
| systemd unit / udev rule validation | **PASS** |
| Portable archive validation | **PASS**, deterministic rebuild, checksums, paths/modes and offline patch reconstruction |
| Physical Ubuntu Touch Bar on this Mac | **NOT TESTED** |
| Physical Ubuntu reboot/suspend/webcam coexistence | **NOT TESTED** |
| Secure Boot enrollment/enforced loading | **NOT TESTED**; no enrollment performed |

## Mac inspected

- macOS Monterey **12.7.6**, build **21H1320**, x86_64.
- **MacBookPro13,2**, Intel i5-6267U 2.90 GHz, 8 GiB RAM.
- System firmware **529.120.1.0.0**, OS loader **540.120.3~37**.
- **Apple T1 Security Chip**, iBridge build **14Y910**.
- Apple T1 Controller: USB **05ac:8600**, bcdDevice **0x0101**, three
  configurations, class **0xef**, subclass **0x02**, protocol **0x01**.
- Read-only boot/security status: FileVault on, Gatekeeper enabled; SIP was
  **already disabled** when inspected. Boot-args exists; value omitted.
- Saved report: `reports/macos-hardware.json`. No hardware serials, UUIDs,
  disk identifiers or raw IORegistry/NVRAM dumps were saved.

The project directory already contained setup logs, a Python venv and a setup
report. Those were preserved. Preexisting setup logs are **excluded** from the
portable archive because they contain local account paths.

No Monterey boot setting, EFI/NVRAM variable, security setting, disk partition,
firmware or T1 identity/calibration was changed. No Linux module was loaded on
macOS; the host's USB/T1 devices were never passed into the VM.

## Linux compilation environment

- Official **Ubuntu 26.10** amd64 released cloud image, image build **20261011**.
- Image SHA256 verified against Canonical's HTTPS SHA256SUMS:
  `0a369348e6c4280a277d5c8ab7c092c9e7bf35b8db8770006eb09bbd56d06d5b`.
  This is a checksum-over-HTTPS check, not a separately verified GPG signature.
- QEMU **9.1.2** from signed **UTM 4.6.5**, whose app code signature was verified.
  A small local CLI adapter uses the QEMU framework and macOS Hypervisor.framework.
  It is locally signed with the hypervisor entitlement; no security protection
  was disabled. VM: two vCPUs, 2 GiB RAM, private qcow2 overlay, localhost-only SSH.
- Guest running kernel: **7.3.0-9-generic**.
- Header packages: **linux-headers-7.3.0-9** and **-generic**, version **7.3.0-9.9**,
  obtained using Ubuntu apt repository verification.
- Compiler: **x86_64-linux-gnu-gcc 15.3.0**, Ubuntu **15.3.0-4ubuntu1**,
  matching the kernel compiler. GCC 16 was also installed during tool discovery
  but is not required by the package or used for its DKMS build.
- DKMS **3.2.2-1ubuntu1**; ShellCheck **0.11.0**.
- sparse **v0.6.5-rc1**, commit
  `37156835e3d725b6d750f000be33ba3814bb2310`, built unprivileged from
  `https://git.kernel.org/pub/scm/devel/sparse/sparse.git`.
  Ubuntu's packaged sparse 0.6.4 was too old for these headers; the first attempt
  was skipped by Kbuild. The final run explicitly logged **CHECK** for both C files.

Commands used in the guest:

```bash
make -C driver KVERSION=7.3.0-9-generic CC=x86_64-linux-gnu-gcc W=1 -j2
SPARSE="$HOME/sparse/sparse" bash tools/validate-linux.sh
```

Outputs: `apple-ibridge.ko`, `apple-touchbar.ko`; modpost/link succeeded and both
vermagic values are **7.3.0-9-generic SMP preempt mod_unload modversions**.
The source archive intentionally contains source rather than guest `.ko` binaries.

**Build notices:** the initial build used the same compiler through the `gcc`
alias and Kbuild warned about its spelling. The final recipe uses the matching
triplet command. Kbuild also reported missing/mismatched `pahole` and skipped
optional BTF generation because the header package lacks `vmlinux`. These were
not C compiler errors, and module linking/modpost completed. See
`reports/linux-build-7.3.0-9-generic.log` and `reports/linux-static-analysis.log`.

## Fixes and installation testing

- Reused the pinned AJ driver and reviewed upstream resume PR; did not reinvent
  the T1 protocol. See `SOURCES.md` for all four repository audits and issue links.
- Added mandatory ACPI skip enforcement and a verifiable child-slot/open bug fix.
- Exact reverse/forward patch reconstruction is checked against pinned upstream
  SHA256s in `patches/UPSTREAM.sha256`.
- Native tests compile the actual changed HID functions with address/undefined
  behavior sanitizers. ALS-first and not-yet-published child cases pass.
- A second native sanitizer harness extracts the actual ACPI allocation, probe,
  suspend and resume functions. It confirms 0/-1/2 overrides fail before lookup
  and `skip_acpi_power=1` executes **zero** ACPI methods across the lifecycle.
- Transaction tests cover original mode/content restoration, later user edits,
  simulated failure mid-deployment, and symlink refusal.
- All three Ubuntu entrypoints refuse macOS before making changes. Kernel-family
  tests accept generic 7.3.0 ABI updates and reject other families/flavors.
- Initial VM installer trials exposed and fixed two packaging bugs: sourcing
  `/etc/os-release` overwrote common NAME/VERSION constants (now isolated in a
  subshell); `make kernelrelease` in these Ubuntu headers returns **7.3.0-rc6**,
  while their generated ABI identifiers correctly say **7.3.0-9-generic** (now
  those identifiers are checked instead). Failure rollback restored owned files.
- DKMS source inspection found Ubuntu's default key-generation path also invokes
  `update-secureboot-policy --enroll-key`. The package now uses a module-scoped
  signing configuration to avoid that implicit EFI operation. Its certificate
  must already be enrolled when signatures are enforced.

The integration test runs only in a disposable QEMU guest. A private mount
namespace substitutes **synthetic** DMI/USB files; actual Ubuntu headers, DKMS,
module signing, initramfs and systemd configuration are exercised. The production
installer has **no hardware-check bypass option**. The test never starts the
activation service or loads either module. It must not be confused with testing
real iBridge enumeration, HID binding, display output or keys.

Final integration result: the real installer built, signed and installed both
modules under the correct package name; enabled the service without starting it;
generated initramfs; refused a repeated installation; then uninstalled cleanly
and tolerated a repeated uninstall. Actual module signatures passed cryptographic
verification, while a modified module and unrelated certificate both failed.
No module was loaded (`/sys/module` absence checked). DKMS's removal message
"ACTIVE" describes its installed version selection, not a loaded driver.
`systemd-analyze verify` reported only unrelated distribution xfs unit warnings;
`udevadm verify` reported one rule file checked, zero failures.

## Outstanding hardware work

After Ubuntu installation, physically validate Esc, screen brightness, media and
volume key events, Fn hold/release and F1–F12, webcam preview, cold/reboot behavior,
and multiple sleep cycles on AC/battery. Record the selected sleep type.

Known unresolved behavior: T1 dim/off is a no-op in the selected fork; disabled
timers make this explicit. S3 wake may remain dark with ACPI power calls skipped.
The resume patch has external evidence on **13,3**, not this **13,2** firmware.
`skip_acpi_power=1` remains mandatory regardless of these limitations.

No runtime reliability claim or confirmation of physical Ubuntu operation is made.

## Artifacts and reproduction

- Required entrypoints/docs, `driver/`, `patches/`, `config/`, `lib/`, tests and
  selected reports are included in `dist/macbook-t1-ubuntu-1.0.0.tar.gz`.
- `SHA256SUMS` covers package contents; adjacent archive SHA256 covers transfer.
  Packaging uses sorted files, fixed timestamps/ownership and deterministic gzip.
  Validation details: `reports/package-validation.log`.
- `python3 tools/test-macos.py` runs native checks; `python3 tools/package.py`
  rebuilds the portable archive. Linux source validation uses the command above.
  Final additional Linux guard/patch checks are in `reports/linux-final-checks.log`.
- Full research checkouts/issue snapshots and VM tooling/downloads remain local
  under `sources/`, `reports/research/`, and `build-env/`. VM disks, SSH keys,
  macOS account paths and setup logs are excluded from the archive.
- The build VM can be shut down with `bash tools/vm-ssh.sh 'sudo poweroff'`.
  It is a local build environment, not part of Ubuntu installation.
