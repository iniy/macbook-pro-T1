# Ubuntu T1 Touch Bar installation result

Date: 2026-10-19.

Published hardware-validation record. Home-directory paths are shown as `~`;
raw diagnostic logs and signing material remain on the tested machine.

## Outcome

**PARTIAL — Driver installed but physical operation not fully verified.**

Both modules are installed and loaded, the activation service is healthy, and
`verify-ubuntu.sh` passes. The Touch Bar is physically operational: real
brightness, volume, keyboard-illumination and function-key events were captured,
and Fn switching was observed. The user explicitly confirmed Esc and F10 work.
However, individual mute/media-key delivery was not captured, despite a broad
user confirmation of completing the requested checks. Reboot and sleep/wake
have not been tested. These verification gaps prevent an unqualified claim
that every requested function has been verified; no driver runtime failure
was observed.

## Detected system

- Apple **MacBookPro13,2**, board `Mac-66E35819EE2D0D05`.
- Intel Core i5-6267U at 2.90 GHz; nominal 8 GB RAM, Linux reports
  `MemTotal: 7462656 kB`.
- Apple firmware `529.120.1.0.0`.
- Ubuntu **26.10 (Stonking Stingray)**, amd64/x86_64.
- Running and retained kernel: **7.3.0-9-generic**.
- Matching headers: `linux-headers-7.3.0-9` and
  `linux-headers-7.3.0-9-generic`, version `7.3.0-9.9`.
- T1 USB **05ac:8600**, bcdDevice `1.01`, USB path `1-3`, three configurations.
- Secure Boot unsupported by this Apple EFI; efivarfs mounted and SecureBoot
  variable absent. Kernel lockdown `[none]`; `sig_enforce=N`.
- Existing keyboard/trackpad use `applespi`. No previous Touch Bar DKMS package,
  custom Touch Bar module or competing Touch Bar service was found.
- Default initramfs provider: **dracut 112-7**.
- Sleep setting: `s2idle [deep]`; suspend was not exercised.

## Source and compatibility adaptations

Repository: <https://github.com/iniy/macbook-pro-T1>

Clone: `~/macbook-pro-T1`

Base Git commit: **`74a421e1dfab32cf0ce106367d7b3779d5cde3f8`**.
Local development branch: **`local/ubuntu-26.10-desktop`**.
The installer adaptations below were developed and tested on that branch.
No driver C source was changed.

The OS, model, architecture and running-kernel ABI match the published target.
Two installer compatibility details required evidence-based adaptations:

1. Desktop uses dracut; the original dependency list would remove it in favor
   of initramfs-tools. The installer now retains installed dracut, uses its
   distribution-provided `update-initramfs` wrapper and passes `--no-remove`
   to apt. The simulated adapted transaction removed/installed zero packages.
2. This mokutil reports `This system doesn't support Secure Boot` with status
   255. The installer now recognizes that exact message only with mounted,
   readable efivarfs and an absent SecureBoot variable. Kernel signature and
   lockdown checks remain in force.

Changed source/package files: `install-ubuntu.sh`, `RECOVERY.md`,
`tests/test_installer_compat.py` (new), `SHA256SUMS`, and the archive/checksum
under `dist/`. The archive used at installation time had this SHA256:

```text
8c01b9676f41a8aad0c095a9b92620cf98e494d3cf39430fc77d5f17e29be88f
```

The source archive was subsequently regenerated to include this published
hardware report and updated documentation. Its current checksum is in
`dist/macbook-t1-ubuntu-1.0.0.tar.gz.sha256`.

## Installation and files changed

Administrative access required Ubuntu desktop authentication through `pkexec`.
No sudoers or authentication-policy changes were made.

Principal commands executed:

```bash
pkexec --disable-internal-agent /usr/bin/apt-get install -y git build-essential dkms evtest
git clone https://github.com/iniy/macbook-pro-T1.git ~/macbook-pro-T1
git switch -c local/ubuntu-26.10-desktop
# Unprivileged compile in /tmp/opencode/t1-build-7.3.0-9-generic:
make KVERSION=7.3.0-9-generic CC=x86_64-linux-gnu-gcc W=1 -j2
python3 tests/test_source_package.py
python3 tests/test_acpi_guard.py
python3 tests/test_hid_slots.py
python3 tests/test_transactions.py
python3 tests/test_installer_compat.py
python3 tools/package.py
sha256sum --check --quiet SHA256SUMS
# From the repository, in the authenticated administrative installation stage:
sudo ./install-ubuntu.sh --install-deps
# Following module ABI/signature, installed-unit and initramfs inspection:
systemctl start macbook-t1-touchbar.service
sudo ./verify-ubuntu.sh
# Read-only verifier smoke test, without rebooting:
systemctl --user start macbook-t1-postboot-check.service
```

