# Measurements — fresh 5 GHz-only rebuild

These results describe the rebuild after restoring the original stock Wi-Fi
baseline. Figures from the retired 2.4 GHz and foreign-country-table experiments
are not acceptance results for this implementation.

## Completed live checks

* Interface associated on **5240 MHz / channel 48**.
* Firmware GET reports **80 MHz** width and **IN/0** country/table.
* Signal observed **−55 to −58 dBm** during activation/reconnect checks.
* Gateway ping: **0% loss**, average **3.177 ms** in the recorded post-reconnect
  three-packet check. This is a short sample, not long-term stability evidence.
* Device-bound DNS and HTTPS pass; Ethernet success is not counted as Wi-Fi.
* A deliberate disconnect/reconnect to the 5 GHz-only profile passes.
* Loaded and installed new module srcversions match.
* All applicable old profiles have autoconnect disabled; only the project's
  band-`a` Wi-Fi profile is automatic. Other interface-bound profiles are excluded.

The host reports country intersection `98` because the AP advertises US and the
owner confirmed physical India. Firmware readback is IN/0. Channel width and
link rates are measured separately from actual traffic throughput.

## Extended measurement

A 30-minute sample series was started with one gateway ping per second and
link measurements every five seconds, plus one 10-second upload and download
to a DHCP-addressed wired macvlan endpoint in a separate network namespace.
The endpoint is not an address local to the Wi-Fi client's namespace. Explicit
interface/source binding and interface byte-counter deltas validate that traffic
crosses Wi-Fi and the AP/LAN rather than local loopback or Ethernet alone.

The completed summary will be recorded here after the measurement finishes.
Raw results and boot-scoped AP tokens are kept in the root-only measurement
directory under `/var/backups/macbook-t1-wifi-original-restore/`.

Reboot and suspend/resume are not claimed as tested. The corrected initramfs
has been inspected for both the vendor helper and selected firmware files.
