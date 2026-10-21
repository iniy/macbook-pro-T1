# MacBookPro13,2 suspend/resume workaround

The Apple S3X NVMe controller (`106b:2003`) on this model needs PCI D3cold
disabled to avoid a known resume failure. The workaround is documented by
[Dunedan/mbp-2016-linux](https://github.com/Dunedan/mbp-2016-linux#suspend--hibernation).
It addresses a shared device power transition used by lid-close, idle-timeout,
and manual suspend.

**NVMe-only workaround: insufficient on the tested system.** The user reported that
deep sleep still left the machine black and unresponsive after waiting over a
minute. The NVMe rule is installed and still reads back `0` after reboot.
Configuration verification must not be treated as successful sleep/wake.

A later controlled s2idle trial completed successfully. The guarded systemd
s2idle integration is now installed on the target machine. Normal cycles returned,
but audio failed after wake; the playback recovery described below still needs
physical sleep/wake acceptance. The one-shot installer now
includes the NVMe rule, the guarded s2idle integration and its required PCIe boot
setting. `./install.sh --no-sleep` skips all three.

## Install and verify

Use `sudo ./install.sh` for the complete setup. For only the sleep components,
run these commands from the repository root:

```bash
sudo ./sleep/manage.sh install
sudo systemd-inhibit --what=sleep:shutdown --mode=block \
  --why="Configure MacBook suspend support" python3 sleep/manage-resume.py install
./sleep/manage.sh verify
python3 sleep/manage-resume.py verify
```

The resume manager stages `pcie_port_pm=off` in GRUB, verifies generated boot
entries, and installs the guarded systemd suspend configuration. It preserves
existing kernel arguments, accepts the exact original trial drop-in and published
pre-audio-recovery wrapper as migrations, and rolls back managed files, the boot
menu and live mode on failure. Other local modifications are preserved.
It does not require the new boot setting to already be active. If a restart is
needed, it reports that explicitly and leaves the live mode alone; normal
suspend is refused by the runtime guard until the restart. The verification
command returns a failure while that required restart is pending. After the
restart, rerun verification and perform the physical acceptance tests.

The NVMe step verifies the machine model, PCI vendor/device IDs and driver,
installs a model-restricted udev rule, reloads the rules, and writes `0` to
the controller's `d3cold_allowed` attribute immediately. The rule reapplies
the setting during PCI device discovery on subsequent boots. A conflicting
existing rule is rejected. An installation failure restores the previous live
setting and removes a newly created rule.

The NVMe step does not suspend or reboot the machine. It preserves the selected
sleep mode, desktop timeouts, lid policy, drivers and wake sources. Disabling
one storage power state can increase power consumption; actual sleep drain
needs measurement. No claim of a kernel or driver root cause is made from a
truncated journal alone.

## Audio recovery after normal wake

On the same machine, boot `e57352cf-a465-407c-bc8f-21a894e0f546` completed three
normal systemd s2idle cycles at 22:56, 22:59 and 23:03 IST on 21 October 2026.
The user reported silent audio after wake. PipeWire was running, the analog
output was unmuted, and ALSA reported a running playback PCM, but both speaker
converters (nodes `0x02` and `0x03`) had stream ID `0`. GPIO setup remained intact.
Closing the PipeWire sink with `pactl suspend-sink` and allowing it to reopen
restored stream ID `1` on both converters during a quiet speech test. Transport
success does not establish audible playback; listening confirmation is separate.

The vendored driver's prepare hook only performs playback setup on the first
prepare call, tracked by `play_init_count`. PCM cleanup/open resets that counter;
its suspend/resume hooks do not. This explains why keeping the PCM open across
sleep can skip programming the cleared converter stream IDs. The upstream
[codec reset proposal](https://github.com/davidjo/snd_hda_macbookpro/pull/220)
addresses a zero GPIO mask after loss of codec power; that signature was absent
here, so the kernel driver has not been replaced with that patch.

`audio.py` now runs after the normal `systemd-sleep` invocation has thawed users,
including when sleep aborts. It cycles only active CS8409 analog playback sinks
in logged-in audio sessions. Client connections, volume, mute, microphone and
other outputs are preserved. Already suspended sinks are left alone. Session
commands run as their own user and have a timeout; a failed suspend command still
attempts to clear its suspension. A logged-out or restarted audio server is
skipped during restoration. Recovery errors are reported by the suspend service.

A live playback test showed that PipeWire immediately reopens the PCM when a
client is playing, even after `pactl suspend-sink 1`. The helper therefore runs
after wake, when that reopen resets the driver and is useful. It does not depend
on keeping a device suspended while its clients remain active.

The live recovery sequence also passed with a continuous silent PulseAudio client:
the PCM trigger timestamp advanced, both speaker stream IDs returned to `1`,
the client connection stayed present, and volume/mute/output-port values matched
before and after. This test did not suspend the machine or prove audible output.

The sleep installer deploys this helper, so rerunning `sudo ./install.sh` includes
the change without rebuilding the audio driver. The narrower sleep installation
command above also updates it. No reboot is required when the PCIe boot setting
is already active. Validate with music playing before sleep, then resume without
refreshing the browser; repeat with the output idle before sleep. Check both
speaker channels and the microphone separately.

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
has failed on this machine; it remains unresolved until actual cycles succeed.
If it still freezes, inspect
the previous boot (`journalctl -b -1 -k`) and diagnose the next failing layer;
do not stack unrelated kernel parameters or disable sleep as a claimed fix.

## Follow-up investigation, 21 October 2026

Two post-installation boots ended at `PM: suspend entry (deep)`:

| Boot ID | Last recorded suspend entry (IST) |
|---|---|
| `940811d4e53c4fc9b913071eb226aabd` | 21:34:48 |
| `a94985893703420dbdce3fca72ab8c3f` | 21:36:20 |

The second attempt was initiated by lid close at 21:36:18. Neither boot has a
recorded suspend exit. On the subsequent boot, both the installed rule and live
NVMe `d3cold_allowed=0` passed verification; `s2idle [deep]` and
`apple_ibridge.skip_acpi_power=1` were unchanged. There is no captured live NVMe
readback at the precise moment of either failed suspend. The current readback
confirms boot persistence, not that historical detail.

Systemd froze `user.slice` and reached the kernel suspend request. The journal
then stops. Kernel messages after processes freeze may never reach disk if the
machine hangs, so this does not distinguish device suspend, platform entry,
resume or display failure. The Wi-Fi ARP-table warning preceding suspend also
occurs during ordinary boot; it is not enough to blame Wi-Fi. No panic dump was
found in `/var/lib/systemd/pstore`; the live `/sys/fs/pstore` requires root and
was not inspected during the unprivileged check.

### Next diagnostic: freezer and device stages

The helper follows the kernel's
[staged PM debugging procedure](https://www.kernel.org/doc/html/latest/power/basic-pm-debugging.html).
It tests process freezing, then device suspend/resume, without entering platform
sleep. This can still hang if a driver is faulty. Save work in **all** logged-in
sessions and keep the lid open. Preview it without changing anything:

```bash
python3 sleep/test-stages.py
```

When ready to pause the desktop, run from the repository root:

```bash
sudo systemd-inhibit --what=sleep:shutdown --mode=block \
  --why="Staged PM diagnosis" python3 sleep/test-stages.py --run
```

Each stage should return automatically after the kernel test delay (currently
5 seconds), plus driver transition time. The helper saves progress to a private
root-owned `/var/tmp/macbook-t1-pm-test-*` directory and flushes it before each
stage. An unfinished `START` record after forced reboot identifies the stage
that did not return; it cannot identify an individual driver. New kernel output
is captured when a test returns, and may be lost on a hard hang.

The helper restores the original debug flags and `pm_test` on normal or handled
error exit; reboot resets them after an unrecoverable hang. It stops if a stage
fails or a wake event prevents it reaching the test checkpoint. It does not
change sleep mode, PM_TRACE/RTC, boot parameters or installed drivers. Direct
kernel tests bypass systemd sleep hooks, so passing them does not validate the
full desktop suspend path. If both return, investigate the later platform/CPU
stages before claiming deep sleep is fixed.

With the user's approval, the initial stages ran at 21:47:55–21:48:08 IST:

* `freezer`: reached its checkpoint and returned without a kernel PM error.
* `devices`: reached its checkpoint and returned without a kernel PM error; suspend success
  counter advanced from 1 to 2, with all failure counters remaining zero.
* Device resume logged the NVMe, i915 and Touch Bar returning, and subsequent
  Touch Bar/audio/camera/Wi-Fi verification passed its software checks.
  **The user then reported silent audio after the initial tests. Physical device
  acceptance failed despite those software checks.**
* `pm_test=none`, both debug flags `0`, and the original `deep` selection were
  confirmed after cleanup. Logs: `/var/tmp/macbook-t1-pm-test-e8l8g1cy` (root).

These passes narrow the search to later callbacks/platform sleep and differences
in the full desktop suspend path. They do not exonerate all drivers in real S3.
The more intrusive `platform`, `processors`, and `core` tests ran with separate
user approval at 21:50:11–21:52:34 IST. They all returned and the PM failure
counters stayed at zero, but **the later stages were not clean passes**:

* `platform` took about 88 seconds and `processors` about 47 seconds.
* Thunderbolt bridges became inaccessible across D3cold transitions.
* Both Thunderbolt controllers (`05:00.0`, `7b:00.0`) produced warnings in
  `tb_cfg_read`/`tb_cfg_write` during `tb_resume_noirq`.
* Both downstream xHCI controllers (`06:00.0`, `7c:00.0`) timed out, including
  65-second waits, and reported dead host controllers.

This identifies a reproducible Thunderbolt/PCIe/USB power-transition problem,
but does not prove it is the only cause of the original S3 black screen.
The later tests had already finished by the time the user's audio report was
received. No further PM tests were started, and all temporary PM settings were
verified restored. Logs: `/var/tmp/macbook-t1-pm-test-ktdfssf5` (root), with
journal copies in the ignored `logs/sleep-investigation-20261021/` directory.

The helper originally classified results using the checkpoint and PM counters.
It now also rejects kernel warnings, inaccessible devices and resume timeouts,
and explicitly labels a return as requiring physical device checks. A driver's
zero return code is not proof of working hardware. The later-stage option is
retained for future controlled diagnosis, not as a recommendation to repeat it
on this already-degraded boot.

For the audio regression, PipeWire, pipewire-pulse and WirePlumber were restarted
in the active user's session. The user confirmed audio worked again after
refreshing Firefox to reconnect YouTube playback. No audio driver was replaced.
The bundled CS8409 driver's resume calls an effectively empty init function;
the upstream project has an
[open resume-reinitialization proposal](https://github.com/davidjo/snd_hda_macbookpro/pull/220).
That proposal targets a reset GPIO mask, whereas this machine's post-test codec
still has programmed GPIOs, so it is not yet a demonstrated fix for this failure.

At the end of diagnosis, the two downstream xHCI functions no longer appeared
in `lspci`. A normal reboot is needed to return to a clean hardware state before
further suspend experiments. No reboot, actual S3 sleep, persistent power-mode
change or Thunderbolt workaround was performed during this investigation.

## Follow-up after restart: Thunderbolt D3cold isolation

The user restarted and requested continuation. Boot
`e5fa9f2c-1626-46e9-b2df-4b322fe19d3c` restored all four Thunderbolt NHI/xHCI
endpoints with their expected drivers. The NVMe rule persisted and PM debug
settings were at defaults.

At 22:10:48 IST, a single `platform` test temporarily set `d3cold_allowed=0`
on the 16 built-in PCI functions under the two Thunderbolt root ports
(`00:1c.4` and `00:1d.0`). The test returned in about 9 seconds, but bridges
still became inaccessible and both xHCI functions disappeared. **Disabling
D3cold alone is not sufficient.** No persistent Thunderbolt rule was installed.
The helper restored the 14 surviving attributes to `1`; the two missing xHCI
attributes could not be restored because their devices were gone. PM test/debug
flags returned to `none`/`0`/`0`. Log directory:
`/var/tmp/macbook-t1-pm-test-5w9n5r45` (root).

### Detach before the platform test, rediscover after

A [first-hand report for this model](https://gist.github.com/bgausden/c7f8a3737c1e52a260dfcdb1fb2e90b2)
describes the same disappearing controllers and uses pre-suspend removal and
post-resume re-enumeration of the two Thunderbolt branches. Its complete
configuration also uses s2idle and disables PCIe port power management; that
entire configuration has not been applied here. Branch removal was tested
with the same kernel test stage after a fresh reboot restored the hardware:

```bash
sudo systemd-inhibit --what=sleep:shutdown --mode=block \
  --why="Targeted Thunderbolt PM diagnosis" \
  python3 sleep/test-stages.py --run --stage platform --thunderbolt-remove
```

Omit `--run` to preview. This trial checks the model, built-in PCI topology,
driver bindings and absence of storage under either branch before changing
anything. It refuses missing endpoints, attached storage (including USB
storage), or unknown PCIe hardware. It detaches only `03:00.0` and `79:00.0`,
then rescans only their two buses and requires all four NHI/xHCI endpoints to
return with expected drivers. USB/Thunderbolt peripherals on those branches
temporarily disconnect. Internal NVMe, Wi-Fi, T1 and audio are outside them.
The rescan runs on both successful and failed test exits. A hard lock can still
prevent cleanup until reboot.

On boot `ad9661d2-6378-4645-b63f-e0265761d5ac`, the test ran at 22:22:10 IST
and returned at 22:22:17 without the earlier kernel checkpoint faults.
However, **post-test rediscovery failed**. The first branch restored its NHI
and xHCI drivers; the second branch lost both endpoints (`7b:00.0`, `7c:00.0`).
The rescan logged an inactive parent, invalid bridge configuration, and devices
inaccessible after D3cold. Returning from the checkpoint was not an overall pass.

A bounded recovery attempt held both root ports at `power/control=on` and
`d3cold_allowed=0` during one additional targeted rescan. The missing endpoints
did not return. Both root ports' settings were restored to `auto` and `1`.
PM test/debug flags are `none`/`0`/`0`; the sleep selection is still `deep`.
No further power test was attempted on this degraded boot. Root logs are in
`/var/tmp/macbook-t1-pm-test-n9m6o1mp`; journal and state copies are in the ignored
`logs/sleep-investigation-20261021/` directory.

### Next boot trial: disable PCIe port power management

The next diagnostic uses `pcie_port_pm=off`. This disables PCIe port power
management, as documented in the
[kernel parameters reference](https://docs.kernel.org/admin-guide/kernel-parameters.html).
The matching installed kernel source implements it by rejecting bridge D3
support in `pci_bridge_d3_possible()`. This differs from disallowing D3cold
alone, which left D3hot transitions possible in the earlier unsuccessful trial.
The rescan failure makes this a relevant next experiment, not a proven fix.

The separate `99-macbook-t1-pcie-pm-trial.cfg` appends only that parameter to
normal GRUB boot entries. It was initially installed separately; the one-shot
installer now manages it through `manage-resume.py`. The boot parameter changes no
drivers or sleep mode, and can increase power consumption. A restart is needed
to activate it. The drop-in is installed in `/etc/default/grub.d/` and
`update-grub` plus `grub-script-check` succeeded. Comparing all old and new
kernel command lines confirmed that only `pcie_port_pm=off` was added to the
normal entries. The original GRUB configuration and command line are backed up
in `/var/tmp/macbook-t1-pcie-pm-trial-vj7zint8` (root-only). The running boot
does not yet have the parameter. Thirteen diagnostic unit tests passed,
including refusal before any write when this boot parameter is absent or
conflicting, and shell checks verified that existing arguments are preserved.

After restarting, verify `/proc/cmdline`, all four NHI/xHCI
driver bindings, and the NVMe rule before repeating the single `platform`
test with `--thunderbolt-remove`. The helper now refuses removal unless exactly
`pcie_port_pm=off` is active, preventing a repeat of the known failing rescan
configuration. Its storage and topology guards remain in place.

The resume manager now owns this boot setting and removes it together with the
suspend wrapper. Do not remove only the boot setting while retaining the wrapper:
its guard would then refuse sleep after reboot. The NVMe rule is independent.

No automatic reboot or actual sleep is initiated. Real sleep/wake and physical
audio, Wi-Fi and USB acceptance remain outstanding. No Thunderbolt sleep hook
has been installed.

### Results with PCIe port power management disabled

After the next user-initiated restart, boot
`cdc575dc-198f-46aa-9ab5-65465f32d2cf` had `pcie_port_pm=off` active, all four
NHI/xHCI endpoints bound, and the NVMe D3cold rule intact.

* The `platform` checkpoint ran at 22:29:39–22:29:48 IST. The kernel test took
  about eight seconds, and both Thunderbolt branches rediscovered successfully.
  Root log directory: `/var/tmp/macbook-t1-pm-test-65kxg8du`.
* The already-authorized `processors` and `core` checkpoints ran at
  22:30:35–22:30:50 IST, with both branches detached for the two tests. Each
  returned in about seven seconds, and all four endpoint drivers returned.
  Root log directory: `/var/tmp/macbook-t1-pm-test-yzhwogut`.
* Kernel suspend success increased from zero to three with all failure counters
  unchanged at zero. There were no kernel warnings, inaccessible-device errors,
  or host-controller timeouts in the test and rediscovery interval. PCI I/O
  window allocation messages and a Broadcom ARP-table message remain in the
  logs; this is not a claim that every log line is error-free or every peripheral
  has been physically validated. All 16 expected PCI functions were present,
  Wi-Fi remained connected, and the user audio services were active.
* `pm_test=none`, debug flags `0`, and the original `deep` selection were restored.

These results support proceeding to actual sleep; they do not validate it.
`sleep/test-s2idle.py` prepares one explicitly approved real kernel sleep cycle
with an RTC wake approximately 20 seconds after arming. It temporarily selects
`s2idle`, detaches the same guarded Thunderbolt branches, then restores the mode,
debug flags and controllers. It rejects an existing RTC alarm or disabled RTC
wakeup, requires at least ten seconds actually suspended, and checks kernel
faults through the end of rediscovery. It is plan-only without `--run`.
Eighteen unit tests cover result classification, refusal and cleanup paths.

This diagnostic uses `/sys/power/state` directly, so desktop logind notifications,
the normal systemd sleep path, lid close and idle timeout need separate acceptance.
The choice of s2idle avoids the final firmware transition of S3 and follows the
model report cited above; sleep battery drain remains to be measured.

### First real s2idle result and normal-suspend integration

The user explicitly approved one real sleep cycle after saving work. It ran at
22:34:28–22:34:50 IST on the same boot. The RTC was armed for approximately
20 seconds, and the difference between `CLOCK_BOOTTIME` and `CLOCK_MONOTONIC`
measured **18.41 seconds actually suspended**. The kernel recorded s2idle entry
and suspend exit, success increased from three to four, and failure counters
remained zero. All four Thunderbolt NHI/xHCI drivers returned. Root logs:
`/var/tmp/macbook-t1-s2idle-bdut3s5h`; journal/state copies are in the ignored
investigation log directory.

Afterward, Wi-Fi was connected at 5220 MHz, and HTTPS bound to `wlp2s0` returned
HTTP 204 from Ubuntu's connectivity endpoint. The Touch Bar logged resume,
the analog audio sink remained present, and all three user audio services were
active. The user's physical confirmation of automatic wake, screen, keyboard,
Touch Bar and sound is still pending; software enumeration alone is insufficient.
The helper cleared its RTC alarm and restored `deep`, `pm_test=none` and zero
debug flags. This one successful kernel trial does not enable normal lid sleep.

The normal-suspend integration in `suspend-wrapper.py` and the two systemd
configuration snippets is **installed, awaiting normal-path acceptance**. It replaces the
suspend service command with a guarded wrapper around the original
`/usr/lib/systemd/systemd-sleep suspend`, preserving the normal systemd sleep
program and hooks. It validates the model, port-PM boot parameter, NVMe setting,
controller topology and absence of attached storage before detaching anything.
Failure prevents the original sleep program from running. A `finally` context
rescans the branches after return or error. This is deliberately not a
`system-sleep` pre-hook, since a failed pre-hook cannot cancel suspend.

The configuration selects `MemorySleepMode=s2idle` and `SuspendState=mem`.
USB/Thunderbolt peripherals on the branches temporarily disconnect. Attached
storage or unknown PCIe hardware makes the wrapper refuse suspend; safely
disconnect such devices before sleeping. A hard kernel lock or power loss can
still prevent cleanup until reboot. Hibernation paths are not configured by
this integration.

The manager rejects conflicting files and rolls back configuration, GRUB and
live mode if installation or validation fails. Integration tests cover refusal
before upstream sleep, recovery after upstream failure, fresh and repeated
installation, pending restarts, boot-argument preservation, configuration
conflicts, symlink refusal, removal and rollback. The diagnostic tests also cover
RTC and PM setting cleanup. The separate installation and verification commands are:

```bash
sudo systemd-inhibit --what=sleep:shutdown --mode=block \
  --why="Install guarded s2idle support" python3 sleep/manage-resume.py install
python3 sleep/manage-resume.py verify
```

The initial integration installation completed with a backup at
`/var/tmp/macbook-t1-resume-install-3fcc__y9` (root-only). `daemon-reload` and
`systemd-analyze verify systemd-suspend.service` succeeded. All four installed
files match the repository and are root-owned mode `0644`. The effective service
command points to the wrapper, the effective sleep configuration selects s2idle,
and live mode reads `[s2idle] deep`. No restart is needed for these changes.
The NVMe rule and active `pcie_port_pm=off` setting are retained. The later
one-shot integration also manages the GRUB drop-in and was checked with isolated
filesystem fixtures; the complete hardware installer was not rerun for that
code change.

Installation did not initiate another sleep or reboot. Acceptance through normal desktop
suspend, lid close, idle timeout, repeated cycles and a subsequent reboot remains
separate. Battery drain has not been measured. Remove the integration with:

```bash
sudo systemd-inhibit --what=sleep:shutdown --mode=block \
  --why="Remove guarded s2idle support" python3 sleep/manage-resume.py uninstall
```

The current manager removes its systemd files and PCIe boot drop-in, then
regenerates GRUB. Removal leaves the current kernel's mode and boot parameter
until reboot and preserves the independent NVMe rule. Its removal step is below.

## Removal

```bash
sudo ./sleep/manage.sh uninstall
```

Removal deletes only the matching rule and reloads udev. The live setting
stays at `0` until reboot, when the kernel default applies again. No automatic
reboot is performed.
