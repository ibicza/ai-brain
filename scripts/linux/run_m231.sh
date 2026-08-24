#!/usr/bin/env bash
set -euo pipefail

command_name="${1:-run-all}"
shift || true

uv run python scripts/m231_fair_bilingual_retest.py "$command_name" "$@"