The installer ran `dkms add`, `dkms build`, `dkms install`, `depmod`, udev rule
reload, `systemctl enable macbook-t1-touchbar.service`, and
`update-initramfs -u -k 7.3.0-9-generic` successfully.

Installed package: **macbook-t1-touchbar/1.0.0**.

| Module | Installed location | Source version |
|---|---|---|
| apple_ibridge | `/lib/modules/7.3.0-9-generic/updates/dkms/apple-ibridge.ko.zst` | `495CE8646B84AF392A459B2` |
| apple_touchbar | `/lib/modules/7.3.0-9-generic/updates/dkms/apple-touchbar.ko.zst` | `60828F8B93A7B64AE62358B` |

Both depend on `hid`. Expected ABI string:
`7.3.0-9-generic SMP preempt mod_unload modversions`.
The source does not declare a separate MODULE_VERSION; version 1.0.0 is the
DKMS package version. DKMS signed both modules with the package-scoped key
under `/var/lib/macbook-t1-signing/`; no key enrollment occurred.

Package-managed system paths:

- `/usr/src/macbook-t1-touchbar-1.0.0/`
- `/var/lib/dkms/macbook-t1-touchbar/1.0.0/`
- `/etc/modprobe.d/macbook-t1-touchbar.conf`
- `/etc/udev/rules.d/90-macbook-t1-touchbar.rules`
- `/etc/udev/rules.d/39-usbmuxd.rules` (T1-only exclusion from the vendor rule)
- `/etc/systemd/system/macbook-t1-touchbar.service` and its enablement symlink
- `/usr/local/libexec/macbook-t1-touchbar/{activate.sh,common.sh}`
- `/etc/dkms/framework.conf.d/zz-macbook-t1-touchbar.conf`
- `/var/lib/macbook-t1-ubuntu/` (transaction records, logs, configuration backups)
- `/var/lib/macbook-t1-signing/` (root-only signing material)
- `/boot/initrd.img-7.3.0-9-generic` (rebuilt with dracut)

Persistent options: `skip_acpi_power=1`, `fnmode=1`, `idle_timeout=-1`,
`dim_timeout=-1`. Only the two custom modules are alias-blacklisted to defer
loading until the late-boot service. Essential USB/HID/keyboard/camera drivers
are not blacklisted.

DKMS `AUTOINSTALL=yes` and `BUILD_EXCLUSIVE_KERNEL=^7[.]3[.]0-[0-9]+-generic$`
are retained. Future ABI updates within that family require matching headers;
new kernel families remain excluded pending a compatibility audit.

Additional read-only validation files created locally on the tested machine
(these helpers are not installed by the source package):

- `~/.config/systemd/user/macbook-t1-postboot-check.service`, enabled for the
  user manager's default target.
- `~/t1-install-logs/postboot-check.sh`
- `~/t1-install-logs/capture-touchbar.py` (genuine event reader; no injection
  or exclusive grabs; ordinary keyboard contents are not logged).

## Tests and diagnostic evidence

Passed before installation:

- Complete requested documentation/scripts, driver source, patches, services,
  udev rules, DKMS settings and uninstall/restore code reviewed.
- Clone matched the reviewed commit archive byte-for-byte; original and
  regenerated package checksums passed.
- Both modules compiled and linked against the exact running-kernel headers
  with matching vermagic. Optional BTF generation was skipped because the
  header environment lacks vmlinux/pahole; no C compilation failure occurred.
- ACPI harness: invalid skip values rejected; skip=1 executed zero ACPI
  methods across mocked probe/suspend/resume (ASan/UBSan).
- HID child-slot/open/forwarding regressions (ASan/UBSan).
- Offline reverse/forward patch reconstruction against pinned source hashes.
- All four backup/restore, interruption and later-edit transaction tests.
- Ten Secure Boot/enforcement decision cases and both initramfs-provider
  dependency cases in the added regression test.
- udev rule syntax validation.
- DKMS build, signing and installation; persistent service enablement;
  initramfs generation.

Initial failures and corrections:

