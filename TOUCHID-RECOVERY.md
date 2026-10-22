# Touch ID recovery

## Persistent installation and fallback

The default installer now selects **Ubuntu with Touch ID (MacBook T1)** on every
boot of the exact supported target. This uses the isolated image already used
by the trial. A five-second GRUB menu keeps the original **Ubuntu** entry available.
If the persistent Touch ID boot is unusable, restart and explicitly select
**Ubuntu**. Another restart by itself does not revert a persistent selection.

Persistent configuration owns `/etc/grub.d/42_macbook_t1_touchid`,
`/etc/default/grub.d/zz-macbook-t1-touchid.cfg` and the generated GRUB menu in the
same private rollback journal as the trial. It preserves the normal kernel,
normal initramfs, installed module tree, fingerprints and password PAM files.
The image is tied to `7.3.0-9-generic`; a different running kernel is rejected.
The explicit `--touchid-trial` option still selects its image for one boot only.

The user requested persistent activation on 22 October after successful enrollment
and basic matching. The first persistent boot selected the isolated image and
retained the saved fingerprint record. Actual GDM fingerprint login has not been
confirmed. The first reported lid-close sleep cycle left the Touch Bar dark.
With both recovery hooks below installed, the user confirmed automatic Touch
Bar recovery and first-attempt GNOME fingerprint unlock after another cycle.

## Dark Touch Bar after s2idle

T1Bridge 0.1.12 parks its display at suspend but does not write the awake value
at resume. The installer now supplies a narrowly scoped workaround in
`/usr/lib/systemd/system-sleep/90-macbook-t1-touchid-resume`. It runs only after
`suspend`, on MacBookPro13,2 with the T1Bridge boot flag and selected s2idle mode.
It checks the exact T1/configuration/interface and device node, then reads the
display power state. An already-awake panel receives no write. A parked panel
gets the documented awake report, with readback verification and a 15-second
deadline. The display hook never opens the fingerprint transport or changes its records.

A separate `80-macbook-t1-fingerprint-resume` hook addresses the observed unlock
race: the first fingerprint request arrived two seconds before the restarted
keybag relay was ready. Systemd keeps user sessions frozen until its post-sleep
hooks finish. During that interval, this hook stops fprintd and its broker to
release any previous operation, restarts the existing relay and waits for its
`Type=notify` readiness, then restores fprintd if it was previously active.
Otherwise it leaves fprintd available for normal D-Bus activation. Fingerprint
sockets remain enabled. Every command has a timeout; the primary recovery has
a 35-second deadline, and restoring an already-active fprintd on failure gets
one bounded six-second attempt. Errors are logged; no PAM rule, password path or
keybag file is changed.
It skips recovery when no existing keybag is present.

To add both hooks to an existing staged/persistent installation and apply
recovery immediately:

```sh
sudo python3 touchid/manage.py install-resume --user "$USER"
```

This does not suspend or reboot the machine. Both hooks join the existing file
journal and are removed by `rollback-trial`. For read-only display-power diagnosis:

```sh
sudo python3 touchid/resume.py check
journalctl -b -u systemd-suspend.service --no-pager
```

An acknowledged awake value does not prove physical illumination or a successful
fingerprint match. Inspect the keybag/broker logs separately if Touch ID remains
unavailable. Do not delete or re-enroll fingerprints as a recovery step. This
workaround does not attempt S3/deep ACPI wake or a composite USB reset.

## Earlier one-boot trial recovery

For a one-boot trial only, if the desktop is unusable, restart the machine again;
the one-time selection should have been consumed. The normal Ubuntu entry remains
available from GRUB. Do not repeat the trial or attempt live USB resets as a repair.
On 22 October, the user confirmed that the subsequent normal boot restored the
visible Touch Bar. Diagnostics also confirmed configuration 1, both legacy
drivers, the input/control interfaces and the active boot service.

The 22 October trial boot exposed a staging bug: the existing
`90-macbook-t1-touchbar.rules` switched the T1 from USB configuration 2 back to
configuration 1. The replacement display disappeared, while the normal Touch Bar
service was correctly skipped by `t1bridge.trial=1`. If the Touch Bar is blank
after that trial, restart into the normal Ubuntu entry, then run the rollback
command below. The observed GRUB environment had an empty `next_entry`, and
`GRUB_DEFAULT=0` still selected normal Ubuntu.

The corrected staging code wraps that exact legacy rule in a trial-boot guard,
journals its original contents/mode for rollback, and explicitly includes the
guard in the separate trial initramfs. Ordinary boots keep the configuration-1
rule. Missing or locally modified rules stop staging for inspection. The corrected
trial has now retained configuration 2 with a visible Touch Bar. Restaging also
accepts GRUB's consumed, empty `next_entry=` value while refusing any nonempty
pending choice, and checks the guard's exact contents in the new trial image.
The corrected trial was rebuilt and armed on 22 October after the successful
normal-boot recovery. The installed guard passed `udevadm verify`, its contents
matched the extracted trial-image copy, and GRUB reported
`next_entry=macbook-t1-touchid-trial`. The normal Touch Bar remained active
through staging. A later trial exposed an importer/readiness race; staging now
starts import after the private xART service signals readiness. The current trial
completed same-sensor import and GNOME Settings enrollment. Independent matching
accepted the enrolled left index finger and rejected the unenrolled right index
finger. The Touch Bar services remained active with zero restarts. Reboot
persistence and full authentication/regression acceptance remain untested.

