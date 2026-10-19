# Physical BCM43602 measurements — 19 October 2026

These are the earlier DMA-investigation measurements. See the subsequent
[controlled 2.4 GHz comparisons](WIFI-2.4GHZ-BENCHMARKS.md) for current results;
different sessions/positions must not be combined as one baseline.

**Reception remains unresolved.** The RX DMA repair restored usable 2.4 GHz
traffic, but does not provide normal radio sensitivity. See
[root-cause evidence](WIFI-ROOT-CAUSE-REPORT.md) and
[recovery](WIFI-RECOVERY.md). All association/traffic tests used the user's
selected network. No network credentials, identities or raw packet captures
are included here.

| Condition | Actual observation | Interpretation |
|---|---|---|
| Stock module | PCI-device DMA read faults, association/ioctl timeouts | Traced RX mapping direction defect |
| Corrected DMA module | Authentication, DHCP, real traffic; no new observed driver faults | DMA repair effective on this machine |
| Initial local transfer | 5.24 Mbps down / 1.13 Mbps up, about -80 dBm | Short transfer, before path correction; not a stability result |
| Mac 1–2 m from router | Approximately -81 to -83 dBm | Reception still poor |
| Wi-Fi power saving off | RSSI remained weak | Reverted; throughput during this trial was confounded by routing |
| Corrected bound-test route/ARP | 5.45 Mbps down / 5.21 Mbps up, -82 dBm; DNS and HTTPS passed; gateway ping 0% loss | Working 2.4 GHz, still poor reception |
| USB Ethernet present | Mean -81.3 dBm, 134 samples | Sample interval approximately 2 seconds |
| USB Ethernet absent | Mean -80.8 dBm, 243 samples | No material RSSI improvement; no return-to-present period captured |
| Firmware per-chain RSSI | Example [-88, -80, -85] dBm | All three chains weak despite enabled mask 7 |
| Firmware noise | -92 dBm | Firmware-reported value, not calibrated RF measurement |
| 5 GHz | No registered 5 GHz band | Not tested for traffic; later deferred at user's request |

Throughput used two 10-second TCP iperf3 directions. The server was in a
separate network namespace on an Ethernet macvlan; the client bound to the
Wi-Fi device, so traffic traversed the wireless link. This was not a localhost
loopback benchmark. The temporary namespace and server were removed afterward.

The first 30-minute sampler collected 52 samples over 1804.8 seconds. Every
sample remained associated and no driver errors were counted, but 39 samples
failed its online criterion. **Sustained stability did not pass.** Position,
power-saving and network-path conditions changed during this session, and
capture evidence subsequently established asymmetric Ethernet return traffic.
It is not valid to attribute all failures to RF, or to call this a controlled
30-minute pass. A new lengthy run was deferred while prioritizing the actual
reception fault.

The user reports good reception in macOS on this same Mac. No numeric macOS
RSSI or simultaneous reference-device comparison was collected. A cold boot
and suspend/resume of the packaged Wi-Fi module remain unverified. Touch Bar
driver checks and audio device/mixer checks passed; the camera decoded 30
frames at both 640x480 and 1280x720. No new audible speaker/headphone or physical
Touch Bar keypress test was claimed for this Wi-Fi session.