- Noninteractive sudo needed authentication; administrative stages use the
  normal Ubuntu desktop authentication mechanism.
- The first backup attempt encountered absent `/etc/initramfs-tools` and
  stopped before running the installer. The backup was corrected to include
  existing dracut paths, and was completed before installation.
- One authentication request timed out before its script started; the later
  authenticated attempt completed.
- Pre-install systemd validation correctly reported the not-yet-installed
  activation executable absent; installed-unit validation subsequently passed
  during activation.
- Baseline kernel logs already contained ACPI table/lookup and early applespi
  packet warnings. Their presence predates this installation.

### Live activation and verification

- Cryptographic PKCS#7 signature verification passed for both installed
  compressed modules against the package certificate.
- Loaded `srcversion` values match the installed modules; installed
  configuration files match the reviewed source byte-for-byte.
- Installed systemd unit validation passed. Both the T1 udev rule and usbmuxd
  exclusion rule passed `udevadm verify`.
- Inspected rebuilt initramfs: the T1 modprobe/udev configuration and essential
  applespi/NVMe components are present.
- Baseline T1 was unconfigured because of the distro usbmuxd rule. After the
  backed-up T1-only exclusion was installed, configuration **1** was selected
  once on the device while no USB interfaces existed. No whole-device
  unbind/rebind, USB reset or authorization toggle was performed.
- USB interfaces `1-3:1.2` and `1-3:1.3` use `usbhid`. Physical HID nodes
  `0003:05AC:8600.0001` and `.0002` bind to `apple-ibridge-hid`.
- Mode/input child `0003:1D6B:0301.0003` binds to `apple-touchbar` and registers
  **`/dev/input/event10`**. Its settings are `fnmode=1`, `idle_timeout=-1`,
  `dim_timeout=-1`.
- `macbook-t1-touchbar.service`: **enabled**, **active (exited)**,
  `Result=success`, `ExecMainStatus=0`.
- `skip_acpi_power=1` is active. Kernel log explicitly confirms that the
  ASOC.SOCW(1) power-on method was **not** executed.
- Repository verifier, including the privileged invocation, returned **0**.
- Existing Apple SPI keyboard/trackpad remain registered and have the expected
  `tbkbd`/`tbtpad` observers. First capture recorded **282 keyboard events** and
  **759 trackpad events**, without logging ordinary typed keys or coordinates.
- External USB Ethernet retains its `cdc_ncm` binding and an **up** link.
  T1 camera interfaces remain with `uvcvideo`; preview was not tested.
- The read-only post-boot verification service was smoke-tested during this
  boot: `Result=success`, `ExecMainStatus=0`; it remains enabled for next login.

### Physical evidence

The user selected **“Controls and Fn work”**, confirming the lit bar, responsive
controls and visible layout changes on Fn hold/release. A second focused test
was confirmed with **“Completed all keys”** for Esc, mute, previous/play/next,
Fn-held F1–F12, then brightness-up after Fn release.

First 150-second non-grabbing evdev capture registered genuine press/release
events for screen brightness up/down, keyboard illumination up/down, volume
up/down and three Fn hold/release cycles. Esc/media/F1–F12 were absent from that
first capture, so a second focused capture was requested rather than inferring
those events from the module's advertised capabilities.

Second 150-second capture registered press/release pairs for **F1–F9, F11 and
F12 while Fn was continuously held**, followed by Fn release. It also recorded
530 keyboard events and 2,011 trackpad events. The user separately and
explicitly stated **“f10 works”** and **“and esc also works”**. These are physical
user confirmations, not evdev records from the first two captures.

A final bounded reader was authorized and confirmed ready before requesting
Esc, mute, previous/play/next and Fn+F10. It closed after 240 seconds with **zero
Touch Bar key events**, while recording keyboard/trackpad activity. This does
not establish that these keys failed; it leaves them without evdev evidence.
No further capture loops or driver configuration changes were attempted.

Final physical coverage:

| Function | Evidence / result |
|---|---|
| Display lights and Fn layout switching | User confirmed working |
| Esc | User explicitly confirmed working; event not captured |
| F1–F9, F11, F12 | Real press/release events while Fn held |
| F10 | User explicitly confirmed working; event not captured |
| Fn release / special-key return | Fn release captured; subsequent special-key events in first test; visual switching user-confirmed |
| Screen brightness up/down | Real press/release events; user confirmed responding controls |
| Volume up/down | Real press/release events; user confirmed responding controls |
| Keyboard illumination keys | Real press/release events; physical illumination changes not separately verified |
| Mute / previous / play-pause / next | User reported completing broad test; individual delivery not captured and remains unverified |
| Keyboard / trackpad | Existing bindings preserved; real activity captured |
| USB | Existing USB Ethernet binding/link preserved; T1 HID/UVC bindings healthy |
| Reboot / sleep-wake | Not performed; remain unverified |