To remove persistent Touch ID boot or cancel an armed trial, first select normal
**Ubuntu** if currently running the T1Bridge image, then use:

```sh
sudo python3 touchid/manage.py rollback-trial
```

Rollback disables only the trial units, restores its journaled files, clears its
own pending boot choice, removes the trial image and DKMS build registration,
restores the original GRUB menu, removes the persistent generator/default drop-in,
and reverses only the added user group membership. It retains private recovery
records and all calibration/biometric state. It refuses hot rollback while booted
with `t1bridge.trial=1`: first return to the normal boot. Staging/rollback/restaging
have been tested before boot. Rollback after the failed hardware trial also
succeeded on 22 October; rollback after a working Touch ID session is untested.

The optional `macbook-t1-volume-osd@local` GNOME user extension was installed
separately to show volume/mute feedback. It is inert on normal boots and is not
part of the root-owned rollback transaction. Its independent removal commands
are in `touchid/gnome-volume-osd/README.md`. A sign-out/sign-in loads it without
leaving the current T1Bridge boot. With persistent installation, reboot selects
Touch ID again; choose normal Ubuntu explicitly when a fallback is needed.

The corrected restaging verified the normal kernel, initramfs and `grub.cfg`
against the original trial baseline and preserved all 31 current PAM files.
Its private verification record is
`/var/tmp/macbook-t1-corrected-trial-0dlmwm2l/` (root-only); the earlier guard-only
restaging record is `/var/tmp/macbook-t1-corrected-trial-97ubdzjb/`.

Remove the private bundle with:

```sh
sudo python3 touchid/manage.py remove-bundle
```

Removal verifies the manifest and refuses to delete modified files or a bundle
referenced by systemd/PAM/D-Bus configuration. Inspect a reported conflict; do not
force removal. Removal never deletes EFI, `/var/lib/t1bridge`, fingerprint records,
existing drivers, or build dependencies. Reinstallation of an identical bundle is
safe; a different/edited bundle requires deliberate review rather than overwrite.

The local baseline is in `/var/backups/macbook-t1-touchid/baseline-20261022`, mode
0700, with configuration archive, driver/package inventory, EFI `EMBEDDEDOS`
backup, and the current kernel/initramfs copies. These are private machine-local
backups, **not an off-device disaster-recovery backup**. The archive reported one
absent legacy state directory (`/var/lib/macbook-t1-sleep`); the actual sleep
configuration under `/etc/systemd/system` and boot configuration was captured.
Do not publish or upload this directory. No credential is stored in project code.

## Trial invariants and remaining validation

1. Preserve a tested boot/recovery route using the saved kernel/initramfs and
   configuration, with accessible local password login and a root recovery shell.
2. Inventory all overrides and DKMS owners. The legacy firmware-mode drivers
   cannot run together with T1Bridge's configuration-2 stack. Do not hot-unbind,
   deauthorize, reset or reload the live T1 to avoid a reboot.
3. The pre-boot transaction and inverse pass; validate them after hardware use. Keep
   the current sleep wrapper and audio recovery intact. Verify camera format
   compatibility and Touch Bar desktop media/volume controls.
4. Confirm the normal boot fallback during physical testing. Do not mark
   rollback validated just because a backup exists or a mock test passed.

## Missing Apple machine data

The upstream importer requires this Mac's
`EFI/APPLE/EMBEDDEDOS/FDRData`. Presence is not proof of validity; import must
match it to the live sensor. Use preserved local EFI or an explicitly selected
same-Mac backup. Never use donor data or fabricated records. An unreadable source
is not proof it was lost.

Automatic same-sensor import has succeeded in the current corrected trial; no
manual re-import is needed. If deliberate recovery from a same-Mac backup is
needed in the future, upstream's local command is:

```sh
sudo /opt/macbook-t1-touchid/0.1.12-81cbdf8/bin/t1bridge machine-data import --from /absolute/path/to/same-mac-backup
```

Do not run that command to work around a conflicting driver stack.
Upstream documents restoring macOS on this machine through a complete first boot
as a way to regenerate lost data. That can erase Linux; it requires separate
backup and deliberate recovery planning. This installer never restores macOS,
formats partitions, or invokes upstream's experimental online recovery.

## Authentication safeguards

Keep PAM unchanged until independent enrollment, correct-finger matching and
incorrect-finger rejection succeed. Use distribution-supported pam_fprintd
integration per consumer with bounded attempts/timeouts and working password
fallback. Test unavailable module, broker, device and socket conditions. GNOME,
GDM and sudo require separate evidence. The GDM password path must remain intact.
Before removing any future active stack, restore and verify password login first,
then reverse the journaled service and driver changes and rebuild the initramfs.
