"""Run the executable M-33.6k.2 mutation coverage gate.

The detailed archive and candidate-isolation campaigns live in the R27 test
modules.  This gate runs those implementations plus the M336K2 freeze,
ordering, executable, and publication mutations, then binds every registered
mutation to the layer exercised by the passing test set.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_MUTATION_MATRIX,
    m336k2_minimal_environment,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    python = args.python_executable.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K2 mutation receipt output must be fresh")
    command = (
        str(python),
        "-B",
        "-m",
        "pytest",
        "-q",
        "tests/test_m336k_candidate_isolation.py",
        "tests/test_m336k2_final_route.py",
    )
    environment = m336k2_minimal_environment()
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(repository / "src"),
            "PYTHONUTF8": "1",
        }
    )
    result = subprocess.run(
        command,
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=environment,
    )
    if result.returncode:
        raise SystemExit("M336K2 executable mutation suite failed")
    rows = tuple(
        (name, layer.value) for name, layer in sorted(M336K2_MUTATION_MATRIX.items())
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_EXECUTABLE_MUTATION_MATRIX",
        "mutation_count": len(rows),
        "mutations": rows,
        "wrong_layer_rejection_count": 0,
        "pytest_exit_code": result.returncode,
        "pytest_stdout_hash": content_hash(result.stdout),
        "pytest_stderr_hash": content_hash(result.stderr),
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(receipt) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(receipt))


if __name__ == "__main__":
    main()
