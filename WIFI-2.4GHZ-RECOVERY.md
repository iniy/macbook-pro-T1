# 2.4 GHz recovery

## Preserved boot and network state

The original kernel `7.3.0-9-generic`, initramfs, Wi-Fi modules, firmware and
configuration were archived root-only in:

`/var/backups/macbook-t1-wifi-2g/20261019-164539/original-state.tar`

Checksums are alongside it. The running kernel was not replaced. Earlier
`/var/lib/macbook-t1-wifi*` transactions and investigation backups remain intact.
These archives contain network secrets; do not upload them.

## Runtime experiments

`wifi/experiment.sh` changes only live power saving and always reverts. It arms
an independent `macbook-t1-wifi-trial-*.timer` before the write. If its process
is interrupted, the timer executes `iw ... set power_save ORIGINAL`; reboot
also restores the unchanged saved-profile policy. State records the original
value under `/var/lib/macbook-t1-wifi-experiments/`.

Do not cancel an armed timer until restoration is verified. A live module unload
is unnecessary. During this physical investigation, a separate local timer also
removed the temporary iperf namespace/route and restored scoped ARP test settings.

## Saved-profile changes

Inspect `/var/lib/macbook-t1-wifi/profile.json` as root for the exact changed
UUID/fields and original values. To restore **only settings/tools** while keeping
the existing association-critical DMA module, use the scoped restoration below:

```bash
sudo ./uninstall-wifi.sh --settings-only
```

It restores only fields still equal to the installer's writes, preserving later
user edits. A profile restoration takes effect on next reconnect; it does not
globally disable Wi-Fi or reset other hardware. Independent Ethernet is the
preferred recovery path before reconnecting.

To remove just the measured AP pin while retaining the other installed settings:

```bash
sudo ./install-wifi.sh --update --bssid ''
```

The change takes effect at the next reconnect. A pinned profile intentionally
will not roam to another AP with the same SSID; clear it when moving to a place
where that AP is no longer reachable. No BSSID is embedded in the project.

The generic `sudo ./uninstall-wifi.sh` also removes the DMA repair from disk.
That can reintroduce the previously traced association failure after reboot.
Use it only when deliberately returning to the pre-DMA driver. See the older
[DMA recovery instructions](WIFI-RECOVERY.md).

## Country policy and module indexes

The selected country is requested through the normal kernel regulatory API.
The owned dispatcher is
`/etc/NetworkManager/dispatcher.d/90-macbook-t1-wifi-country`; settings-only
removal removes it and the owned country service. It does not patch regulatory
enforcement. Global `98`/PHY `99` can represent intersections rather than a
literal country code; inspect `iw reg get` and allowed channels.

Public module indexes can be safely regenerated without unloading any driver:

```bash
sudo sh -c 'umask 022; depmod -a "$(uname -r)"'
modinfo brcmfmac
```

## Post-boot verification

The existing read-only Wi-Fi verifier timer remains enabled. After an attended
reboot, `sudo ./verify-wifi.sh --online --radio` checks the association, device-bound
traffic and current radio state. Inspect `journalctl -b -u macbook-t1-wifi-verify.service`.
Reboot and suspend must be measured separately; saved settings and a timer alone
are not proof of either. Live brcmfmac/WCC unload previously caused P2P teardown
oopses: use normal reboot for a staged module change, not repeated unloads.
