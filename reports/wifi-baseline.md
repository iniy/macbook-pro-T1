# Wi-Fi baseline — 2026-10-19

Captured before Wi-Fi-specific changes; identifiers intentionally omitted.

* Model: MacBookPro13,2; Ubuntu 26.10; kernel 7.3.0-9-generic.
* BCM43602 revision 02, PCI 14e4:43ba, Apple subsystem 106b:0157.
* Stock, signed, in-tree brcmfmac with brcmfmac_wcc; no competing wl/b43
  installation or Wi-Fi DKMS package found.
* Firmware loads: 7.35.177.61 / 01-ea662a8c. Ubuntu linux-firmware
  20260915.git1522c78a.1ubuntu; package verification passed.
* Generic `.bin.zst` and `.ap.bin.zst` present. No BCM43602 `.txt`,
  `.clm_blob`, `.txcap_blob` or Apple-qualified variant found.
* Interface exists and is not rfkill-blocked. 2.4 GHz scanning works;
  only band 1 is exposed, initially channels 1–11. No 5 GHz band.
* Original saved WPA-PSK network has autoconnect enabled and default PMF.
  Repeated association attempts fail with status 16, then NM asks for secrets.
  A stored credential was later confirmed present without printing it.
* NM 1.58.1; wpa_supplicant 2.11. Scan MAC randomization was already disabled
  in the shared NM configuration. Default Wi-Fi power saving is 3 (enabled);
  the saved profile uses default 0. No local brcmfmac options were found.
* Global regulatory domain 00, driver custom domain 99. The user subsequently
  confirmed physical location in India. wireless-regdb 2026.05.30 installed.
* Firmware reports its generic fallback hardware address; the value is omitted.
  This supports investigating missing board configuration, but is not by itself
  proof that a particular community calibration file is valid.
* No brcmfmac timeout/crash was in the initial boot log. Later testing exposed
  command timeouts/commonring exhaustion; see the implementation report.
* Independent USB Gigabit Ethernet provides the internet/default route.
  No SSH environment variables were present. Ethernet was retained throughout.
* Touch Bar and CS8409 DKMS packages 1.0.0 installed for this kernel;
  T1 guard/service/bindings, audio software-mixer checks and UVC enumeration pass.

Git baseline: `10f013d2759a945cde6a02c20e895d7f79b590ed`, clean working tree.
Branch created: `feature/bcm43602-wifi`.
Private configuration/module/log/firmware backups exist outside Git under
`/var/backups/macbook-t1-wifi-baseline` and the invoking user's `wifi-private`.
The archives contain sensitive data and are not publishable.
