#!/usr/bin/env bash
# Unified test, quality, type & coverage runner for Linux/macOS
set -e
cd "$(dirname "$0")/.."
python3 run_tests.py "$@"

