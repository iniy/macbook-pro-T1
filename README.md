# MacBookPro13,2 Ubuntu support

One-shot setup for the late-2016 MacBook Pro 13,2 on Ubuntu 26.10:

* Apple T1 Touch Bar and keyboard integration
* CS8409 internal speakers, headphones and microphone
* FaceTime HD camera through Ubuntu `uvcvideo`
* Broadcom BCM43602 5 GHz-only Wi-Fi
* Guarded s2idle suspend with NVMe and PCIe power workarounds
* GNOME Bounce Keys preference

Test target: Ubuntu 26.10, kernel `7.3.0-9-generic`, matching Ubuntu source and
headers `7.3.0-9.9`. Other releases, kernels and Mac models are not claimed.

Touch ID is under development on `codex/touchid-integration`. The default
installer reports its prerequisites and acceptance status. It does **not** claim
Touch ID is working or enable it by default before physical/security validation.
See [implementation](TOUCHID-IMPLEMENTATION.md), [test evidence](TOUCHID-TEST-RESULTS.md)
and [recovery](TOUCHID-RECOVERY.md). The attended `--touchid-trial` option is a
development-only, one-boot trial from a verified private build. It will not be
required for a future validated default installation.

## One-shot installation

From a local checkout:

```bash
git clone https://github.com/iniy/macbook-pro-T1.git
cd macbook-pro-T1
sudo ./install.sh
```

The installer runs the existing independent installers in this order:

1. `install-ubuntu.sh --touchbar --audio --camera` — builds or reuses the T1
   and CS8409 DKMS components; camera setup remains stock UVC.
2. `sleep/manage.sh install`, then `sleep/manage-resume.py install` — disables
   NVMe D3cold, configures `pcie_port_pm=off` in GRUB, and installs guarded s2idle
   suspend with Thunderbolt removal/recovery and internal playback recovery.
   The second command runs under a
   sleep/shutdown inhibitor. A fresh installation requires a restart to activate
   the boot setting; the guard refuses sleep until then. Use `--no-sleep` to skip
   all sleep and boot configuration. See [sleep diagnostics](sleep/README.md).
3. `wifi/install-5ghz.sh` — builds the exact Ubuntu brcmfmac DKMS module,
   fetches the checksum-pinned board-data file, creates a high-priority 5 GHz
    NetworkManager profile, and disables automatic fallback to older Wi-Fi profiles.
4. `desktop/configure.sh` — reports the three touchpad settings without changing
   them, then enables GNOME Bounce Keys with a 100 ms delay.
5. `touchid/manage.py auto` — detects prerequisites/conflicts and reports the
   closed Touch ID release gate; saves a private JSON report under
   `/var/lib/macbook-t1-touchid-reports/`. It preserves the existing password path.

Useful options:

```bash
./install.sh --plan
sudo ./install.sh --no-sleep
sudo ./install.sh --activate-wifi       # requires independent Ethernet
sudo ./install.sh --wifi-profile UUID   # choose a saved WPA2 profile
sudo ./install.sh --no-install-deps
sudo ./install.sh --no-wifi
sudo ./install.sh --no-desktop
```

The Wi-Fi installer does not copy proprietary firmware into Git. It obtains the
Ubuntu firmware package and separately fetches the referenced board data. It
preserves the device MAC and does not rewrite unrelated security profiles.

## Verification and removal

```bash
./verify-ubuntu.sh --all
python3 sleep/manage-resume.py verify
sudo ./wifi/verify-5ghz.sh
./verify-camera.sh --capture
sudo ./wifi/uninstall-5ghz.sh
```

The Wi-Fi subsystem was restored to the original stock baseline, then rebuilt
for **5 GHz only**. It now associates on channel 48 at 80 MHz with native India
firmware-country handling; Wi-Fi-bound DNS/HTTPS and a deliberate reconnect pass.
Older profiles keep their credentials with automatic fallback disabled.
The required `brcmfmac-wcc` boot helper is explicitly included in the initramfs.
Current measurements are in [WIFI-5GHZ-BENCHMARKS.md](WIFI-5GHZ-BENCHMARKS.md).
Reboot/suspend acceptance is separate from live connection tests.

The one-shot installer includes the guarded s2idle workaround and reopens the
internal playback PCM after wake. On **21 October 2026**, the user confirmed
successful sleep/wake with audio working after installing this recovery. The
normal suspend service also logged successful audio and controller recovery.
Long-term reliability and sleep battery drain have not been measured.
Sleep is refused with storage attached under the Thunderbolt
branches or with unknown PCIe devices. Installation never initiates sleep or
reboots automatically. Evidence, verification and rollback instructions are in
[sleep/README.md](sleep/README.md).

## Files

| File/directory | Purpose |
|---|---|
| `install.sh` | One-shot installer |
| `install-ubuntu.sh` | Touch Bar/audio/camera component router |
| `wifi/install-5ghz.sh` | Optional 5 GHz DKMS installation |
| `wifi/verify-5ghz.sh` | 5 GHz verification |
| `wifi/uninstall-5ghz.sh` | 5 GHz rollback/removal |
| `desktop/configure.sh` | GNOME settings configuration |
| `WIFI-5GHZ-IMPLEMENTATION.md` | Final implementation details |
| `WIFI-5GHZ-BENCHMARKS.md` | Actual measured results |
| `WIFI-5GHZ-RECOVERY.md` | Recovery and rollback |
| `CREDITS.md` | Essential upstream GitHub credits |
| `LICENSE` | License boundaries |

## Licensing

New integration code, scripts, tests and documentation—including AI-generated
original code—are MIT licensed unless an upstream license applies. Included
Touch Bar/audio kernel sources and derivative driver patches retain their
original GPL or ISC licenses in their source headers and accompanying license
files. Ubuntu/Broadcom firmware is not redistributed here and remains subject
to its own license.

See [LICENSE](LICENSE) and [CREDITS.md](CREDITS.md).
