#!/usr/bin/env bash
# Build-only verification, usable in an Ubuntu VM. Never loads modules.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
[[ $(uname -s) == Linux ]] || { echo 'Run in the Ubuntu build VM.' >&2; exit 1; }
KERNEL=${1:-$(uname -r)}
TMP=$(mktemp -d)
trap 'rm -rf -- "$TMP"' EXIT
cp "$ROOT"/driver/* "$TMP/"
make -C "$TMP" KVERSION="$KERNEL" CC=x86_64-linux-gnu-gcc W=1 -j2
make -C "$TMP" KVERSION="$KERNEL" CC=x86_64-linux-gnu-gcc C=2 CHECK="${SPARSE:-sparse}" 2>&1 | tee "$TMP/sparse.log"
grep -Eq 'CHECK[[:space:]]+apple-ibridge.c' "$TMP/sparse.log" || { echo 'sparse did not run' >&2; exit 1; }
grep -Eq 'CHECK[[:space:]]+apple-touchbar.c' "$TMP/sparse.log" || { echo 'sparse did not run' >&2; exit 1; }
for m in apple-ibridge apple-touchbar; do
    modinfo "$TMP/$m.ko"
    [[ $(modinfo -F vermagic "$TMP/$m.ko") == "$KERNEL "* ]]
done
(cd "$ROOT" && shellcheck -x ./*.sh lib/*.sh tests/*.sh tools/*.sh)
python3 "$ROOT/tests/test_transactions.py"
python3 "$ROOT/tests/test_hid_slots.py"
python3 "$ROOT/tests/test_acpi_guard.py"
