#!/usr/bin/env bash
# Quick launcher for Chronicle Traffic Bot GUI Dashboard
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/automation/gui.py" "$@"
