# Touch ID implementation status

This development branch builds and privately stages T1Bridge. **Physical
enrollment, correct-finger matching and wrong-finger rejection now pass in the
one-boot trial.** At the user's explicit request, persistent boot is now enabled
on the development host and included in the one-shot installer for that exact
model/OS/kernel target. Login, unlock, sudo, reboot persistence and the remaining
physical acceptance checks are still pending; enabling installation does not
mark those checks as passed.

## Implemented

- The default `install.sh` sequence checks the Touch ID host/account first, then
  installs persistent support after the baseline hardware components. No separate
  Touch ID opt-in is required. `--no-touchid` skips it; `--touchid-trial` retains
  one-boot staging. Missing firmware or unsupported targets fail preflight.
- Fresh installation obtains missing packages, builds locked sources as the
  desktop user, verifies and privately installs the bundle, and stages a separate
  boot image. A new GRUB entry becomes the persistent default with normal Ubuntu
  available in a five-second menu. There is no live USB switch or automatic reboot.
- Existing private bundles and persistent installations are verified and reused.
  The account, exact kernel, boot/image hashes and journaled files must match.
  Fingerprints are neither read nor deleted. Failed promotion restores only its
  new boot files; full rollback restores the original menu and removes its
  generator/default drop-in.
- The one-shot installer includes a root-owned system-sleep hook for the
  MacBookPro13,2 T1Bridge s2idle path. It dynamically finds the display HID
  interface and restores the awake value only when feature report 3 says the
  panel is parked. It checks the readback and reports errors; it does not reset
  USB, switch configurations, call ACPI methods or touch biometric storage.
  Existing installations can add it with `touchid/manage.py install-resume`.
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
   identifies the conflict and keeps physical acceptance separate from the
   explicitly requested exact-target installation. Existing sleep files are not
   changed by the Touch ID component.

## Remaining implementation and hardware boundary

The normal boot uses USB configuration 1; the current corrected trial uses
configuration 2. Upstream SEP transport requires
configuration 2, selected early by `t1_cfgsel`; its Arch package blocks
`apple_ibridge`, `apple_touchbar`, `apple_ib_tb` and `apple_ib_als`. It also
replaces `appletbdrm` and `uvcvideo`. Loading those drivers together or hot-resetting
the USB device is not a safe migration strategy.

The implemented Ubuntu trial uses a separate module-tree copy and initramfs,
a one-time GRUB entry, and boot-flag-conditioned T1Bridge services. It builds via
DKMS without installing modules into the normal module tree. The legacy Touch
Bar service is suppressed only on that trial boot. A conditional fprintd launcher
uses the private daemon on trial boots and the distribution daemon otherwise.
The one-boot mode returns to the original image afterward. Persistent mode uses
the same isolated image and `t1bridge.trial=1` service guard on every selected
Touch ID boot; normal Ubuntu uses the original image and drivers. Staging, pre-boot
rollback and restaging succeeded. The legacy udev rule is guarded on trial boots
to preserve configuration 2, and machine-data import waits for xART readiness.
Sensor operations and visible Touch Bar availability now pass; full hardware
regression and rollback after successful enrollment remain pending.

On the first observed persistent boot, a lid-close s2idle cycle completed but
the user reported both Touch Bar darkness and unavailable Touch ID afterward.
The display device and services remained present; the keybag relay logged a
lost connection and recovered after one automatic restart. A saved fingerprint
record remained listed. The installed 0.1.12 display driver parks the panel on
suspend but omits its awake write on resume. The downstream hook addresses that
specific omission, following the protocol evidence in upstream
[PR #47](https://github.com/standardagents/t1bridge/pull/47) and
[issue #18](https://github.com/standardagents/t1bridge/issues/18). The live helper
changed parked to awake, and the user confirmed both Touch Bar and Touch ID
working again. Automatic recovery across a further sleep cycle remains pending;
the test report records the observed scope. S3/deep sleep is outside this hook's
scope.

A new unprivileged PipeWire/MPRIS provider supplies volume/mute/media control and
GNOME display-power state through upstream's documented provider v1 protocol.
It validates fixed actions, uses bounded calls and never participates in
fingerprint authorization. Read-only status and synthetic action tests pass;
the user confirmed physical volume and mute control. The optional GNOME 51
extension in `touchid/gnome-volume-osd/` supplies the native OSD for external
volume changes during T1Bridge boots. The one-shot installer installs it as the
desktop user while preserving disabled-extension preferences. It loaded in the
subsequent normal session, where its boot guard kept it inert; visual confirmation
on a T1Bridge boot and other control checks remain pending.

Automatic same-sensor import, GNOME Settings enrollment and independent matching
were exercised on this host on 22 October 2026. A left index fingerprint matched;
an unenrolled right index fingerprint was rejected. The initial terminal
enrollment failed during keybag preparation before the later Settings enrollment
succeeded; the cause remains unproven. Reboot persistence is untested. No PAM
rule was enabled and no automatic firmware recovery was run. Consumer-specific
authentication and password-fallback acceptance remain required for
sudo/GNOME/GDM. See TOUCHID-TEST-RESULTS.md for the exact observed scope.

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
point remains `sudo ./install.sh`. The separate `check`/`auto` commands remain
read-only acceptance reports; they do not enroll or activate anything.

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

There is no automatic reboot. After restarting, confirm import and service
readiness before supervised enrollment. GNOME Settings → System → Users provides
the fingerprint enrollment interface when the trial reader is available;
`gnome-control-center system users` opens that panel. Verify the enrolled finger
and rejection of an unenrolled finger independently before authentication
integration. Keep PAM unchanged until consumer-specific activation and password
fallback tests are prepared. Persistent boot is now the default installation path
on the exact supported target; the trial option remains a one-boot alternative.
