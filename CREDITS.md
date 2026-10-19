# Credits, upstream lineage and licensing

This package builds on substantial work by the Linux, Broadcom and MacBook-on-Linux
communities. **Original authors retain their copyright and credit.** The root
[LICENSE](LICENSE) describes the component boundaries; original source headers,
license files and linked upstream history retain the full contributor record.
[SOURCES.md](SOURCES.md) contains the detailed pinned-source audit.

## Wi-Fi implementation and directly used references

| People / project | Contribution used here | License / provenance |
|---|---|---|
| **Broadcom Corporation and brcmfmac/brcm80211 contributors** | The underlying PCIe FullMAC driver, firmware interfaces, radio capability handling and firmware binary | Bundled driver/header files are ISC; [ISC text](wifi/dkms/LICENSE.ISC). Firmware has a [separate Broadcom license](LICENSES/Broadcom-firmware.txt). |
| **Linux kernel developers, maintainers and Linux wireless contributors** | Kernel networking/cfg80211, PCIe, IOMMU, module infrastructure, upstream fixes and source on which this package is built | Individual source SPDX notices apply. The kernel is not relicensed by this package. |
| **Canonical / Ubuntu kernel and firmware teams**, with **Debian maintainers** | Exact Ubuntu `7.3.0-9.9` source and headers, Ubuntu 26.10 integration, firmware distribution and packaging | Original upstream licenses and distribution packaging notices; no blanket MIT claim. |
| **Hans de Goede** and **the Asahi Linux Contributors** | Contributions present in the bundled brcmfmac source, including platform/Apple support | Their ISC copyright notices remain in the original files. |
| **Bogdan Korolyov (Bogdan7c)** — [macbook-bcm43602-wifi-fix](https://github.com/Bogdan7c/macbook-bcm43602-wifi-fix) | Primary 5 GHz reference: the `fixed_regdom` investigation, working model-specific NVRAM recipe, 80 MHz/GB-revision-3 findings, DKMS approach and vendor-query examples | Commit `35dd57c5b2b0fc8f76af5c6c2a45ead010692421`; driver patch ISC, scripts MIT. [Upstream MIT notice](LICENSES/Bogdan7c-MIT.txt) is retained. The Ubuntu adaptation is not his original installer. |
| **MikeRatcliffe** — [BCM43602 NVRAM gist](https://gist.github.com/MikeRatcliffe/9614c16a8ea09731a9d5e91685bd8c80) | Published board-data file referenced by Bogdan7c | Gist history revision `38180b6a0ce552e1a3a2826ffea2bf1f52d05e9f`. The board data is fetched separately; this package does not assign it a new license. |
| **Participants in Linux kernel bug 193121** and the associated MacBook Wi-Fi discussions | Shared board-data experiments and the history of BCM43602 band/firmware behavior | [Bug discussion](https://bugzilla.kernel.org/show_bug.cgi?id=193121); original authors and terms apply. Direct Bugzilla access was unavailable during parts of the investigation; quoted material was read through the linked GitHub discussions. |
| **Andy Holst (andyholst)** | Documented BCM43602 experiments and boardflag/front-end discussion, including the historical community NVRAM lineage | [BCM43602_macbookpro](https://github.com/andyholst/BCM43602_macbookpro) and Dunedan issue 47. Credit for research, not a claim that every table originated with this author. |
| **Sonal Santan (sonals)** | Windows/VFIO/MMIO tracing and board-data extraction methodology studied during the calibration investigation | [macbookpro14-3](https://github.com/sonals/macbookpro14-3), particularly `doc/MMIOTrace.rst`. A donor unit's factory calibration is not presented as this unit's calibration. |
| **Broadcom public DHD interface authors** and **Android common kernel maintainers** | Public `wlioctl` structures, command definitions and boardflag definitions used to interpret diagnostic replies | Reference headers at Android common revision `4f750cefc34ed7fc0ba4ef8b72d28b7924c24c6e`; hashes are in SOURCES.md. |

### Board-data and firmware license boundaries

The reference NVRAM is community-published data. No explicit standalone
redistribution grant for that text was established by this audit. It is **not
included in Git or the portable source archive**, and the project's MIT/ISC
licenses do not grant rights over it. Installation obtains a checksum-verified
copy from the pinned source and keeps the generated device-specific file local.
Acknowledging a source is not a substitute for its license.

The firmware binary is supplied by Ubuntu's `linux-firmware-broadcom-wireless`
package and the upstream **linux-firmware maintainers**, with copyright retained
by **Broadcom Corporation**. It remains unmodified and is not redistributed in
this source package. Its original license is reproduced for reference in
[LICENSES/Broadcom-firmware.txt](LICENSES/Broadcom-firmware.txt).

## Touch Bar / iBridge and HID lineage

* **Ronald Tschalär (roadrunner2)** — original Apple iBridge and Touch Bar driver
  authorship, including the 2017–2018 copyright notices preserved in `driver/`.
* **t2linux/apple-ib-drv contributors** — upstream lineage and Apple HID/iBridge
  work; audited `mbp15` revision `4afd30950a7364b06b8cef8a34d6cc6653ca3120`.
* **AJ-dev-i60 and t1-touchbar contributors** — selected T1 implementation,
  revision `20d65c7b0fe6d05ea9734f869b27384a62de5109`.
* **Eugene Ray** — upstream resume/keypress patch, PR #1, revision
  `a33c7eb27777339c047b8f532d1e6baebaec46bd`; its reported OpenAI Codex assistance
  is preserved in the source audit.
* **Andreas Gal**, **Vojtech Pavlik**, **Michael Haboustak / Concept2, Inc.**, and
  **Jiri Kosina** — copyright holders named in the included HID definitions.
* **Linux HID, input and USB maintainers and contributors** — the kernel
  infrastructure and definitions on which this driver depends.

These sources and derivative changes retain their GPL-2.0 / GPL-2.0-or-later
notices. See [driver/LICENSE](driver/LICENSE) and the individual source headers.

## Audio, camera, keyboard and trackpad

* **davidjo and snd_hda_macbookpro contributors** — Apple CS8409 audio work,
  pinned at `89b22ff90b86468b186706861dd18663562defa7`.
* **leifliddy** — installation setup credited in the upstream audio README.
* **Cirrus Logic, Inc.**, **Cirrus Logic International Semiconductor Ltd.**,
  **Takashi Iwai**, and **Linux/ALSA contributors** — underlying HDA/CS8409 source
  and audio infrastructure. Original GPL notices and license texts are retained
  under `audio/upstream/` and `audio/kernel-source/`.
* **Laurent Pinchart and Linux UVC contributors** — the stock `uvcvideo` driver
  used for the FaceTime HD camera; this project integrates/tests that driver.
* **Ronald Tschalär**, **Federico Lorenzi**, and **Linux input contributors** —
  the stock Apple SPI keyboard/trackpad support on which this installation relies.
* **PipeWire, WirePlumber, PulseAudio and ALSA communities** — userspace audio
  routing, policy, compatibility interfaces and diagnostics.

## Research and compatibility acknowledgments

The following work informed diagnosis or compatibility choices. Their findings
are credited even where their installers, patches or settings were not adopted:

* **DeyAgrO**, [macbook-pro-13-2-linux](https://github.com/DeyAgrO/macbook-pro-13-2-linux),
  `1d52273baa4d86f71113b4e65a181c839fce94fb`.
* **Nori Nishigaya (xeeban)** and contributors,
  [macbook-t1-linux](https://github.com/xeeban/macbook-t1-linux),
  `982d97a61a0c834d03e7cf7af5203b11ad7bae44`.
* **Dunedan and mbp-2016-linux contributors/reporters**,
  `3da5e3f586ecd835c12d2c6a3021e66ca0934d96`, particularly the Wi-Fi issue discussions.
* **bgausden**, for the documented suspend/board-data investigation.
* **Michele Dionisio**, for the proposed P2P teardown-locking fix studied when
  designing the quiesced unload/recovery procedure; that patch is not included.
* **Ubuntu bug 2169339 participants**, for independent BCM43602/IOMMU reports.
* **Phennova**, **parport0**, **xtocdra**, **moabdrabou**, **standardagents/t1bridge**,
  and their contributors, for MacBook hardware compatibility and alternative
  implementations reviewed in SOURCES.md.
* **Tim Sutton / Brigadier contributors**, **sgan81 / apfs-fuse contributors**,
  **libyal / libfsapfs contributors**, and **Apple / LZFSE contributors**, for
  tools/methods used in the private, read-only firmware-source investigation.
* **Apple** and **Intel**, for hardware documentation, Apple PKI/Boot Camp source
  provenance and the USB 3 / 2.4 GHz interference guidance reviewed.
* **StreamUnlimited/broadcom-bcmdhd-4359 maintainers** and the original Broadcom
  interface authors, for additional public interface-header research.

## Build, packaging, runtime and validation tools

Credit also goes to these external projects and all their maintainers:

* **GNU / Free Software Foundation and contributors** — GCC, Binutils, Make,
  patch, Bash, coreutils, tar and gzip.
* **Dell / DKMS maintainers**, **Linux kmod maintainers**, **dracut contributors**,
  **systemd contributors**, and **Debian/Ubuntu APT, dpkg and packaging teams** —
  module builds, installation, early boot, services and reversible deployment.
* **Python Software Foundation and Python contributors** — the implementation
  language and standard library used by the integration and diagnostic tools.
* **GNOME, GLib/GSettings and dconf contributors** — the per-user desktop and
  accessibility settings used by the optional desktop configuration step.
* **NetworkManager contributors**, **Netplan contributors**, **Jouni Malinen and
  hostap/wpa_supplicant contributors**, and **wireless-regdb maintainers** —
  association, authentication, saved-profile management and regulatory data.
* **iw/nl80211**, **iproute2**, **iputils**, **ethtool**, **pciutils**, **usbutils**
  and **BlueZ** contributors — hardware/network diagnostics and control APIs.
* **ESnet / Lawrence Berkeley National Laboratory and iperf3 contributors** —
  measured LAN throughput testing.
* **Daniel Stenberg and curl contributors**, **OpenSSL**, **OpenSSH**, **Git**
  and **GitHub** — authenticated transport, provenance checks and version control.
* **Meta / Zstandard contributors**, **7-Zip/p7zip**, **UnRAR**, **QEMU**,
  **FFmpeg**, **v4l-utils**, **Mozilla Firefox** and **ShellCheck** contributors —
  build/research environments, archive processing, hardware validation and checks.
* **OpenCode** and **OpenAI-assisted development tooling**, for implementation,
  investigation and test assistance; original upstream authorship remains as
  credited above.

These tools are dependencies or development aids, not bundled toolchain
executables. Each retains its own license and copyright; using a tool does not
relicense the driver sources under that tool's license.

## Project integration

**Iniy** and the **macbook-pro-T1 contributors** provide the Ubuntu integration,
hardware-scoped local fixes, diagnostics, rollback, packaging and documentation.
New integration material is MIT; changes to upstream driver code retain the
affected files' upstream licenses. Attribution does not imply upstream endorsement.
