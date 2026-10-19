#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
exec ssh -i "$ROOT/build-env/vm-key" -p 22261 \
    -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 \
    -o StrictHostKeyChecking=accept-new \
    -o "UserKnownHostsFile=$ROOT/build-env/known_hosts" builder@127.0.0.1 "$@"
