# BCM43602 — 5 GHz only

Supported target: MacBookPro13,2, Apple BCM43602 `14e4:43ba`, subsystem
`106b:0157`, revision 02; Ubuntu 26.10 / 7.3.0 generic with matching source.

```bash
sudo ./install-wifi.sh --profile SAVED_WIFI_UUID --activate
./verify-wifi.sh --online
sudo ./uninstall-wifi.sh
```

`--activate` requires working independent Ethernet and quiesces the Wi-Fi
supplicant/P2P interface before reloading only brcmfmac. Without it, installation
stages the driver and firmware for the next boot. Reinstallation checks the
existing transaction and preserves a matching completed installation.
Use `sudo ./install-wifi.sh --refresh-tools` to update owned diagnostics/recovery
helpers without reloading the radio. A driver/firmware version change requires
removal and a fresh install from the restored stock baseline.

The created profile is locked to band `a` (5 GHz). Previous applicable Wi-Fi
profiles are retained, with their autoconnect flags backed up and disabled.
There is no automatic 2.4 GHz fallback. Ethernet and profiles explicitly bound
to other wireless interfaces are excluded. A profile you create manually later
must also be set to 5 GHz if it should follow this policy.

The firmware can still report/scan its hardware's 2.4 GHz capability; that is
not a supported connection path in this component. The former 2.4 GHz tuning
installer, trial tools and separate DMA installer are retired. Their history
was archived before the original stock baseline was restored.

The fresh driver build contains only the exact-device RX DMA direction repair
and board-file load diagnostics. Native cfg80211/firmware regulatory handling
is retained. The confirmed physical country is India; the country service and
adapter-scoped NM dispatcher issue an ordinary `iw reg set IN` request. A host
domain of `98` denotes the intersection with AP hints; firmware readback must
be inspected separately. No foreign-country table patch or transmit-power
override is installed.

The unchanged Ubuntu firmware and checksum-pinned model-matched community board
file are installed in an isolated firmware directory. The board file is not a
unit-specific factory calibration; its original RF values are preserved. No
firmware or calibration data is distributed in Git. See the provenance and
compatibility evidence in [the implementation report](../WIFI-5GHZ-IMPLEMENTATION.md).

Optional measured acceptance:

```bash
sudo ./wifi/benchmark.sh --seconds 1800 --band 5 --output /var/tmp/wifi-5ghz.json
# Add --iperf-server LAN_SERVER_IPV4 only for a suitable local endpoint.
```

The verifier's default accepted band and benchmark default are 5 GHz. Metrics
are allowlisted; IPs, SSIDs, MACs and passwords are not printed. Keep the full
benchmark's boot-scoped AP tokens and all deployment backups private.

[Measurements](../WIFI-5GHZ-BENCHMARKS.md) ·
[Recovery](../WIFI-5GHZ-RECOVERY.md)
