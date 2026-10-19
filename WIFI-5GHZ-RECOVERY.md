# 5 GHz-only recovery

Protected pre-undo state: `/var/backups/macbook-t1-wifi-original-restore/`.
Git history/uncommitted patch archive: the invoking user's `wifi-baseline-restore/`.
Current installation journal: `/var/lib/macbook-t1-wifi-5ghz/` (0700).
These archives can contain network credentials; keep them private.

For an older installed 5 GHz version, use its recorded installed recovery helper
before rebuilding from stock: `sudo python3 /usr/local/libexec/macbook-t1-wifi-5ghz/deploy.py uninstall`.
The new source uninstaller refuses another deployment version rather than
removing the wrong DKMS package. Version 1.1.0 uses the normal command below.

```bash
sudo ./uninstall-wifi.sh
```

Removal restores the stock wireless module and saved initramfs, removes owned
5 GHz configuration and the created profile, and restores saved-profile
autoconnect flags if still equal to the value written by this project. Deleted
profiles are not recreated. Later owned-file/source edits stop removal for review.
Firmware still referenced by a live driver is retained until that driver is
replaced; subsequent installation cleans only hash-matching retired files.

No live driver unload occurs during ordinary uninstall. Save work and reboot
when appropriate, or use the explicit local rollback while independent Ethernet
is connected:

```bash
sudo python3 wifi/5ghz/deploy.py rollback
```

Live rollback quiesces Wi-Fi, restores the stock driver and leaves networking
recovery to Ethernet. It does not reconnect a 2.4 GHz profile or automatically
reboot. Failure to restore the live driver is reported for an attended reboot.

Fresh installation arms a 45-minute rollback timer. After live verification:

```bash
sudo python3 wifi/5ghz/deploy.py confirm
```

Confirmation cancels that timer. Post-boot verification is read-only:
`journalctl -b -u macbook-t1-wifi-5ghz-verify.service` and the private
`postboot.json`. It checks the installed provider for the **running** kernel
and requires actual 5 GHz association/IP/traffic. Failure is reported; it does
not trigger 2.4 GHz fallback or reboot loops.

For compatible Ubuntu 7.3.0 ABI updates, install the exact matching headers and
source, run DKMS autoinstall and rebuild the initramfs. Confirm the initramfs
contains `brcmfmac-wcc.ko*` as well as the isolated station binary and board file.
Other kernel families require a new source audit. Keep a previously bootable
kernel. Touch Bar/audio/camera recovery is independent of this component.
