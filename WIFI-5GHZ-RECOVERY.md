# 5 GHz recovery

The original running kernel and other hardware modules are retained. Before
experiments, the full protected baseline was archived at:

`/var/backups/macbook-t1-wifi-5ghz/20261019-173701/`

The persistent installer additionally saves the previously selected brcmfmac,
its checksum, the previous initramfs, NetworkManager/netplan/modprobe configuration
and original profile metadata under `/var/lib/macbook-t1-wifi-5ghz/` (0700).
Archives may contain network secrets. Do not upload them.

## Automatic recovery

* Installation arms `macbook-t1-wifi-5ghz-rollback.timer` for 45 minutes.
  It operates locally without the AI session or network. Runtime rollback
  restores disk state, safely quiesces Wi-Fi, and reconnects the original profile.
  If live restoration fails after disk recovery succeeds, it requests one recovery
  reboot.
* First-boot verification runs approximately two minutes after startup. A failed
  unconfirmed boot restores the prior module/initramfs/profile and requests one
  recovery reboot. The recovery marker and new verification unit are removed
  before reboot, preventing a loop.
* The `confirm` action verifies the loaded installed module and 5 GHz traffic,
  then cancels the runtime timer. First-boot recovery remains armed until an
  actual successful post-install boot is observed.

```bash
sudo python3 wifi/5ghz/deploy.py confirm
```

Confirmation is distinct from a 30-minute stability pass. Results and recovery
state remain local in the private journal.

## Manual disk-only removal

```bash
sudo ./wifi/uninstall-5ghz.sh
```

This restores the previous driver/initramfs and removes the owned 5 GHz profile,
module options and units. It does not unload a live driver. Reboot applies the
driver recovery. The earlier DMA package is re-registered where it was the
original provider; the exact original module bytes are also preserved for
offline restoration. No Touch Bar/audio/camera module is reinstalled.

Firmware in use by a still-running driver is retained as a private recovery
artifact until reboot. A subsequent installation only cleans such retired
firmware when its hashes match the recorded owned files and it is no longer
the live firmware path. Later edits cause recovery to stop for review rather
than overwrite user work.

For immediate local rollback, including Wi-Fi-only reconnection:

```bash
sudo python3 wifi/5ghz/deploy.py rollback
```

The original 2.4 GHz connection profile remains in NetworkManager. Whether it
can associate while the 5 GHz reference NVRAM is active is a separate tested
limitation; restoring the previous driver/firmware path restores the previous
2.4 GHz behavior. Do not remove the older DMA component while the combined
5 GHz provider is installed.

## Verification after recovery or reboot

Inspect `journalctl -b -u macbook-t1-wifi-5ghz-verify.service`, the private
`postboot.json`, `dkms status`, and the loaded/installed `brcmfmac` srcversions.
The `boot-validated` marker is created only on a different boot ID from
installation. A configured timer alone is not evidence of a completed reboot.
