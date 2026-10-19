# 2.4 GHz implementation — 2026-10-19

Branch: `feature/bcm43602-2g-reception`, based on local commit
`117774d16b23162907b8500d79698ef11ca0aa0a`.

Validated tooling implementation: `729398141cc8a56c28d9820b6a68547f63111170`.
The owner subsequently redirected the mission to 5 GHz. The 2.4 GHz sustained
test was stopped and cleaned up; RF improvement and 30-minute acceptance remain
unverified. This checkpoint preserves the completed work and measurements.

## Scope

This extends the existing optional Wi-Fi component. The prior exact-source DMA
repair remains the association baseline; weak reception is not claimed fixed.
Touch Bar, CS8409 audio, camera, T1/EFI firmware and amplifier settings are outside
these changes. No RF calibration values or proprietary firmware are distributed.

## Source changes

* `wifi/manage.py`: `--2ghz-only`, optional `--bssid`, active-profile discovery, canonical NM
  power-save enum parsing, country dispatcher deployment, and settings-only
  rollback that retains the DMA module. Only explicitly selected profile fields
  are modified; original fields and configuration are privately archived.
* `wifi/country.py`: accepts a dispatcher interface and ignores other adapters;
  requests the explicitly selected country through ordinary `iw reg set`.
* `wifi/driver.py`: accepts DKMS's installed-with-originals annotation and runs
  system module-index/package commands under umask 022. Private transaction
  files retain restrictive permissions. No kernel-source/DMA quirk change.
* `wifi/benchmark.py`, `wifi/benchmark.sh`: repeated real device-bound LAN
  transfers, RSSI distributions, link-rate distributions, packet loss, latency,
  counter deltas and new driver errors. Rejects same-namespace iperf endpoints.
* `wifi/experiment.py`, `wifi/experiment.sh`: one-variable runtime power-saving
  trial with independent systemd watchdog, verified restore and private results.
  The saved profile is not modified during a trial.
* `wifi/diagnose.sh`: independent entry point for existing allowlisted diagnostics.
* Focused Wi-Fi tests, documentation and deterministic source packaging.

## Installation and rollback interface

```bash
# Physically in India, with an already-connected trusted Wi-Fi profile:
sudo ./install-wifi.sh --update --country IN --2ghz-only
# Only after a measured beneficial trial:
sudo ./install-wifi.sh --update --powersave off
sudo ./uninstall-wifi.sh --settings-only
```

Installation validates model, PCI/subsystem, Ubuntu release, kernel/module
ownership, firmware presence and existing modifications before deploying owned
  files. It neither unloads the live driver nor restarts NetworkManager. Saved
profile changes apply on reconnect. Existing DMA DKMS registration handles
matching audited kernel updates; unsupported ABI/source/signature conditions
retain their explicit failure behavior. See [component instructions](wifi/README.md).

## Runtime file scope

Owned country dispatcher:
`/etc/NetworkManager/dispatcher.d/90-macbook-t1-wifi-country`.
Existing helper directory: `/usr/local/libexec/macbook-t1-wifi/`.
Existing country/verification units: `/etc/systemd/system/macbook-t1-wifi-*`.
Private configuration journal: `/var/lib/macbook-t1-wifi/`.
Public module dependency indexes: `/usr/lib/modules/7.3.0-9-generic/modules.*`.
Only selected Wi-Fi fields are journaled; unrelated profiles remain intact.

## Upstream and provenance

No newly downloaded upstream code is incorporated into the kernel module.
The inherited driver uses Ubuntu **7.3.0-9.9**, with exact bundled-source hashes
in `wifi/dkms/SOURCE-SHA256.json` and the narrow
`wifi/patches/0001-apple-43602-rx-dma-direction.patch`.
External repository revisions and rejected calibration/regulatory recipes are
documented in [SOURCES.md](SOURCES.md) and the root-cause report.

## Acceptance

Installation, traffic, RF reception, sustained service and boot/resume are
separate milestones. See [the measured results](WIFI-2.4GHZ-BENCHMARKS.md).
Successful tooling tests do not establish the missing Apple board calibration
or normal receiver performance.

## Actual deployment checks

The update and subsequent idempotent install completed on the physical system.
An initial idempotency check found NetworkManager's terse output escaping the
BSSID colons; immediate recovery restored the prior profile. `profile_value()`
now explicitly requests unescaped values. Settings-only uninstall/reinstall and
the repeated no-op install then passed, retaining the loaded DMA driver. This
was an installer parsing issue, not an RF fault.

The active profile retains `bg` and its original default power policy; the
measured nearer-AP pin is privately journaled. A real profile reconnect passed
Wi-Fi-bound DNS/HTTPS/ping verification. The root-only recovery timers were
armed before configuration/reconnection and disarmed after verified completion.
No live module unload or firmware/calibration replacement occurred.

The country dispatcher now yields a normal regulatory intersection (`98`/`99`)
after association, with 13 enabled 2.4 GHz channels. `modinfo` is usable without
root following dependency-index regeneration under umask 022.

## Other hardware and persistence

Before/after checks passed for Touch Bar HID bindings/control attributes/boot
service, CS8409 DKMS/loaded ABI/software-mixer policy and PipeWire speaker/mic
nodes. Camera capture decoded 30 frames each at 640×480 and 1280×720 before and
after deployment; no images were retained. A short microphone stream captured
129,802 frames in memory and was discarded. This proves streaming, not spoken
intelligibility. The headphone port exists but no plugged-in headphone output
was available for an audible test. Physical Touch Bar key presses and listening
were not repeated.

Keyboard/trackpad and Bluetooth remain enumerated. Hash comparisons confirmed
that brcmfmac, Touch Bar, audio, camera, Apple SPI and Bluetooth module binaries,
their loaded srcversions, and all versioned `/boot` files were unchanged.

The earlier DMA module was already active after this session's starting boot,
and its installed/loaded srcversions match. The new profile/dispatcher settings
were verified through an actual reconnect, **not a new reboot or suspend/resume**.
The existing read-only post-boot verifier remains enabled. No automatic reboot
was initiated for these configuration-only changes.

## Validation

31 Wi-Fi unit/regression tests passed, including the actual hardware-scoped DMA
C helper, source integrity, DKMS status parsing, public-index umask, settings-only
removal isolation, NM enum normalization and per-field rollback. ShellCheck,
Python compilation and `git diff --check` passed. These tests supplement the
physical comparisons; they do not substitute for RF or cold-boot acceptance.