Capture files and JSON summaries are retained in the baseline log directory.
The current service remained enabled/active with exit status 0 after all
capture windows; final kernel diagnostics contained no T1 probe/mode failure,
Oops, BUG or call trace.

### Kernel log interpretation

No T1 mode-transfer/probe failure, kernel Oops, BUG or call trace was observed
after activation. The kernel reports the normal out-of-tree module taint and
`module verification failed: signature and/or required key missing` because the
local signing certificate is not in its trusted keyring. Both signatures were
cryptographically verified before loading; enforcement is off on this system.
Taint value is **12288** (out-of-tree and untrusted-signature flags), not a
detected crash. No key enrollment or enforcement change was made.

## Touch Bar limitations

The driver implements firmware-rendered Esc, special keys and Fn-switched
F1–F12. The working-function results use real input and user observation as
detailed above, not merely module loading. Individual mute/media input delivery
remains a verification limitation.
Automatic Touch Bar display dim/off is unsupported in this fork and its timers
are disabled. Screen-brightness keys are distinct from Touch Bar dimming.
Touch ID and arbitrary app-specific graphics are unsupported. Volume/media
input verification does not establish operation of this Mac's audio hardware.
Sleep/wake reliability and reboot persistence require hardware testing.

## Reboot and post-boot verification

A reboot is not needed to use the already-active Touch Bar, but is still needed
to validate boot persistence. A reboot has not been performed. The active
desktop installation session could not be guaranteed to resume automatically,
so an automatic reboot would have interrupted it.
After saving work, the single reboot command is:

```bash
sudo reboot
```

On the next normal login, the enabled user validation service waits up to 45
seconds for the boot activation service, then runs the repository verifier and
records module/service, HID/input, USB and relevant kernel diagnostics under:

```text
~/t1-install-logs/postboot/<boot-id>.log
```

This mechanism does not simulate physical keys or automatically claim success.
It has been syntax/unit-validated and successfully run on the current boot;
an actual post-reboot run is still pending.

## Backups, logs and recovery

Baseline/user-accessible logs:
`~/t1-install-logs/20261019-104036/`. This contains the original
discovery, installation and activation transcripts, real-input captures,
verification results, the local source patch and executed administrative-stage
scripts. `~/t1-install-logs/LATEST` identifies this directory.

Root-only boot/configuration backups and administrative logs:
`/var/lib/macbook-t1-baseline-20261019/`.
This includes the original kernel and initramfs, checksums, configuration tar,
package/DKMS snapshots and pre-install kernel log. The existing kernel was
retained. No disk partitions, EFI firmware files or firmware settings changed.

Package rollback records: `/var/lib/macbook-t1-ubuntu/`.

Normal removal:

```bash
sudo ~/macbook-pro-T1/uninstall-ubuntu.sh
systemctl --user disable --now macbook-t1-postboot-check.service
sudo reboot
```

The repository uninstaller restores owned configurations, removes its DKMS
registration/modules and rebuilds initramfs through the retained dracut
wrapper. Loaded modules remain until reboot; it does not reset live USB.
Later user edits are preserved for review. Dependency packages, signing
material and diagnostic backups are retained. The extra user validation unit
does not activate hardware and may be removed after disabling it.

If Ubuntu hangs during boot: in GRUB select Ubuntu, press `e`, append to the
`linux` line, then boot with Ctrl-X/F10:

```text
module_blacklist=apple_ibridge,apple_touchbar t1_touchbar.disable=1
```

Once booted, run the uninstaller. If necessary use recovery mode or a live
Ubuntu system with the existing root mounted/chrooted. Restore the saved
original initramfs from the baseline directory if the regenerated boot image
itself is damaged. Do not repartition or format anything.

Keep `skip_acpi_power=1`. Never use SOCW/FRST, unsafe ACPI resets, firmware
flashing, EFI-file replacement or whole-iBridge reset loops. Full procedures:
`RECOVERY.md` and `~/t1-install-logs/RECOVERY-QUICK-REFERENCE.md`.
