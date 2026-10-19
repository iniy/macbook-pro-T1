# Wi-Fi installation and recovery

Target: MacBookPro13,2, BCM43602 `14e4:43ba`, Apple `106b:0157`, revision 02,
Ubuntu 26.10 and audited `7.3.0-*-generic` kernels.

## Install

```bash
sudo ./install-wifi.sh --dma-fix --install-deps --update
sudo ./verify-wifi.sh --online
```

The first command installs the DKMS DMA repair and refreshes this project's
existing Wi-Fi tools. It preserves selected country/profile options. On a fresh
installation `--update` is harmless. Use `--country IN` only while in India.
The suite's default `--wifi` installation remains configuration/diagnostics
only; use the direct command above to select the driver repair explicitly.

Installation does not disconnect Wi-Fi, unload modules, or reboot. The on-disk
module applies at the next normal boot. Module presence alone is not proof of
connectivity; run verification after boot and inspect its separate metrics.
`--online` requires certificate-verified HTTPS and can fail even when local
Wi-Fi or HTTP connectivity works. Never disable certificate checking to make
this test pass.

Check persistence before rebooting:

```bash
dkms status -m macbook-t1-wifi-dma
modinfo -n brcmfmac
modinfo -F vermagic brcmfmac
cat /sys/module/brcmfmac/srcversion
```

`modinfo` describes the selected file on disk; `/sys/module` describes the
currently loaded module. They can differ before reboot. DKMS should report
installed for the target kernel, and module selection should be under
`updates/dkms`. Preserve a working kernel in the boot menu.

## Roll back just the DMA module

```bash
sudo ./uninstall-wifi.sh --dma-only
modinfo -n brcmfmac
```

The selected path must return to the packaged `kernel/drivers/.../brcmfmac`
module. The command removes this project's DKMS entry, runs depmod and updates
affected initramfs images. It does not unload the current module. Save work and
use a normal reboot to switch drivers. The stock driver can reproduce the
original DMA/association failure; keep Ethernet available.

To remove all Wi-Fi-owned configuration as well:

```bash
sudo ./uninstall-wifi.sh
```

NetworkManager profile fields are restored only if unchanged since installation.
Later user edits are preserved and require review. Shared firmware packages and
all other hardware components remain installed. Source edits also stop DKMS
removal rather than silently deleting them. Removal retains archived state under
`/var/lib/macbook-t1-wifi-dma-removed-*` and
`/var/lib/macbook-t1-wifi-removed-*`.

## Failed installation or future kernel upgrade

Private state is under `/var/lib/macbook-t1-wifi-dma` (mode 0700), including
the original initramfs and stock-module digest. DKMS logs are in
`/var/lib/dkms/macbook-t1-wifi-dma/1.0.0/`. An installation failure attempts
DKMS rollback; if that also fails, the error explicitly requests attention.
Do not reboot into an unverified image. Review the local logs and run the
project's uninstaller to finish recovery.

For a new supported kernel, install its exact headers and matching
`linux-source-7.3.0` package before DKMS autoinstall. The bundled source covers
only Ubuntu source version `7.3.0-9.9`; another version is not substituted.
Check DKMS and `modinfo -k NEW_KERNEL -n brcmfmac` before selecting that kernel.
An unsupported kernel family requires a new source/API audit. If it does not
build, use the retained working kernel; do not force-load an old `.ko`.

## Avoid the live P2P teardown crash

Do not run `nmcli device set ... managed no` immediately followed by
`modprobe -r brcmfmac_wcc brcmfmac`. That sequence caused two automatic
restarts in this investigation. NetworkManager and supplicant teardown is
asynchronous. There is no automatic reload timer in this installation.

Prefer on-disk rollback and a normal reboot with saved work. An expert live
recovery requires independent access, a route that does not use Wi-Fi, and
confirmation that all affected supplicant and P2P interfaces have completely
disappeared before any unload. If quiescence cannot be proved, stop the unload.
Do not reset T1, USB, audio, camera, NVMe or ACPI to recover Wi-Fi.

The private investigation backups additionally contain kernel logs, DMA traces,
original autoconnect choices, configuration archives and benchmark details.
`/var/crash` contains the two kernel dumps. These can expose secrets or memory
contents; do not publish them. The repository reports contain selected metrics
only. Only the user-selected SSID is permitted to autoconnect in the final session policy;
the other original profile choices are retained privately for an intentional
future reversal of that policy.
