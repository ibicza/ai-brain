#!/usr/bin/env bash
set -euo pipefail

cd "${AI_BRAIN_DIR:-$HOME/ai-brain}"

export PATH="$HOME/.local/bin:$PATH"
export UV_LINK_MODE=copy

mkdir -p runs/m192c_count_state_representation/logs

echo "host: $(hostname)"
echo "branch: $(git branch --show-current)"
echo "commit: $(git rev-parse HEAD)"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true

command="${1:-run-all}"
shift || true

uv run python scripts/m192c_count_state_representation.py "$command" "$@"
