#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/lib/common.sh"
[[ $# == 0 ]] || die 'Usage: sudo ./uninstall-ubuntu.sh'
linux_only
root_only
[[ -d $STATE && ! -L $STATE ]] || { echo 'No owned installation to remove.'; exit 0; }
exec 9>/run/macbook-t1-install.lock
flock -n 9 || die 'Another install/uninstall is running.'
systemctl disable --now "$SERVICE" 2>/dev/null || true
# No ExecStop/unbind: loaded modules remain until a normal reboot.
if [[ -e $STATE/dkms-added ]] && dkms status -m "$NAME" -v "$VERSION" | grep -q .; then
    dkms remove -m "$NAME" -v "$VERSION" --all
fi
python3 "$STATE/deploy.py" restore || die "Later configuration edits preserved. See $STATE/files.json and RECOVERY.md."
if [[ -e $STATE/source-owned ]]; then rm -rf -- "/usr/src/$NAME-$VERSION"; fi
systemctl daemon-reload
udevadm control --reload-rules
depmod -a
if [[ -e $STATE/modules-installed ]]; then update-initramfs -u -k all; fi
archive="${STATE}-removed-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mv -- "$STATE" "$archive"
echo "Removed. Original configurations restored; logs/backups: $archive"
echo 'Reboot to finish; no live USB reset or driver unload was performed.'
