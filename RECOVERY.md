# Recovery and rollback

## Wi-Fi component recovery

Keep Ethernet available and run `sudo ./uninstall-wifi.sh` to restore only the
Wi-Fi component's unchanged owned files and individual profile settings.
Backups are retained under `/var/lib/macbook-t1-wifi-removed-*`; the initial
hardware session also has `/var/backups/macbook-t1-wifi-baseline`.
These root-only archives can contain credentials: never publish them.

An installation/update is idempotent; an interrupted transaction must be removed
before reinstalling. Later user edits are preserved and listed in the private
transaction journal. If only selected fields changed, restore those fields
deliberately rather than replacing an entire NetworkManager profile/archive.
APT-provided firmware and diagnostic dependencies are shared and retained.

The optional DMA DKMS module has a separate `--dma-only` rollback mode.
See [WIFI-RECOVERY.md](WIFI-RECOVERY.md) for exact-source installation,
kernel-update checks, private backups and rollback instructions.

**Do not immediately unload brcmfmac after disconnecting or unmanaging Wi-Fi.**
An asynchronous P2P teardown race caused two kernel crashes during this
investigation. The old live-reload instructions have been withdrawn. Install
or remove the module on disk and use a normal reboot with saved work to apply
it. No T1, USB, audio, camera, NVMe or ACPI reset is part of Wi-Fi recovery.

`journalctl -b -u macbook-t1-wifi-verify.service` shows the read-only post-boot
check. Wi-Fi verification does not establish physical Touch Bar or audio tests.

## Audio/camera component recovery

Keep the working Touch Bar while removing audio:

```bash
sudo ./uninstall-audio.sh
sudo reboot
```

DKMS restores the archived stock CS8409 module, the owned WirePlumber/signing
configuration is restored, and initramfs is rebuilt. The live audio module is
left alone until reboot. The camera and iBridge are not reset.

If the custom codec prevents boot, append this to GRUB's `linux` line for one
boot, then uninstall audio once logged in:

```text
module_blacklist=snd_hda_codec_cs8409
```

This also blocks the stock codec for that one boot; the next normal boot after
removal restores the distribution codec. The original running kernel and
pre-audio initramfs were backed up before installation. No new kernel is needed.

Camera removal only unregisters this project's camera component:

```bash
sudo ./uninstall-camera.sh
```

It leaves the distribution `uvcvideo` and shared T1 configuration intact.
`sudo ./uninstall-ubuntu.sh --all` removes the post-login verification service,
then Wi-Fi, camera registration, audio and Touch Bar in dependency order. Removing
Touch Bar alone is refused while camera registration still depends on it.

Audio transaction logs/backups: `/var/lib/macbook-t1-audio/`.
Audio source: `/usr/src/macbook-t1-audio-1.0.0/`.
Root-only signing material: `/var/lib/macbook-t1-audio-signing/` (retained on
removal). Verification runtime ownership: `/var/lib/macbook-t1-suite/`.
Later edits are preserved by the same edit-aware restore mechanism as Touch Bar.

Never troubleshoot weak output by writing amplifier registers or playing via
direct ALSA `hw:`/`plughw:`. Check software attenuation, the selected output port,
PipeWire and the documented PCM software-volume layer first. Test helpers use
deliberately quiet signals and return to mute afterward. If recording works in
PipeWire but an already-running Firefox reports no microphone after an audio
service reload, try the isolated browser test or restart Firefox normally after
saving work; keep normal microphone permissions enabled.

Audio DKMS builds use the exact Ubuntu source-package version of the target
kernel headers. The initial `7.3.0-9.9` source subset is bundled. For a later
7.3.0 ABI, install matching headers and the **matching version** of
`linux-source-7.3.0`, then run `sudo dkms autoinstall -k "$(uname -r)"`.
A source-version mismatch or patch failure is a blocker, not a reason to use
an unrelated tarball. Keep the previously bootable kernel available.

## Touch Bar-only removal or interrupted installation

From the copied package on Ubuntu:

```bash
sudo ./uninstall-ubuntu.sh
```

Reboot normally. Removal disables only this package's service, removes its DKMS
registration/modules, restores backed-up configuration, and refreshes initramfs.
It does not unload live modules or reset the shared USB device. Dependency packages
installed through apt and `/var/lib/macbook-t1-signing` are retained. That root-only
directory contains a signing key/certificate or links to an existing Ubuntu key.

A failed install attempts the same owned-file rollback and retains diagnostics in
`/var/lib/macbook-t1-ubuntu`. Run the uninstaller to complete/acknowledge rollback
before retrying. Look at `build.log`, `install.log`, and `files.json` there.

If a configuration was edited after installation, restoration stops and preserves
it. `files.json` lists the unresolved paths; `backups/` contains original files.
Save the edited file under a different name, then rerun the uninstaller to restore
the original (or remove the package-created file). Never delete all of
`/etc/modprobe.d`, `/etc/udev/rules.d`, or unrelated DKMS packages.

## Ubuntu hangs during boot

In GRUB, select an entry and press `e`. Append this to its `linux` line for one boot:

```text
module_blacklist=apple_ibridge,apple_touchbar t1_touchbar.disable=1
```

