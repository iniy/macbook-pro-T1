#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Install/remove the model-specific Apple NVMe suspend workaround. Never suspends.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
SOURCE="$ROOT/99-macbook-t1-nvme-sleep.rules"
RULE=/etc/udev/rules.d/99-macbook-t1-nvme-sleep.rules

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
usage() { echo "Usage: $0 {install|verify|uninstall}"; }

case ${1:-} in
    install|verify|uninstall) ACTION=$1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac
[[ $# == 1 ]] || { usage >&2; exit 2; }
[[ $(uname -s) == Linux ]] || die 'This workaround requires Linux.'
[[ $(cat /sys/class/dmi/id/product_name) == MacBookPro13,2 ]] || die 'Only MacBookPro13,2 is supported.'

DEVICES=()
for device in /sys/bus/pci/devices/*; do
    [[ $(cat "$device/vendor") == 0x106b ]] || continue
    [[ $(cat "$device/device") == 0x2003 ]] || continue
    [[ -f $device/d3cold_allowed ]] || die "Missing d3cold_allowed for $device"
    [[ $(basename "$(readlink -f "$device/driver")") == nvme ]] || die "Apple controller is not bound to nvme: $device"
    DEVICES+=("$device")
done
[[ ${#DEVICES[@]} == 1 ]] || die 'Expected exactly one Apple S3X NVMe controller (106b:2003).'
ATTRIBUTE=${DEVICES[0]}/d3cold_allowed

verify() {
    local failed=0
    if [[ -f $RULE && ! -L $RULE ]] && cmp -s "$SOURCE" "$RULE"; then
        echo "PASS persistent rule: $RULE"
    else
        echo "FAIL persistent rule missing or different: $RULE"
        failed=1
    fi
    if [[ $(cat "$ATTRIBUTE") == 0 ]]; then
        echo "PASS Apple NVMe D3cold disabled: $ATTRIBUTE"
    else
        echo "FAIL Apple NVMe D3cold is still allowed: $ATTRIBUTE"
        failed=1
    fi
    printf 'Sleep mode: '; cat /sys/power/mem_sleep
    echo 'Physical sleep/wake validation is separate; these checks do not prove resume reliability.'
    return "$failed"
}

if [[ $ACTION == verify ]]; then
    verify
    exit
fi
[[ $EUID == 0 ]] || die "Administrator authentication required: sudo $0 $ACTION"
[[ ! -L $RULE ]] || die "Refusing to modify symlink: $RULE"
if [[ -e $RULE ]] && ! cmp -s "$SOURCE" "$RULE"; then
    die "Existing rule differs; preserve and review it before proceeding: $RULE"
fi

if [[ $ACTION == uninstall ]]; then
    if [[ -f $RULE ]]; then
        rm -- "$RULE"
        udevadm control --reload-rules
    fi
    echo 'Persistent workaround removed. The current setting stays in effect until reboot.'
    echo 'After reboot the kernel defaults apply again. No reboot was requested.'
    exit
fi

udevadm verify "$SOURCE"
PREVIOUS=$(cat "$ATTRIBUTE")
[[ $PREVIOUS == 0 || $PREVIOUS == 1 ]] || die "Unexpected D3cold value: $PREVIOUS"
CREATED=0
rollback() {
    local rc=$?
    trap - EXIT
    if [[ $rc != 0 ]]; then
        echo 'Installation failed; restoring the previous setting.' >&2
        printf '%s\n' "$PREVIOUS" > "$ATTRIBUTE" || true
        if [[ $CREATED == 1 ]]; then
            rm -f -- "$RULE"
            udevadm control --reload-rules || true
        fi
    fi
    exit "$rc"
}
trap rollback EXIT
if [[ ! -f $RULE ]]; then
    install -d -m 0755 /etc/udev/rules.d
    CREATED=1
    install -o root -g root -m 0644 "$SOURCE" "$RULE"
fi
udevadm control --reload-rules
printf '0\n' > "$ATTRIBUTE"
verify
echo 'Applied now and configured for subsequent boots. No reboot or suspend was requested.'
