#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/lib/common.sh"
deps=0
case "${1:-}" in
    --install-deps) deps=1 ;;
    --help|-h) echo 'Usage: sudo ./install-ubuntu.sh [--install-deps]'; exit 0 ;;
    '') ;;
    *) die 'Unknown argument. Use --help.' ;;
esac
[[ $# -le 1 ]] || die 'Too many arguments.'
linux_only
root_only
release=$(
    # shellcheck source=/dev/null
    source /etc/os-release
    printf '%s:%s' "$ID" "$VERSION_ID"
)
[[ $release == ubuntu:26.10 ]] || die 'Target is Ubuntu 26.10 (latest stable at packaging time).'
hardware_check
KERNEL=$(uname -r)
supported_kernel "$KERNEL" || die "Unsupported kernel $KERNEL; this package targets Ubuntu 7.3.0-*-generic."
[[ -d /run/systemd/system ]] || die 'Requires a normally booted systemd Ubuntu installation.'
[[ ! -e $STATE && ! -L $STATE ]] || die "Existing installation/transaction at $STATE. Run verify-ubuntu.sh or uninstall-ubuntu.sh first."
if [[ $deps == 1 ]]; then
    apt-get update
    apt-get install -y build-essential dkms "linux-headers-$KERNEL" \
        mokutil openssl kmod python3 usbutils initramfs-tools zstd
fi
for tool in dkms make x86_64-linux-gnu-gcc python3 modinfo modprobe depmod mokutil openssl \
            systemctl udevadm update-initramfs flock sha256sum findmnt zstd; do
    command -v "$tool" >/dev/null || die "Missing $tool. Re-run with --install-deps."
done
[[ -f /lib/modules/$KERNEL/build/Makefile ]] || die "Missing matching linux-headers-$KERNEL; no generic-header fallback is used."
# Ubuntu's headers can retain an upstream -rc Makefile version. Use the
# packaged, generated ABI identifiers rather than recomputing kernelrelease.
[[ $(cat "/lib/modules/$KERNEL/build/include/config/kernel.release") == "$KERNEL" ]] || die 'Header/kernel release mismatch.'
grep -Fxq "#define UTS_RELEASE \"$KERNEL\"" "/lib/modules/$KERNEL/build/include/generated/utsrelease.h" || die 'Header UTS_RELEASE mismatch.'
[[ -f $ROOT/SHA256SUMS ]] || die 'Missing package checksum manifest.'
(cd "$ROOT" && sha256sum --check --quiet SHA256SUMS) || die 'Package checksum mismatch.'
python3 "$ROOT/lib/preflight.py"
existing=$(dkms status)
if grep -Eq '^(apple-ib-drv|apple-touchbar|mbp-t1-touchbar-driver|macbook-t1-touchbar)[/,]' <<< "$existing"; then
    die 'A competing Touch Bar DKMS package is registered. Use its uninstaller first.'
fi
for module in apple_ibridge apple_touchbar apple_ib_tb apple_ib_als; do
    [[ ! -d /sys/module/$module ]] || die "$module is already loaded. Uninstall the previous package and reboot."
    if modinfo "$module" >/dev/null 2>&1; then die "Existing $module module would be overwritten. Resolve it first."; fi
done
[[ ! -e /usr/src/$NAME-$VERSION ]] || die 'Existing source directory; refusing to overwrite it.'
[[ ! -e /etc/systemd/system/$SERVICE && ! -L /etc/systemd/system/$SERVICE ]] || die 'Existing service file; refusing to replace it.'
SIGN_REQUIRED=0
if [[ -d /sys/firmware/efi ]]; then
    sb_rc=0
    sb=$(mokutil --sb-state 2>&1) || sb_rc=$?
    case "$sb" in
        *'SecureBoot enabled'*) [[ $sb_rc == 0 ]] || die 'Secure Boot query failed.'; SIGN_REQUIRED=1 ;;
        *'SecureBoot disabled'*) [[ $sb_rc == 0 ]] || die 'Secure Boot query failed.' ;;
        *'Failed to read "SecureBoot" variable: No such file or directory'*)
            # Older Apple EFI lacks the UEFI Secure Boot variable. Confirm
            # efivarfs is actually mounted before treating ENOENT as absence.
            [[ $(findmnt -n -o FSTYPE --target /sys/firmware/efi/efivars) == efivarfs ]] || die 'EFI variable storage unavailable.'
            [[ ! -e /sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c ]] || die 'SecureBoot variable exists but cannot be read.'
            echo 'Apple EFI has no SecureBoot variable; checking kernel signature enforcement separately.' ;;
        *) die 'Unrecognized Secure Boot state; refusing installation.' ;;
    esac
fi
if [[ -r /sys/module/module/parameters/sig_enforce ]] &&
   grep -Eq '^(Y|1)$' /sys/module/module/parameters/sig_enforce; then SIGN_REQUIRED=1; fi
if [[ -r /sys/kernel/security/lockdown ]] &&
   grep -Eq '\[(integrity|confidentiality)\]' /sys/kernel/security/lockdown; then SIGN_REQUIRED=1; fi

