#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Shared constants are consumed by scripts sourcing this file.
# shellcheck disable=SC2034
NAME=macbook-t1-touchbar
# shellcheck disable=SC2034
VERSION=1.0.0
# shellcheck disable=SC2034
STATE=/var/lib/macbook-t1-ubuntu
# shellcheck disable=SC2034
SERVICE=macbook-t1-touchbar.service
export LC_ALL=C

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
linux_only() { [[ $(uname -s) == Linux ]] || die 'Run this script on Ubuntu, not macOS.'; }
root_only() { [[ $EUID == 0 ]] || die "Run with sudo: $0"; }
supported_kernel() { [[ $1 =~ ^7\.3\.0-[0-9]+-generic$ ]]; }
hardware_check() {
    [[ $(uname -m) == x86_64 ]] || die 'Only x86_64 is supported.'
    [[ $(cat /sys/class/dmi/id/product_name) == MacBookPro13,2 ]] || die 'This package supports MacBookPro13,2 only.'
    local d count=0
    for d in /sys/bus/usb/devices/*; do
        [[ -f $d/idVendor && -f $d/idProduct ]] || continue
        if [[ $(cat "$d/idVendor") == 05ac && $(cat "$d/idProduct") == 8600 ]]; then
            count=$((count + 1))
        fi
    done
    [[ $count == 1 ]] || die 'Expected one T1 USB 05ac:8600. See RECOVERY.md; no ACPI reset will be attempted.'
}
