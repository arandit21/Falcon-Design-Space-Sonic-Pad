#!/bin/sh
set -eu
PATCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$PATCH_DIR/install.py" "$@"
