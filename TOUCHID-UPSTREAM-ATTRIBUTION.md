# Touch ID upstream attribution

This branch integrates existing engineering; it does not claim to have invented
Apple T1 communication, Secure Enclave fingerprint matching, keybags, calibration
import, the Touch Bar renderer, or the libfprint driver.

| Work | Source and exact revision | Authors / license |
| --- | --- | --- |
| T1Bridge runtime, service contracts, importer, SEP broker, keybag and xART persistence, renderer, Arch recipes and fingerprint patches | https://github.com/standardagents/t1bridge at `81cbdf81026a16e02f0bea74735c6b029a8ffae2` (0.1.12) | T1Bridge contributors; commit history includes Andrew Boyd, Jose Salazar and Nicolas Nistal. MIT except the boundaries below. Arch recipe adaptation is credited to those upstream packaging contributors. |
| libfprint | https://gitlab.freedesktop.org/libfprint/libfprint at `3f1e2817ed01660d0b422a0283effc0e5d3e4b80` (1.94.100) | Daniel Drake and the libfprint contributors; LGPL-2.1-or-later. T1Bridge's added driver has its original MIT notice. |
| fprintd | https://gitlab.freedesktop.org/libfprint/fprintd at `b54a007ccf58ac0ae074c7151b223f35cbd17306` (1.94.5) | Daniel Drake, Bastien Nocera and contributors; GPL-2.0-or-later. |
| appletbdrm, as carried by pinned T1Bridge | T1Bridge `kernel/appletbdrm-t1`, including its upstream patches | Kerem Karabay, Linux and T1Bridge contributors; GPL-2.0-only. |
| uvcvideo, as carried by pinned T1Bridge | T1Bridge `kernel/uvcvideo-t1`, Linux 7.1.9 base according to upstream | Laurent Pinchart, Linux and T1Bridge contributors; GPL-2.0-or-later. |
| T1 configuration selector and NCM adapter | Pinned T1Bridge `kernel/t1-cfgsel` and `kernel/apple-t1-ncm` | T1Bridge contributors; dual MIT/GPL-2.0-only. |

The original driver headers, SPDX identifiers and complete license files remain
in fetched sources and the private bundle. Upstream renderer assets (Cupertino,
Myna UI and Inter), recovery parsing crates, and their MIT/OFL terms are preserved
verbatim in `touchid/upstream-notices/T1Bridge-THIRD-PARTY.md`. Existing project
contributors and driver lineages remain credited in `CREDITS.md`.

## Classification of this branch

**Original upstream work:** all biometric protocols, hardware-backed matching,
protected persistence, source drivers and fingerprint protocol patches.

**Adapted work:** `touchid/patches/0001-link-native-dependencies-after-static-archive.patch`
reorders Cargo native link directives for GNU ld. Private source builds reproduce
the upstream Arch recipe's selected binaries/features and fingerprint patches
without executing pacman recipes. The generated DKMS metadata fixes its stale
0.1.11 version to 0.1.12 and restricts automatic builds to the target kernel ABI.

**New implementation / integration work:** read-only discovery, distribution
command adapters, pinned retrieval, isolated fingerprint builds, private bundle
verification/installation/removal, file transaction support, the default installer
acceptance report, failure-path tests and documentation in this repository.
These are MIT licensed. Distribution recognition is not hardware validation.

No Apple binary, FDR record, biometric material, packet capture or calibration
payload is committed or packaged. The private bundle contains open-source code
only. Online recovery is present in the pinned upstream tool but is never invoked
by this integration.

## Reproducibility and distribution

`sources.lock.json` pins repositories, archive hashes and the local patch hash.
Do not float upstream revisions during an install. Source downloads and compiled
outputs stay in ignored `sources/`. Before distributing any compiled bundle,
provide the complete corresponding patched GPL/LGPL sources and build scripts,
and the license notices, alongside it. The Git branch distributes integration
source and notices, not compiled T1Bridge binaries. The local DEB is an evaluation
artifact, not a validated public package release.

Additional adapted files are `fprintd/meson.build` (private policy-data paths,
GPL-2.0-or-later) and `libfprint/fprint-list-metainfo.c` (USB-presence metadata,
LGPL-2.1-or-later; original copyright Marco Trevisan). Their minimal patches and
hashes are in `touchid/fprintd-patches/`, `touchid/libfprint-patches/` and the lock
file. The one-boot migration and desktop-provider code are original integration
work; they use upstream protocols and do not implement biometric matching.
