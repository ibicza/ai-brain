"""Export public-safe metadata for an exact M336K5 Karina capsule."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    compute_m336j_project_source_identity,
    load_private_execution_capsule,
    verify_execution_capsule,
)
from ai_brain.stage3.acquisition.m336k5_startup import startup_receipt_from_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-capsule", type=Path, required=True)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    args = parser.parse_args()
    capsule = load_private_execution_capsule(args.private_capsule)
    receipt, python, dependencies, audit = verify_execution_capsule(
        args.private_capsule
    )
    project_source_identity = compute_m336j_project_source_identity(
        Path(str(capsule.repository_checkout)), Path(str(capsule.git_executable))
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K5_KARINA_CAPSULE_METADATA",
        "public_execution_capsule_receipt": asdict(receipt),
        "python_environment_identity": asdict(python),
        "executable_dependency_manifest": asdict(dependencies),
        "dependency_audit": asdict(audit),
        "project_source_identity": project_source_identity,
        "startup_receipt_hash": startup_receipt_from_path(
            args.startup_receipt
        ).receipt_hash,
        "status": "PASS",
    }
    print(canonical_json({**body, "metadata_hash": content_hash(body)}))


if __name__ == "__main__":
    main()
