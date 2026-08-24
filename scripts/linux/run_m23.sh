#!/usr/bin/env bash
set -euo pipefail

command=${1:-run-all}
shift || true

mkdir -p runs/m23_language_to_spec/logs
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
uv run python scripts/m23_language_to_spec.py "$command" "$@" 2>&1 \
  | tee "runs/m23_language_to_spec/logs/${command}.log"
