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

## License rule for this repository

Original integration code, scripts, tests, documentation and original AI-created
code are MIT licensed unless an upstream license prevents relicensing. Upstream
GPL and ISC source remains under its own license. Proprietary Ubuntu/Broadcom
firmware and separately fetched board data are not included in this repository.
