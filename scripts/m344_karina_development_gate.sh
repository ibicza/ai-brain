#!/usr/bin/env bash
set -euo pipefail

project=${1:?project path required}
corpus_root=${2:?development corpus root required}
output_root=${3:?output root required}
jdk_root=${4:?JDK root required}

export JAVA_HOME="$jdk_root"
export PATH="$JAVA_HOME/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd "$project"

python="$project/.venv/bin/python"
"$python" -m pytest -q \
  tests/test_m344_oracle_free_java.py \
  tests/test_m343_semantic_proposal_gate.py \
  tests/test_m342_java_type_universe.py \
  > "$output_root/targeted-tests.log" 2>&1
"$python" scripts/m344_development_acceptance.py \
  --source-root "$corpus_root/m344-jackson-selected-probe" \
  --oracle-root "$corpus_root/m344-jackson-selected-oracle" \
  --output "$output_root/karina-core" \
  --platform karina \
  > "$output_root/core.log" 2>&1
"$python" scripts/m344_development_acceptance.py \
  --source-root "$corpus_root/m344-jdk21-generic-dev" \
  --oracle-root "$corpus_root/m344-jdk21-generic-oracle" \
  --output "$output_root/karina-jdk" \
  --platform karina \
  > "$output_root/jdk.log" 2>&1
touch "$output_root/completed"
