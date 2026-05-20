#!/usr/bin/env bash
set -euo pipefail

cd /home/zeio99/Alv
PYTHONPATH=src python scripts/submit_full.py "$@"

