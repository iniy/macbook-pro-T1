# Actual 5 GHz measurements — 2026-10-19

Reference performance of 584–651 Mbps is not attributed to this machine.
The original 2.4 GHz setup measured approximately −85 to −88 dBm; its first
controlled median LAN result was 21.60 Mbps down / 7.34 Mbps up with 2.4% gateway
loss. Different sessions, RF conditions and bands are not an isolated sensitivity
comparison.

## Completed trials

| Trial | Mode | RSSI | Actual down/up Mbps | Gateway loss | Observation |
|---|---|---|---|---|---|
| Reference NVRAM, ordinary country handling | 5 GHz, channel 48 | −57 to −61 dBm | Not measured in this initialization trial | 0% in seven 3-ping samples | Wi-Fi DNS/HTTPS worked across several 65-second intervals; firmware/host country hints changed |
| G1, India table, power save on | 5 GHz, 40 MHz | Median −69 dBm | 54.42 / 23.27 | 0% | 64/64 associated samples, idle RTT median 2.925 ms |
| G2, power save off only | 5 GHz, 40 MHz | Median −66 dBm | 103.38 / 15.46 | 0% | 64/64 associated samples, idle RTT median 2.775 ms |
| G3, return to power save on | 5 GHz, 40 MHz | Median −65 dBm | 144.53 / 39.32 | 0% | 64/64 associated samples, idle RTT median 2.960 ms |
| Legacy-table prototype | 5 GHz, **80 MHz**, channel 48 | −56 dBm at verification | Not yet measured in this short trial | 0% in 3 pings | TX/RX last-packet rates 175.5/526.5 Mbps; Wi-Fi DNS/HTTPS worked |
| Installed DKMS activation | 5 GHz, **80 MHz**, channel 48 | −58 dBm at verification | Separate throughput test follows | 0% in 3 pings | TX/RX last-packet rates 234/585 Mbps; loaded/installed module match |
| Installed driver, automatically selected AP | 5 GHz, 80 MHz, power save on | Median −59.5 dBm | **316.55 / 84.68** | **0%** | 64/64 associated samples; idle RTT median **2.845 ms** |
| Alternate observed AP on the same network | 5 GHz, 80 MHz, power save on | Median −61 dBm | 289.43 / 43.23 | 0% | 63/63 associated samples; idle RTT median 5.305 ms; temporary pin restored |

G1–G3 used two ten-second uploads and two downloads per 125-second series.
Each had one AP, one unchanged IPv4 source, and no new runtime DMA or firmware
errors. The best individual G3 download was **172.68 Mbps**. RSSI/time changed
across the trials, and returning to power saving on outperformed the off trial:
there is no established power-saving-off improvement to retain.

Throughput traverses the built-in Wi-Fi, AP/LAN, and a wired macvlan server in a
separate network namespace on this machine. Source/interface binding and Wi-Fi
byte-counter deltas reject accidental loopback/Ethernet-only measurements.
Ethernet reports 1000 Mbps. These are LAN tests, not ISP speed estimates.

The first 80 MHz trial rolled back because the verifier expected the firmware
abbreviation IN. The saved snapshot shows it was already connected at 80 MHz
with working traffic: firmware reports GB/3, while the kernel reports IN and
only channels 36–48 remain enabled. Verification and duplicate-country handling
were corrected based on this observed behavior.

## Final acceptance status

The owner confirmed that Wi-Fi was working properly and requested an end to
experiments. The working installed 5 GHz configuration was retained and its
temporary deployment rollback timer was cancelled after successful live
verification. **30-minute, reboot and suspend/resume tests were not completed**;
no pass is claimed for them. First-boot verification/recovery remains configured.

The selected-AP 80 MHz trial measured downloads of 303.66 and 329.44 Mbps,
uploads of 83.07 and 86.29 Mbps, RSSI range −68 to −54 dBm, and no TX-failed
counter increase. RX PHY peaked at 650 Mbps; TX PHY peaked at 325 Mbps in that
series. These are measured rates, not the reference project's 866 Mbps claim.
The AP advertises two VHT spatial streams and short GI at 80 MHz; the client
advertises three, so the AP limits the possible spatial-stream count here.
The alternative AP did not improve throughput, and its BSSID pin was removed.

An earlier 2.4 GHz sustained test was interrupted on the owner's change of
mission and is not a 5 GHz pass.
Teardown-only `delete_flowring` timeouts are retained in boot logs and separated
from new runtime errors; no P2P oops occurred in the quiesced 5 GHz trials.
