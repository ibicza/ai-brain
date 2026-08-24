#!/usr/bin/env bash
set -euo pipefail

cd "${AI_BRAIN_DIR:-$HOME/ai-brain}"
export PATH="$HOME/.local/bin:$PATH"
export UV_LINK_MODE=copy

mkdir -p runs/m222_cegis_rule_acquisition/logs

echo "host=$(hostname)"
echo "branch=$(git branch --show-current 2>/dev/null || true)"
echo "commit=$(git rev-parse --short HEAD 2>/dev/null || true)"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
fi

command="${1:-run-all}"
shift || true

uv run python scripts/m222_acquisition_integrity_cegis.py "$command" "$@"
