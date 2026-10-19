# MacBookPro13,2 Ubuntu support

One-shot setup for the late-2016 MacBook Pro 13,2 on Ubuntu 26.10:

* Apple T1 Touch Bar and keyboard integration
* CS8409 internal speakers, headphones and microphone
* FaceTime HD camera through Ubuntu `uvcvideo`
* Optional Broadcom BCM43602 5 GHz / 80 MHz Wi-Fi
* GNOME Bounce Keys preference

Test target: Ubuntu 26.10, kernel `7.3.0-9-generic`, matching Ubuntu source and
headers `7.3.0-9.9`. Other releases, kernels and Mac models are not claimed.

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
2. `wifi/install-5ghz.sh` — builds the exact Ubuntu brcmfmac DKMS module,
   fetches the checksum-pinned board-data file, creates a high-priority 5 GHz
   NetworkManager profile, and preserves the original profile as fallback.
3. `desktop/configure.sh` — reports the three touchpad settings without changing
   them, then enables GNOME Bounce Keys with a 100 ms delay.

Useful options:

```bash
./install.sh --plan
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
sudo ./wifi/verify-5ghz.sh
./verify-camera.sh --capture
sudo ./wifi/uninstall-5ghz.sh
```

The 5 GHz implementation has automatic timed/boot recovery and preserves the
previous kernel module and initramfs. It was measured on this machine at 80 MHz
on channel 48: **316.55 Mbps download, 84.68 Mbps upload, 0% gateway loss** in
the selected-AP short test. A 30-minute, reboot and suspend/resume test was not
completed. 2.4 GHz fallback association was not successful with the 5 GHz
board-data configuration.

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
