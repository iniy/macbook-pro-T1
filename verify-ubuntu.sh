#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Read-only, allowlisted diagnostics: no dmesg dump, serials or UUIDs.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/lib/common.sh"
for arg in "$@"; do
    case "$arg" in
        --touchbar|--audio|--camera|--wifi|--all|--verify)
            exec python3 "$ROOT/lib/components.py" verify "$@" ;;
    esac
done
linux_only
[[ $# == 0 ]] || die 'Usage: sudo ./verify-ubuntu.sh'
failed=0
ok() { printf 'PASS %s\n' "$*"; }
bad() { printf 'FAIL %s\n' "$*"; failed=1; }
printf 'Kernel: %s\nModel: %s\n' "$(uname -r)" "$(cat /sys/class/dmi/id/product_name)"
if [[ $(cat /sys/class/dmi/id/product_name) == MacBookPro13,2 ]]; then ok 'Target model'; else bad 'Unsupported model'; fi
if supported_kernel "$(uname -r)"; then ok 'Supported kernel API family'; else bad 'Kernel outside validated family'; fi
if command -v dkms >/dev/null; then
    status=$(dkms status -m "$NAME" -v "$VERSION" -k "$(uname -r)" 2>/dev/null || true)
    if [[ $status == *': installed'* ]]; then ok 'DKMS installed for running kernel'; else bad 'DKMS not installed for running kernel'; fi
else bad 'dkms missing'; fi
for m in apple_ibridge apple_touchbar; do
    if [[ -d /sys/module/$m ]]; then ok "$m loaded"; else bad "$m not loaded"; fi
    if command -v modinfo >/dev/null && modinfo "$m" >/dev/null 2>&1; then
        printf '%s path: %s\n' "$m" "$(modinfo -F filename "$m")"
        printf '%s signer: %s\n' "$m" "$(modinfo -F signer "$m")"
        if [[ $(modinfo -F vermagic "$m") == "$(uname -r) "* ]]; then ok "$m vermagic"; else bad "$m vermagic mismatch"; fi
    fi
done
if [[ -r /sys/module/apple_ibridge/parameters/skip_acpi_power ]] &&
   [[ $(cat /sys/module/apple_ibridge/parameters/skip_acpi_power) == 1 ]]; then
    ok 'skip_acpi_power=1'
else bad 'Freeze guard missing or not equal to 1'; fi
usb=0
camera=0
for d in /sys/bus/usb/devices/*; do
    [[ -f $d/idVendor && -f $d/idProduct ]] || continue
    [[ $(cat "$d/idVendor") == 05ac && $(cat "$d/idProduct") == 8600 ]] || continue
    usb=$((usb + 1))
    if [[ $(cat "$d/bConfigurationValue") == 1 ]]; then ok 'T1 USB configuration 1'; else bad 'T1 USB configuration is not 1'; fi
    printf 'T1 USB power/control: %s\n' "$(cat "$d/power/control")"
    for intf in "$d":*; do
        [[ -f $intf/bInterfaceClass ]] || continue
        owner=unbound
        [[ ! -L $intf/driver ]] || owner=$(basename "$(readlink -f "$intf/driver")")
        printf 'T1 interface %s class=%s driver=%s\n' "${intf##*:}" "$(cat "$intf/bInterfaceClass")" "$owner"
        [[ $owner != uvcvideo ]] || camera=1
    done
done
if [[ $usb == 1 ]]; then ok 'One T1 05ac:8600'; else bad 'T1 absent or ambiguous'; fi
count=0
for d in /sys/bus/hid/devices/0003:05AC:8600.*; do
    [[ -d $d ]] || continue
    count=$((count + 1))
    owner=unbound
    [[ ! -L $d/driver ]] || owner=$(basename "$(readlink -f "$d/driver")")
    if [[ $owner == apple-ibridge-hid ]]; then ok 'T1 physical HID bound'; else bad "T1 physical HID owner: $owner"; fi
done
[[ $count -gt 0 ]] || bad 'No physical T1 HID devices'
controls=0
input=0
for d in /sys/bus/hid/devices/0003:1D6B:0301.*; do
    [[ -f $d/fnmode ]] || continue
    controls=1
    printf 'Controls: fnmode=%s idle_timeout=%s dim_timeout=%s\n' "$(cat "$d/fnmode")" "$(cat "$d/idle_timeout")" "$(cat "$d/dim_timeout")"
    for event in "$d"/input/input*/event*; do
        [[ ! -d $event ]] || { printf 'Touch Bar input: /dev/input/%s\n' "${event##*/}"; input=1; }
    done
done
if [[ $controls == 1 ]]; then ok 'Touch Bar control attributes'; else bad 'No Touch Bar control attributes'; fi
if [[ $input == 1 ]]; then ok 'Touch Bar event device'; else bad 'No Touch Bar event device'; fi
if [[ $camera == 1 ]]; then ok 'T1 webcam UVC binding (picture not tested)'; else printf 'NOTE T1 webcam UVC binding not detected; check camera separately.\n'; fi
if command -v mokutil >/dev/null; then mokutil --sb-state 2>/dev/null || true; fi
if systemctl is-active --quiet "$SERVICE"; then ok 'Boot service active'; else bad 'Boot service inactive/failed'; fi
echo 'MANUAL TEST REQUIRED: Esc, brightness, volume/media, hold/release Fn and F1-F12; webcam preview; reboot and sleep/wake.'
echo 'A passing diagnostic proves binding, not physical display, key delivery or resume reliability.'
exit "$failed"
