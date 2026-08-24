#!/usr/bin/env bash
set -euo pipefail

command=${1:-run-all}
shift || true

mkdir -p runs/m223a_blackbox_validation/logs
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
uv run python scripts/m223a_evaluator_process.py "$command" "$@" 2>&1 | tee "runs/m223a_blackbox_validation/logs/${command}.log"
