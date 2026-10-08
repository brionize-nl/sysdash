#!/usr/bin/env bash
set -euo pipefail
# Explicit local administrator operation; never delegated via passwordless sudo.
exec python3 "$(dirname "$0")/setup.py" --mode advanced "$@"
