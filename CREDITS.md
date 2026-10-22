# Essential upstream credits

**Iniyavan** took responsibility for adapting, testing,
packaging and integrating the complete setup. These are the GitHub projects
without which the corresponding parts of this repository could not have been
assembled:

## 1. Wi-Fi: Bogdan7c

**Repository:** https://github.com/Bogdan7c/macbook-bcm43602-wifi-fix

**Commit used as reference:**
`35dd57c5b2b0fc8f76af5c6c2a45ead010692421`

The 5 GHz BCM43602 investigation, model-matched board-data reference and DKMS
structure informed this work. The current rebuild retains native country handling;
the earlier foreign-country table and regulatory-guard patches were removed.
The Ubuntu implementation here is independently adapted and does not run the
original installer. Its original MIT/ISC boundaries remain applicable to the
corresponding upstream material.

## 2. Touch Bar: AJ-dev-i60

**Repository:** https://github.com/AJ-dev-i60/t1-touchbar

**Revision:** `20d65c7b0fe6d05ea9734f869b27384a62de5109`

The T1 Touch Bar/iBridge driver lineage and resume behavior used by this
project come from the AJ-dev-i60 implementation. The exact pinned source
revision and GPL notices are preserved in the driver files.

## 3. Audio: davidjo

**Repository:** https://github.com/davidjo/snd_hda_macbookpro

**Commit:** `89b22ff90b86468b186706861dd18663562defa7`

The Apple CS8409 audio implementation and speaker/headphone/microphone support
are based on this project. The GPL license and upstream source notices remain
under `audio/upstream/` and `audio/kernel-source/`.

## 4. Suspend/resume research: Dunedan

**Repository:** https://github.com/Dunedan/mbp-2016-linux

The MacBookPro13,2 Apple NVMe D3cold resume workaround follows the hardware-
specific guidance in the repository's [Suspend & Hibernation
notes](https://github.com/Dunedan/mbp-2016-linux#suspend--hibernation). The
model-checked udev rule and installer integration in this repository are
independently implemented.

## 5. Touch ID development: T1Bridge and libfprint/fprintd

T1Bridge developers and packaging contributors, including **Andrew Boyd,
Jose Salazar and Nicolas Nistal**, supplied the T1 protocol, Secure Enclave
fingerprint implementation, protected keybag storage, machine-data importer,
kernel integrations, renderer, service contracts and Arch packaging used here.
Source: https://github.com/standardagents/t1bridge at
`81cbdf81026a16e02f0bea74735c6b029a8ffae2` (0.1.12).

The matched fingerprint stack builds on **Daniel Drake, Bastien Nocera and the
libfprint/fprintd contributors**. The AppStream generator adaptation retains
**Marco Trevisan**'s copyright and LGPL notice. T1Bridge's DRM and UVC sources
retain **Kerem Karabay**, **Laurent Pinchart**, Linux contributors and other
original notices. Exact revisions, packaging credit and license boundaries are
in [TOUCHID-UPSTREAM-ATTRIBUTION.md](TOUCHID-UPSTREAM-ATTRIBUTION.md).

This project's work is portability, packaging, testing and integration; upstream
biometric/hardware functionality is not claimed as original work.

## License rule for this repository

Original integration code, scripts, tests, documentation and original AI-created
code are MIT licensed unless an upstream license prevents relicensing. Upstream
GPL and ISC source remains under its own license. Proprietary Ubuntu/Broadcom
firmware and separately fetched board data are not included in this repository.
