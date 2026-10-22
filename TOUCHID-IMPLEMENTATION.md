# Touch ID implementation status

This development branch builds and privately stages T1Bridge, but does **not yet
provide working Touch ID authentication on this Mac**. The released installer
must not activate it until physical, security and regression acceptance passes.

## Implemented

- The default `install.sh` sequence always runs a read-only Touch ID readiness
  and acceptance report. No `--touchid` opt-in is needed for this assessment.
  Missing firmware, model support, headers, systemd or driver compatibility is
  reported explicitly. A blocked Touch ID step preserves baseline installation.
- USB 05ac:8600 and active configuration/driver discovery, distribution/version,
  init, desktop, tools and exact header checks. EFI preflight tests file presence
  only; same-sensor validation belongs to the upstream importer. No payload or
  identifier is included in the public report.
- Locked source retrieval, checksum verification, explicit upstream patch
  application, runtime and kernel compilation, separate synthetic fingerprint
  tests, private prefix installation and removal, local inert DEB construction.
- The libfprint/fprintd pair is built together. Ubuntu's system libraries,
  daemon, PAM files and biometric records are not overwritten. Test-only virtual
  readers are absent from the production library.
- Journaled file transactions preserve original bytes and permissions, reject
  symlinks and unowned files, recover interrupted writes, and refuse to overwrite
  subsequent local edits. These are tested support code; no live PAM transaction
  has been deployed.
- Original license texts and notices accompany staged upstream components.

## Actual adaptations relative to T1Bridge

1. **GNU ld link order.** Upstream emitted recovery dynamic-library directives
   before the native archive. GNU ld with `--as-needed` failed the all-feature
   test link with unresolved curl/archive/crypto symbols. The separate patch
   emits those dependencies after the archive. Runtime policy and recovery
   behavior are unchanged. This benefits GNU-linker builds across distributions;
   Ubuntu is the locally reproduced environment. No kernel dependency.
2. **Build permissions.** A host umask of 0002 produced group-writable synthetic
   recovery directories, correctly rejected by upstream protected-storage code.
   Child build/test commands now use umask 0022. Security checks remain intact.
3. **Private fingerprint packaging.** Arch recipes replace distro libfprint and
   fprintd. This evaluation build puts a matched pair under an immutable-version
   `/opt/macbook-t1-touchid/` prefix and gives the daemon that library path.
   It does not globally redirect the loader or replace PAM modules. Activation
   for the one-boot trial uses a conditional systemd launcher; permanent package
   ownership integration remains pending.
4. **Exact DKMS metadata.** The pinned release's kernel recipe still says 0.1.11.
   Generated source metadata uses 0.1.12 and an exact kernel build restriction.
   DKMS add/build has succeeded locally. Normal installed modules remain unchanged;
   compiled trial modules go into a copied module tree and separate initramfs.
   Kernel-update acceptance remains pending.
5. **Installer reporting and release gate.** Upstream packaging has no knowledge
   of this repository's working legacy Touch Bar and sleep stack. Discovery now
   identifies the conflict and keeps promotion blocked until the complete matrix
   is accepted. Existing sleep files are not changed.

## Remaining implementation and hardware boundary

The current T1 is in USB configuration 1. Upstream SEP transport requires
configuration 2, selected early by `t1_cfgsel`; its Arch package blocks
`apple_ibridge`, `apple_touchbar`, `apple_ib_tb` and `apple_ib_als`. It also
replaces `appletbdrm` and `uvcvideo`. Loading those drivers together or hot-resetting
the USB device is not a safe migration strategy.

The implemented Ubuntu trial uses a separate module-tree copy and initramfs,
a one-time GRUB entry, and boot-flag-conditioned T1Bridge services. It builds via
DKMS without installing modules into the normal module tree. The legacy Touch
Bar service is suppressed only on that trial boot. A conditional fprintd launcher
uses the private daemon on trial boots and the distribution daemon otherwise.
The next ordinary boot retains the original image and drivers. Staging, pre-boot
rollback and restaging succeeded; hardware behavior and post-use rollback await
physical testing.

A new unprivileged PipeWire/MPRIS provider supplies volume/mute/media control and
GNOME display-power state through upstream's documented provider v1 protocol.
It validates fixed actions, uses bounded calls and never participates in
fingerprint authorization. Read-only status and synthetic action tests pass;
physical controls remain unverified.

Secure import, enrollment, matching and keybag persistence are implemented
upstream, but have not been exercised on this host. No fingerprint was enrolled,
no PAM rule was enabled, and no automatic firmware recovery was run. Independent
matching and password-fallback tests must precede sudo/GNOME/GDM activation.
The local EFI backup does not establish successful same-sensor import.

## Development commands

These are maintainer build tools, not a second supported end-user installer:

```sh
python3 touchid/manage.py check --json
python3 touchid/manage.py dependencies
sudo python3 touchid/manage.py dependencies --install-deps
python3 touchid/manage.py build --work sources/touchid-build-clean
sudo python3 touchid/manage.py install-bundle --work sources/touchid-build-clean
python3 touchid/manage.py package-deb --work sources/touchid-build-clean --output sources/touchid-bundle.deb
```

Use a fresh build directory. Builds run without root; installation verifies every
manifest entry and installs only an inert private bundle. The default user entry
point remains `sudo ./install.sh`. It explicitly reports Touch ID as unavailable
until the remaining implementation and acceptance work is complete.

## Further tested packaging adaptations

- Make targets run with Bash explicitly: upstream recipes use brace expansion,
  while Ubuntu's `/bin/sh` is Dash. No system shell is replaced.
- fprintd's private-prefix patch keeps D-Bus and Polkit data within the selected
  prefix instead of following system pkg-config paths into `/usr`. Its `/usr`
  packaging behavior is unchanged. The staged bundle is checked for escaped files.
- libfprint's AppStream generator now includes `FP_DEVICE_TYPE_USB_PRESENCE`.
  A T1-only build otherwise emitted an empty provides list and failed validation.
  This changes metadata only; T1 remains excluded from generated USB power/udev
  policies as required upstream. All applicable tests pass after the change.
- Runtime tests exclude the unpublished Arch release tool. The obsolete direct
  PAM module is not built or installed by this integration; standard pam_fprintd
  is built and its 560 daemon/PAM tests pass. See the explicit exclusions in the
  test report; the complete upstream `make quality` is not claimed to pass.

## Attended trial through the standard entry point

After the verified private bundle is installed, this development-only command
runs the ordinary installer and stages the one-boot trial:

```sh
sudo ./install.sh --no-install-deps --touchid-trial
```

There is no automatic reboot. Return to this chat after restarting for calibration,
physical regression checks and supervised enrollment. Do not enable PAM or enroll
manually before independent verification and GNOME/GDM activation controls are
prepared. A permanent default installation remains gated, rather than silently
turning the development trial into a release.
