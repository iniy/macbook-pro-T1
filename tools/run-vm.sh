#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
ENV="$ROOT/build-env"
export QEMU_FRAMEWORK="$ENV/UTM.app/Contents/Frameworks/qemu-x86_64-softmmu.framework/qemu-x86_64-softmmu"
exec "$ENV/qemu-launch" \
    -L "$ENV/UTM.app/Contents/Resources/qemu" \
    -machine q35,accel=hvf -cpu host -smp 2 -m 2048 \
    -drive "file=$ENV/vm.qcow2,if=virtio,format=qcow2" \
    -drive "file=$ENV/seed.iso,media=cdrom,readonly=on" \
    -netdev user,id=net0,hostfwd=tcp:127.0.0.1:22261-:22 \
    -device virtio-net-pci,netdev=net0 \
    -display none -monitor none -serial "file:$ENV/console.log" \
    -pidfile "$ENV/qemu.pid"
