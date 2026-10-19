# Exact-source BCM43602 DMA module

This is part of the macbook-pro-T1 Wi-Fi component. Use `install-wifi.sh
--dma-fix`; do not install this directory as an unrelated driver.

`kernel-source/7.3.0-9.9/{brcmfmac,include}` is the unmodified corresponding
subtree of Ubuntu's `linux-source-7.3.0` package, version `7.3.0-9.9`, obtained
from the configured Ubuntu archive. The source tarball SHA256 is
`0642d50f59a0e720a24f26de61743d822631616a9e0d19fa9d900f4168e793fb`.
Its upstream location is
[`drivers/net/wireless/broadcom/brcm80211`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/net/wireless/broadcom/brcm80211).

All bundled driver files retain their original copyright and ISC SPDX notices;
the corresponding Linux `LICENSES/deprecated/ISC` is in `LICENSE.ISC`.
The small build/deployment scripts are MIT, under the repository license.
No firmware or calibration data is bundled. `SOURCE-SHA256.json` verifies
the pristine source and the patch copied from `wifi/patches` by the installer.

Preparation obtains the exact header package's **source version**, uses the
matching bundled source, or requires the installed `linux-source-7.3.0` package
to have that same version. Patch application allows no fuzz. DKMS builds with
the target kernel's configuration/headers and `W=1`. Only `brcmfmac` is
installed; Ubuntu's `brcmutil` and firmware-vendor modules remain installed.
Their private ABI must come from that same Ubuntu source version.

DKMS autoinstall covers the audited `7.3.0-*-generic` family when matching source
is available. A future ABI without that source fails the build explicitly.
Other kernel families are excluded, not claimed supported. Before rebooting
after an upgrade, check `dkms status` and module selection for the new kernel;
keep the working older kernel. The patch may require review for later source
changes. See `WIFI-RECOVERY.md` at the repository root.
