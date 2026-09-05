#!/usr/bin/env bash
# Command 2 helper for macOS/Linux: mark a job as applied
cd "$(dirname "$0")/.." || exit 1
python3 -m jobhunt applied "$@"
