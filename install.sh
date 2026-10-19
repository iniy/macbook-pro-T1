#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$ROOT/lib/one_shot.py" "$@"
