#!/usr/bin/env bash
# One-command launcher for macOS/Linux
cd "$(dirname "$0")/.." || exit 1
python3 auto.py "$@"
