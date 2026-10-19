# Controlled 2.4 GHz measurements — 2026-10-19

The sustained run was deliberately interrupted when the owner replaced this
mission with the 5 GHz objective. **No 30-minute pass is claimed.** Its local
monitor log was retained and its namespace, route, ARP settings and timer were
cleaned up before beginning the new work. Bluetooth trials were not executed.

**No RF reception improvement established.** A PHY rate is not throughput.
All rows below use the built-in BCM43602, channel 5 / 2432 MHz, 40 MHz AP width,
the existing DMA-corrected driver and original Ubuntu firmware. The active
saved profile was already 2.4 GHz-only before this session.

## Method

Each completed short series samples the association/RSSI/rates approximately
every two seconds for 125 seconds (64 samples), with one gateway ping per
second. Idle RTT uses the first 20 replies before traffic starts. Loaded RTT
includes iperf traffic. Every series runs two ten-second TCP uploads and two
downloads; direction-specific values below are medians of those two transfers.
No laptop/AP movement was requested during the series; physical position was
not independently instrumented. A quantitative reference-device reading was
not accessible.

The server runs in a separate Linux network namespace on an Ethernet macvlan
with a temporary nonconflicting private /32 address and explicit Wi-Fi host
route. Packets traverse Wi-Fi → AP/LAN → Ethernet, rather than local loopback.
Both client source address and interface are bound, and real Wi-Fi byte-count
deltas are checked against transferred bytes. Scoped ARP settings prevent
Ethernet from replying for the Wi-Fi address. The temporary namespace, route
and ARP controls are restored after testing; the machine's Ethernet default
route remains available throughout.

The first endpoint preflight stopped because `arping` was absent; it restored
its temporary state without changing radio power. Ubuntu `iputils-arping` was
installed. A later benchmark attempt hit a blocked/overdue `ping` subprocess;
no incomplete row is treated as a completed measurement. The sampler now
spools ping output to an anonymous temporary file and supplies a wall-clock
deadline. Its timed recovery and finally-cleanup restored the original state.

## Experiment table

| Experiment | Configuration | RSSI median [range], dBm | Median TX/RX PHY, Mbps | Actual down/up, Mbps | Gateway loss | Idle RTT median | Decision |
|---|---|---|---|---|---|---|---|
| A1 baseline | Power save on | −85 [−88, −83] | 81 / 13 | 21.60 / 7.34 | 2.4% | 19.70 ms | Reference |
| B1 | Power save off only | −86 [−90, −80] | 162 / 99 | 21.91 / 12.94 | 0% | 12.64 ms | Repeat required; RF not improved |
| A2 | Power save on; roaming occurred | −87 [−90, −85] | 108 / 54 | 22.49 / 2.99 | 5.38% | 18.80 ms | Confounded by roaming/DHCP change |
| B2 | Power save off; roaming occurred | −88 [−96, −80] | 81 / 27 | Unavailable | 3.10% | 12.25 ms | Confounded; test route/source changed |
| A3 | Nearer AP pinned, power save on | −86 [−88, −84] | 135 / 30 | 16.25 / 3.72 | 1.57% | 7.41 ms | One AP retained; candidate for sustained test |
| B3 | Same pinned AP, power save off | −85 [−88, −81] | 162 / 60 | 20.03 / 10.15 | 3.85% | 13.70 ms | Reverted: packet loss worsened; RF change negligible |

A1 RSSI standard deviation: 1.672 dB; B1: 1.707 dB. All 64 samples in each
completed series remained associated; no new driver timeouts or DMA faults.
A1 loaded RTT min/mean/max: 3.491 / 110.456 / 1439.316 ms; B1:
3.201 / 97.020 / 751.835 ms. TX-failed counter deltas were 118 and 193,
respectively. Firmware does not expose `tx retries` through this station API;
missing retry counts are not zero. B1 uploads ranged from 2.17 to 23.70 Mbps,
so the first pair alone cannot establish a repeatable throughput improvement.

A2 and B2 each visited two BSSIDs on the same SSID/channel. NetworkManager logs
confirm DHCP restarts and changed IPv4 addresses, invalidating the manually
established test source/return route. Their aggregate station counters span
different peers and are not comparable. B2's failed transfers are therefore not
reported as zero throughput or as proof of a power-saving defect. The sampler
now explicitly flags source changes and suppresses cross-peer counter deltas.
The endpoint also clears its own old neighbor entry and announces its newly
created virtual link, avoiding stale ARP state between experiments.

A3/B3 used a temporary, backed-up BSSID pin to the stronger observed AP. Both
retained one AP for all 64 samples. The pin constrains association, not receiver
gain. A3 RSSI standard deviation was 0.879 dB; B3 was 1.585 dB. Loaded RTT
min/mean/max was 3.420/145.970/2379.260 ms (A3) and
3.440/107.226/1038.283 ms (B3). Neither had a new DMA/firmware fault.
Power saving off increased throughput in this pair but worsened packet loss
and did not repeat the earlier idle-latency improvement. The original default
power-saving policy was retained.

After installation, a real NetworkManager reconnect verified `bg`, the selected
AP, unchanged power saving on, working Wi-Fi DNS/HTTPS and a zero-loss three-ping
check. RSSI was −88 dBm with TX/RX 27/1 Mbps at that instant. India's ordinary
regulatory request resulted in global `98`/PHY `99`, 13 enabled 2.4 GHz channels,
and no 5 GHz band. This short verification is not a sustained pass.

The first sustained-test preflight found Ethernet's DHCP routes missing even
though its address/device remained present. Reconnecting that existing Ethernet
profile restored its route and device-bound HTTPS without editing the profile.
That test-path issue is separate from RF reception; no incomplete preflight is
counted as a stability run.

## Scope of historical data

The previous investigation measured approximately −81 dBm at a user-reported
1–2 metres and roughly 5.45/5.21 Mbps in its final short iperf run. Those are
different sessions/conditions, not interchangeable with this session's baseline.
The present instantaneous starting RSSI was −87 dBm; use series medians above
for comparisons. The previous flawed 30-minute test is not counted as a pass.

5 GHz throughput is intentionally not tested. This firmware exposes no 5 GHz
channels, independently of the NetworkManager `bg` association restriction.
