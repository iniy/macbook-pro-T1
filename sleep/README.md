# MacBookPro13,2 suspend/resume workaround

The Apple S3X NVMe controller (`106b:2003`) on this model needs PCI D3cold
disabled to avoid a known resume failure. The workaround is documented by
[Dunedan/mbp-2016-linux](https://github.com/Dunedan/mbp-2016-linux#suspend--hibernation).
It addresses a shared device power transition used by lid-close, idle-timeout,
and manual suspend.

## Install and verify

From the repository root:

```bash
sudo ./sleep/manage.sh install
./sleep/manage.sh verify
```

Installation verifies the machine model, PCI vendor/device IDs and driver,
installs a model-restricted udev rule, reloads the rules, and writes `0` to
the controller's `d3cold_allowed` attribute immediately. The rule reapplies
the setting during PCI device discovery on subsequent boots. A conflicting
existing rule is rejected. An installation failure restores the previous live
setting and removes a newly created rule.

The installer does not suspend or reboot the machine. It preserves the selected
sleep mode, desktop timeouts, lid policy, drivers and wake sources. Disabling
one storage power state can increase power consumption; actual sleep drain
needs measurement. No claim of a kernel or driver root cause is made from a
truncated journal alone.

## Evidence and acceptance

On 21 October 2026, the inspected MacBookPro13,2 ran Ubuntu 26.10 with kernel
`7.3.0-9-generic`. The Apple SSD at `0000:01:00.0` had `d3cold_allowed=1`,
`s2idle [deep]` was selected, and the existing T1 guard had
`apple_ibridge.skip_acpi_power=1`. Two earlier boots ended with
`PM: suspend entry (deep)`, at 12:16:16 and 19:35:45 IST, without recorded
resume. The user reported a black/frozen machine requiring forced power-off.
This is consistent with the documented SSD issue, but does not prove that it
is the only fault.

The workaround was applied on the same date. The installed root-owned rule
passed `udevadm verify`, and the live controller read back `d3cold_allowed=0`.
Shell syntax and ShellCheck checks passed. The user elected to perform the
lid-close and idle-timeout tests later, so no physical suspend was initiated.

After installation, save open work before testing:

1. Suspend from the desktop menu, wait 20 seconds, and wake the machine. Allow
   up to a minute for the first resume; upstream reports slow wake on this model.
2. Close the lid, wait 20 seconds, reopen it, and check that the session returns.
3. Let the configured idle timer suspend the machine and verify wake again.
   A screen blank alone is not a suspend. On the inspected user's account,
   battery idle suspend is 15 minutes; AC idle suspend is disabled. Another
   logged-in user's GNOME power manager initiated the recorded failures.
4. Check the display, keyboard, Touch Bar, sound, Wi-Fi and file access after
   each cycle. Repeat on battery and AC and recheck after reboot.

```bash
./sleep/manage.sh verify
journalctl -b -k --no-pager -g 'PM: suspend|nvme|Touchbar'
```

A configuration check is not a physical sleep/wake test. Hardware acceptance
remains pending until the actual cycles succeed. If it still freezes, inspect
the previous boot (`journalctl -b -1 -k`) and diagnose the next failing layer;
do not stack unrelated kernel parameters or disable sleep as a claimed fix.

## Removal

```bash
sudo ./sleep/manage.sh uninstall
```

Removal deletes only the matching rule and reloads udev. The live setting
stays at `0` until reboot, when the kernel default applies again. No automatic
reboot is performed.
