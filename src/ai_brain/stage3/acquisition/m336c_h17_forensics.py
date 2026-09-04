"""Read-only contract forensics for immutable historical H17 artifacts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.final_artifact_contract import (
    FINAL_ARTIFACT_CONTRACT_REGISTRY,
)

H17_SHA = "1a05ccfa0bad25a79e388dab7c6672fc308cb890"
E17_SHA = "1541805f9cd6c19ff9c372afeefbd41148217736"
H17_HISTORICAL_OUTCOME = "OUTCOME_C_BLOCKED"


def build_h17_contract_forensics(project: Path) -> dict:
    project = project.resolve(strict=True)
    paths = tuple(
        sorted(
            subprocess.run(
                (
                    "git",
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    H17_SHA,
                ),
                cwd=project,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
        )
    )
    rows = []
    unknown = 0
    unclassified = 0
    missing = 0
    unexpected = 0
    role_mismatches = 0
    for path in paths:
        raw = subprocess.run(
            ("git", "show", f"{H17_SHA}:{path}"),
            cwd=project,
            check=True,
            capture_output=True,
        ).stdout
        try:
            contract = FINAL_ARTIFACT_CONTRACT_REGISTRY.match(path)
            validation = FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(path, raw)
        except (ValueError, TypeError):
            unknown += 1
            rows.append(
                {
                    "path": path,
                    "artifact_type": None,
                    "role": None,
                    "schema": None,
                    "expected_fields": (),
                    "observed_fields": (),
                    "disclosure_fields": (),
                    "public_or_predeclared_fields": (),
                    "missing": (),
                    "extra": (),
                    "status": "FAIL",
                }
            )
            continue
        row = {
            "path": path,
            "artifact_type": contract.artifact_type,
            "role": contract.role.value,
            "schema": contract.media_type,
            "expected_fields": tuple(
                sorted({*contract.required_fields, *contract.optional_fields})
            ),
            "observed_fields": validation.observed_fields,
            "disclosure_fields": validation.disclosure_fields,
            "public_or_predeclared_fields": validation.public_or_predeclared_fields,
            "missing": validation.missing_fields,
            "extra": validation.unexpected_fields,
            "status": validation.status,
        }
        rows.append(row)
        unclassified += len(validation.unclassified_fields)
        missing += len(validation.missing_fields)
        unexpected += len(validation.unexpected_fields)
        role_mismatches += int(validation.role is not contract.role)
    blocked = json.loads(
        subprocess.run(
            (
                "git",
                "show",
                f"{H17_SHA}:evaluation/m336b_final_java/blocked_result.json",
            ),
            cwd=project,
            check=True,
            capture_output=True,
        ).stdout
    )
    if blocked["outcome"] != H17_HISTORICAL_OUTCOME:
        raise ValueError("immutable H17 historical outcome changed")
    prior_audit = json.loads(
        subprocess.run(
            (
                "git",
                "show",
                f"{E17_SHA}:runs/m336b_final_gate/role_disclosure_audit.json",
            ),
            cwd=project,
            check=True,
            capture_output=True,
        ).stdout
    )
    prior_audit_body = dict(prior_audit)
    prior_audit_hash = prior_audit_body.pop("report_hash")
    if content_hash(prior_audit_body) != prior_audit_hash:
        raise ValueError("immutable E17 H17 role audit hash mismatch")
    previous_extra = prior_audit["known_path_diagnostic_only_extra_claim_count"]
    body = {
        "schema_version": 1,
        "h17_sha": H17_SHA,
        "historical_outcome": blocked["outcome"],
        "path_count": len(paths),
        "paths": tuple(rows),
        "unknown_path_count": unknown,
        "unclassified_field_count": unclassified,
        "missing_mandatory_field_count": missing,
        "unexpected_field_count": unexpected,
        "role_mismatch_count": role_mismatches,
        "previous_role_audit_hash": prior_audit_hash,
        "previously_extra_protected_field_occurrence_count": previous_extra,
        "previously_extra_protected_field_classified_count": previous_extra
        if unknown == unclassified == unexpected == 0
        else 0,
        "status": "PASS"
        if unknown == unclassified == missing == unexpected == role_mismatches == 0
        else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}
