#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
export PATH="$HOME/.local/bin:$PATH"

mkdir -p runs/m231_fair_language_to_spec
log="runs/m231_fair_language_to_spec/remote_run.log"
exec > >(tee "$log") 2>&1

finish() {
  status=$?
  printf 'M231_EXIT:%s\n' "$status"
}
trap finish EXIT

uv sync
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
uv run pytest -q
uv run python scripts/m231_fair_bilingual_retest.py cuda-smoke
uv run python scripts/m231_fair_bilingual_retest.py run-all \
  --max-steps 20000 \
  --checks "Karina: ruff format --check; ruff check; pytest; CUDA smoke; official training/evaluation"
