#!/usr/bin/env bash
# Real installer lifecycle in a disposable QEMU guest, with synthetic USB/DMI only.
# This must NEVER run on the physical Mac. No module loading occurs.
set -euo pipefail
[[ $(uname -s) == Linux && $EUID == 0 ]] || exit 77
[[ $(cat /sys/class/dmi/id/sys_vendor) == QEMU ]] || { echo 'Disposable QEMU guest required'; exit 77; }
[[ ${1:-} == --inside-namespace ]] || exec unshare --mount --propagation private "$0" --inside-namespace
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
[[ ! -e /var/lib/macbook-t1-ubuntu ]] || { echo 'Guest has an existing transaction'; exit 1; }
TMP=$(mktemp -d)
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -e /var/lib/macbook-t1-ubuntu ]]; then bash "$ROOT/uninstall-ubuntu.sh" || true; fi
    rm -rf -- "$TMP"
    exit "$status"
}
trap cleanup EXIT
if bash install-ubuntu.sh > "$TMP/rejected" 2>&1; then echo 'ERROR: accepted QEMU hardware'; exit 1; fi
grep -q 'supports MacBookPro13,2 only' "$TMP/rejected"
echo 'PASS unsupported hardware rejected before writes'
[[ ! -e /var/lib/macbook-t1-ubuntu ]]
mkdir -p "$TMP/usb/1-3"
printf 'MacBookPro13,2\n' > "$TMP/model"
printf '05ac\n' > "$TMP/usb/1-3/idVendor"
printf '8600\n' > "$TMP/usb/1-3/idProduct"
mount --bind "$TMP/model" /sys/class/dmi/id/product_name
mount --bind "$TMP/usb" /sys/bus/usb/devices
if bash install-ubuntu.sh; then echo 'PASS install, DKMS build/sign/install and initramfs'; else exit 1; fi
dkms status -m macbook-t1-touchbar -v 1.0.0 -k "$(uname -r)" | grep ': installed'
systemctl is-enabled macbook-t1-touchbar.service
grep -q 'skip_acpi_power=1' /etc/modprobe.d/macbook-t1-touchbar.conf
[[ ! -d /sys/module/apple_ibridge && ! -d /sys/module/apple_touchbar ]]
echo 'PASS installer did not load modules'
cert=$(sed -n 's/^Public certificate (MOK): *//p' /var/lib/macbook-t1-ubuntu/build.log | tail -1)
if [[ -f $cert ]]; then
    ko=$(modinfo -F filename apple_ibridge)
    python3 lib/check-signature.py "$ko" "$cert"
    python3 - "$ko" "$TMP/tampered.ko" <<'PY'
from pathlib import Path
import runpy
import sys
read = runpy.run_path('lib/check-signature.py')['module_bytes']
data = bytearray(read(Path(sys.argv[1])))
data[128] ^= 1
Path(sys.argv[2]).write_bytes(data)
PY
    if python3 lib/check-signature.py "$TMP/tampered.ko" "$cert"; then exit 1; fi
    openssl req -new -x509 -nodes -days 1 -newkey rsa:2048 -subj '/CN=Wrong test key/' \
        -keyout "$TMP/wrong.key" -outform DER -out "$TMP/wrong.der" >/dev/null 2>&1
    if python3 lib/check-signature.py "$ko" "$TMP/wrong.der"; then exit 1; fi
    echo 'PASS signature verifier accepts actual DKMS signature and rejects tampering/wrong certificate'
else
    echo 'ERROR: DKMS certificate not found'; exit 1
fi
systemd-analyze verify --man=no /etc/systemd/system/macbook-t1-touchbar.service
udevadm verify /etc/udev/rules.d/90-macbook-t1-touchbar.rules
echo 'PASS systemd service and udev rule validation'
sha256sum /etc/modprobe.d/macbook-t1-touchbar.conf > "$TMP/before-repeat"
bash install-ubuntu.sh > "$TMP/repeated" 2>&1
grep -q 'already installed' "$TMP/repeated"
sha256sum --check "$TMP/before-repeat"
echo 'PASS repeat install preserves the matching installation'
bash uninstall-ubuntu.sh
[[ ! -e /etc/modprobe.d/macbook-t1-touchbar.conf ]]
[[ ! -e /etc/systemd/system/macbook-t1-touchbar.service ]]
[[ ! -e /usr/src/macbook-t1-touchbar-1.0.0 ]]
[[ ! -e /var/lib/macbook-t1-ubuntu ]]
if dkms status | grep -q 'macbook-t1-touchbar'; then exit 1; fi
if modinfo apple_ibridge >/dev/null 2>&1; then exit 1; fi
echo 'PASS uninstall removes owned DKMS, source, configs, service and initramfs references'
bash uninstall-ubuntu.sh
echo 'PASS repeat uninstall harmless'