Boot with Ctrl-X/F10. Kernel `module_blacklist` also blocks explicit loads; the
second parameter prevents this package's service from running. Once booted, run
the uninstaller. Alternatively select a previously working kernel under GRUB's
Advanced options. These instructions concern a future Ubuntu recovery boot.

If normal boot is unavailable, use Ubuntu recovery mode or a live environment and
an appropriately mounted/chrooted Ubuntu root, then remove this package. Disk
selection/mounting is deliberately not automated. Never repartition or format to
recover a driver installation.

## Touch Bar dark, absent, or broken after sleep

1. Run `sudo ./verify-ubuntu.sh`. Check for USB **05ac:8600**, configuration **1**,
   `skip_acpi_power=1`, physical HID ownership, and a virtual **1d6b:0301** input.
2. Inspect the local service error with
   `sudo journalctl -b -u macbook-t1-touchbar.service --no-hostname`.
   Raw logs can contain identifiers; review/redact them before sharing.
3. If initialization failed at boot, a normal reboot is preferable to a live
   whole-device unbind. The late-boot service can be retried with
   `sudo systemctl restart macbook-t1-touchbar.service`; it only claims missing
   HID bindings and **does not guarantee relighting an already-bound dark bar**.
4. For failed sleep recovery, save work and reboot. Avoid further suspend cycles
   until tested. There is no supported ACPI-based wake workaround in this package.
5. If the T1 is in recovery mode (`05ac:1281`) or missing, shut down normally,
   leave the machine off for at least 15 seconds, then boot again. If available,
   boot the preserved macOS installation and confirm the Touch Bar there first.

**Never use `skip_acpi_power=0`, `ASOC.SOCW(1)`, `ASOC.FRST`, ACPI-call hooks, or
firmware flashing to force this driver to load.** This build rejects a disabled
guard. A timeout around a userspace command cannot interrupt a kernel AML hang.
Do not authorize/deauthorize or unbind the entire iBridge as a routine recovery:
the webcam shares that device.

T1 initialization depends on Apple's existing firmware resources, commonly under
`EFI/APPLE/EMBEDDEDOS`. Their presence on this disk was not audited or changed.
This package cannot recreate missing firmware or identity/calibration data.

## Secure Boot / signature enforcement

The installer reads Secure Boot, kernel lockdown and signature-enforcement state.
On older Apple EFI without a SecureBoot variable, absence is accepted only when
efivarfs is mounted/readable and mokutil specifically reports that variable
missing or reports "This system doesn't support Secure Boot". The SecureBoot
variable must be absent in either case; kernel enforcement is checked separately.
Unreadable/ambiguous state causes failure.

On Ubuntu 26.10 Desktop, the installer retains the installed dracut provider
and uses its distribution-supplied `update-initramfs` compatibility command.

DKMS signs through a module-scoped framework drop-in. It reuses an existing Ubuntu
key when available, otherwise creates a root-only local key without enrollment.
This avoids DKMS 3.2's implicit `update-secureboot-policy --enroll-key` fallback.
If signatures are enforced, the
installer requires an **already enrolled** certificate and cryptographically
verifies each built module's PKCS#7 signature against it. Pending enrollment is not accepted.
It never changes EFI/NVRAM or disables signature validation.

If enrollment is needed, stop and obtain explicit approval for that EFI change.
The certificate path is printed by DKMS in the retained `build.log` (usually
`/var/lib/macbook-t1-signing/MOK.der`, possibly a link to an existing Ubuntu key).
After approval, use
Ubuntu's normal MOK enrollment procedure for **that certificate**, reboot through
shim/MokManager to confirm it, check `mokutil --test-key <certificate>`, then rerun
installation after clearing the failed transaction with the uninstaller.
Signing/enrollment under actual Secure Boot has not been hardware-tested here.

## Kernel updates / conflicts

If special keys work but Fn does not, inspect keyboard remappers such as keyd,
kanata or input-remapper. An exclusive grab of the Apple SPI keyboard prevents
the driver seeing `KEY_FN`; this is reported upstream. Resolve that remapping
deliberately rather than replacing the keyboard driver. No remapper is disabled
automatically by this package.

For a supported 7.3.0 generic ABI:

```bash
sudo apt install "linux-headers-$(uname -r)"
sudo dkms autoinstall -k "$(uname -r)"
sudo ./verify-ubuntu.sh
```

If the kernel is outside `7.3.0-*-generic`, use the previous kernel while obtaining
an audited update. DKMS's exclusive-kernel rule may skip such an update; it is not
a promise of compatibility. Build logs are under
`/var/lib/dkms/macbook-t1-touchbar/1.0.0/`.

Existing apple-ib-drv/apple-touchbar/mbp-t1-touchbar packages, old Touch Bar boot
configuration, or active tiny-dfr/t1bar services must be resolved using their own
uninstall instructions. Review any old uninstaller before running it; some remove
unrelated applespi packages. This package never globally blacklists `hid-generic`,
`hid-sensor-hub`, `usbhid`, `uvcvideo` or Apple keyboard drivers.

The backed-up usbmuxd override excludes only **05ac:8600**. If usbmuxd is upgraded,
compare the vendor rule in `/usr/lib/udev/rules.d` with its `/etc` override to keep
other device fixes current. Uninstall restores the original override or removes
the package-created one, exposing the current vendor rule again.
