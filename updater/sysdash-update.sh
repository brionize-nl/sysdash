#!/bin/bash
set -euo pipefail
exec /opt/sysdash/.venv/bin/python /opt/sysdash/updater/update.py