exec 9>/run/macbook-t1-install.lock
flock -n 9 || die 'Another install/uninstall is running.'
install -d -m700 "$STATE"
install -m644 "$ROOT/lib/deploy.py" "$STATE/deploy.py"
install -m644 "$ROOT/lib/common.sh" "$STATE/common.sh"
SRC="/usr/src/$NAME-$VERSION"
cleanup() {
    local rc=$?
    trap - EXIT
    if [[ $rc != 0 ]]; then
        echo "Installation failed. Rolling back owned changes; logs/backups retained in $STATE." >&2
        systemctl disable "$SERVICE" >/dev/null 2>&1 || true
        if [[ -e $STATE/dkms-added ]]; then dkms remove -m "$NAME" -v "$VERSION" --all || true; fi
        python3 "$STATE/deploy.py" restore || true
        if [[ -e $STATE/source-owned ]]; then rm -rf -- "$SRC"; fi
        systemctl daemon-reload || true
        udevadm control --reload-rules || true
        if [[ -e $STATE/modules-installed ]]; then update-initramfs -u -k "$KERNEL" || true; fi
        echo 'Read RECOVERY.md before retrying; uninstall-ubuntu.sh completes interrupted rollback.' >&2
    fi
    exit "$rc"
}
trap cleanup EXIT
# Keys persist across rollback/uninstall, so an approved enrollment remains
# usable on reinstall. Creating key files is not EFI enrollment.
SIGN_DIR=/var/lib/macbook-t1-signing
[[ ! -L $SIGN_DIR ]] || die 'Refusing symlink signing directory.'
install -d -m700 "$SIGN_DIR"
if [[ ! -e $SIGN_DIR/MOK.priv && ! -L $SIGN_DIR/MOK.priv && ! -e $SIGN_DIR/MOK.der && ! -L $SIGN_DIR/MOK.der ]]; then
    if [[ -f /var/lib/shim-signed/mok/MOK.priv && -f /var/lib/shim-signed/mok/MOK.der ]]; then
        ln -s /var/lib/shim-signed/mok/MOK.priv "$SIGN_DIR/MOK.priv"
        ln -s /var/lib/shim-signed/mok/MOK.der "$SIGN_DIR/MOK.der"
    elif [[ -f /var/lib/dkms/mok.key && -f /var/lib/dkms/mok.pub ]]; then
        ln -s /var/lib/dkms/mok.key "$SIGN_DIR/MOK.priv"
        ln -s /var/lib/dkms/mok.pub "$SIGN_DIR/MOK.der"
    else
        (umask 077; openssl req -new -x509 -nodes -days 3650 -newkey rsa:2048 \
            -subj '/CN=MacBook T1 module signing/' -addext 'extendedKeyUsage=codeSigning' \
            -keyout "$SIGN_DIR/MOK.priv" -outform DER -out "$SIGN_DIR/MOK.der" \
            > "$STATE/key-generation.log" 2>&1)
    fi
fi
[[ -f $SIGN_DIR/MOK.priv && -f $SIGN_DIR/MOK.der ]] || die 'Incomplete signing key pair; inspect /var/lib/macbook-t1-signing.'
touch "$STATE/source-owned"
install -d "$SRC"
for file in Makefile dkms.conf apple-ibridge.c apple-ibridge.h apple-touchbar.c hid-ids.h LICENSE; do
    install -m644 "$ROOT/driver/$file" "$SRC/"
done
# Configuration (including the freeze guard) is committed before modules exist.
python3 "$ROOT/lib/deploy.py" install "$ROOT"
touch "$STATE/dkms-added"
dkms add -m "$NAME" -v "$VERSION"
dkms build -m "$NAME" -v "$VERSION" -k "$KERNEL" 2>&1 | tee "$STATE/build.log"
module_dir="/var/lib/dkms/$NAME/$VERSION/$KERNEL/$(uname -m)/module"
if [[ $SIGN_REQUIRED == 1 ]]; then
    cert=''
    candidate=$(sed -n 's/^Public certificate (MOK): *//p' "$STATE/build.log" | tail -1)
    for key in "$candidate" "$SIGN_DIR/MOK.der"; do
        [[ -f $key ]] || continue
        key_state=$(mokutil --ignore-keyring --test-key "$key" 2>&1) || continue
        # Exit status alone also accepts pending/blocked keys in mokutil.
        if [[ $key_state == *'is already enrolled' ]]; then cert=$key; break; fi
    done
    [[ -n $cert ]] || die 'Signature enforcement is active, but no enrolled DKMS key was found. See RECOVERY.md. No key enrollment was attempted.'
    for m in apple-ibridge apple-touchbar; do
        ko=$(find "$module_dir" -maxdepth 1 -name "$m.ko*" -print -quit)
        [[ -n $ko ]] || die "Missing built module $m."
        python3 "$ROOT/lib/check-signature.py" "$ko" "$cert" || die "$m is not signed by the enrolled DKMS key."
    done
fi
touch "$STATE/modules-installed"
dkms install -m "$NAME" -v "$VERSION" -k "$KERNEL" 2>&1 | tee "$STATE/install.log"
depmod -a "$KERNEL"
for m in apple-ibridge apple-touchbar; do
    [[ $(modinfo -k "$KERNEL" -F vermagic "$m") == "$KERNEL "* ]] || die "Incorrect vermagic for $m."
    [[ $(modinfo -k "$KERNEL" -F filename "$m") == */updates/dkms/* ]] || die 'DKMS module selection failed.'
done
systemctl daemon-reload
udevadm control --reload-rules
systemctl enable "$SERVICE"
update-initramfs -u -k "$KERNEL"
printf '%s\n' "$KERNEL" > "$STATE/installed-kernel"
touch "$STATE/complete"
trap - EXIT
echo 'Installed. Reboot Ubuntu, then run: sudo ./verify-ubuntu.sh'
echo 'Physical Touch Bar operation has not yet been verified. Rollback: sudo ./uninstall-ubuntu.sh'
