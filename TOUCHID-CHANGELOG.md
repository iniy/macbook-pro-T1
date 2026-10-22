# Touch ID change log

## 2026-10-22 — persistent one-shot installation

- Enabled Touch ID by default in the one-shot installer at the user's request,
  scoped to MacBookPro13,2, Ubuntu 26.10 x86_64 and kernel `7.3.0-9-generic`.
  Added `--no-touchid` and explicit account selection; retained one-boot trial mode.
- Added prerequisite checks, missing runtime/build dependencies, source builds
  as the desktop user, and verified reuse of the existing private bundle.
- Reused the isolated boot image for a persistent GRUB default, keeping normal
  Ubuntu in a five-second menu. Journaled boot changes support rollback and
  reject subsequent local edits. Existing fingerprints and password PAM rules
  are preserved; no automatic reboot or enrollment occurs.
- Included the optional GNOME 51 volume OSD extension in desktop installation,
  preserving disabled-extension preferences.
- Passed 95 repository tests, including 37 Touch ID and 9 one-shot tests.
  No physical fingerprint tests were repeated; full acceptance remains pending.

## 2026-10-22 — development integration, not promoted

- Recorded baseline revision `ffa6df7`, kernel and drivers; the initial checkout
  was clean. Created a dedicated `codex/touchid-integration` branch.
- Preserved root-only system-configuration, EFI and boot-image backups locally.
- Pinned T1Bridge 0.1.12 and its matching libfprint/fprintd source revisions.
- Added read-only preflight, distribution dependency adapters, source build and
  private-bundle lifecycle code, acceptance reporting in the default installer,
  and failure-path tests.
- Added a minimal GNU linker-order patch, build umask control, exact-ABI DKMS
  staging and upstream notices. No biometric protocol was rewritten.
- Kept driver replacement, PAM activation and default installation gated. Full
  physical and one-shot Touch ID acceptance remain incomplete.

See TOUCHID-IMPLEMENTATION.md for the original limitations and precise changes,
TOUCHID-TEST-RESULTS.md for evidence, and the patch directory for an auditable
upstream delta. No success is inferred from a compiled binary or started service.

- Built and installed a private matched fingerprint stack; verified removal and
  reinstall without replacing distribution libraries or PAM.
- Added a conditional, separate-image one-boot Ubuntu trial, original desktop
  provider, and source-lock-checked fingerprint packaging patches.
- Validated real pre-boot staging, rollback and restaging. Normal boot-file
  hashes stayed unchanged. The normal installer repeat run passed.
- Runtime Rust: 1,046 pass / 3 ignored; libfprint: 98 pass / 33 unrelated-driver
  skips; fprintd/PAM: 560 pass. Full physical and reboot acceptance remain pending.
- Fixed trial USB configuration switching by guarding the legacy udev rule and
  checking its exact bytes in the trial initramfs. Preserved ordinary-boot behavior.
- Accepted consumed empty GRUB boot choices while preserving pending choices;
  ordered machine-data import after private xART readiness.
- Confirmed same-sensor import, left-index enrollment and matching, rejection of
  an unenrolled right index finger, visible Touch Bar, and volume/mute controls.
  Retained the initial keybag-preparation failure and untested acceptance rows.
- Added an optional GNOME 51 volume OSD extension, inactive outside trial boots.
  Syntax and packaging pass; sign-out/sign-in and visual acceptance remain pending.
- Re-ran the complete top-level suite: 81 tests passed before publishing to main.
