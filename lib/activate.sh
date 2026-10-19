#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Runs at late boot; only rebinds the T1 HID children, never the USB camera.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib/common.sh
source "$HERE/common.sh"
linux_only
root_only
hardware_check
supported_kernel "$(uname -r)" || die 'Kernel outside the validated API family; service stopped.'
[[ " $(cat /proc/cmdline) " != *' t1_touchbar.disable=1 '* ]] || exit 0
exec 9>/run/macbook-t1-touchbar.lock
flock -n 9 || die 'Another activation is running.'
for d in /sys/bus/usb/devices/*; do
    [[ -f $d/idVendor && -f $d/idProduct ]] || continue
    if [[ $(cat "$d/idVendor") == 05ac && $(cat "$d/idProduct") == 8600 ]]; then
        [[ $(cat "$d/bConfigurationValue") == 1 ]] || die 'iBridge not in USB configuration 1. Reboot; see RECOVERY.md.'
    fi
done
# Load the child driver first so virtual HID devices bind during parent probe.
modprobe apple_touchbar
modprobe apple_ibridge skip_acpi_power=1
[[ $(cat /sys/module/apple_ibridge/parameters/skip_acpi_power) == 1 ]] || die 'ACPI freeze guard not active.'
target=/sys/bus/hid/drivers/apple-ibridge-hid
[[ -d $target ]] || die 'iBridge platform probe failed; see diagnostics.'
count=0
for d in /sys/bus/hid/devices/0003:05AC:8600.*; do
    [[ -d $d ]] || continue
    id=${d##*/}
    current=''
    if [[ -L $d/driver ]]; then current=$(basename "$(readlink -f "$d/driver")"); fi
    case "$current" in
        apple-ibridge-hid) count=$((count + 1)); continue ;;
        hid-generic|hid-sensor-hub|'') ;;
        *) die "Unexpected T1 HID owner: $current. Refusing to evict it." ;;
    esac
    if [[ -n $current ]]; then printf '%s' "$id" > "/sys/bus/hid/drivers/$current/unbind"; fi
    if ! printf '%s' "$id" > "$target/bind"; then
        # Restore the previous HID driver if our targeted bind fails.
        if [[ -n $current ]]; then printf '%s' "$id" > "/sys/bus/hid/drivers/$current/bind" || true; fi
        die "Binding $id failed; no USB reset was attempted."
    fi
    count=$((count + 1))
done
[[ $count -gt 0 ]] || die 'No T1 HID interfaces enumerated.'
found=0
for d in /sys/bus/hid/devices/0003:1D6B:0301.*; do
    [[ -f $d/fnmode ]] && found=1
done
[[ $found == 1 ]] || die 'No Touch Bar control interface; inspect verify-ubuntu.sh.'
printf 'T1 HID binding complete; physical key/display verification is still required.\n'
