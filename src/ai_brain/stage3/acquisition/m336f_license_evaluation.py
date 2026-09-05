"""Platform-neutral SPDX evaluation evidence for M-33.6f."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336f_thresholds import ratio_string

M336F_LICENSE_SEMANTIC_CONTRACT = "m336f.independent-license-semantic.v1"
_TELEMETRY_FIELDS = frozenset(
    {
        "java_reference_compilation_seconds",
        "java_reference_spdx_match_seconds",
        "peak_java_reference_bytes",
        "production_spdx_match_seconds",
    }
)


@dataclass(frozen=True)
class M336FLicenseEvaluationSplit:
    semantic: dict
    telemetry_timings_seconds: tuple[tuple[str, str], ...]
    peak_java_reference_bytes: int


def split_m336f_license_evaluation(value: dict) -> M336FLicenseEvaluationSplit:
    """Turn the legacy mixed report into count-first semantic and telemetry roles."""

    required = {
        "document_count",
        "disagreement_count",
        "disagreement_review_required_count",
        "false_automatic_license_identity_count",
        "selected_root_unresolved_disagreement_count",
        "rows",
        "status",
        *_TELEMETRY_FIELDS,
    }
    if not required <= set(value):
        raise ValueError("independent SPDX evaluation is incomplete")
    rows = tuple(value["rows"])
    document_count = int(value["document_count"])
    disagreement_count = int(value["disagreement_count"])
    false_automatic = int(value["false_automatic_license_identity_count"])
    selected_disagreements = int(value["selected_root_unresolved_disagreement_count"])
    if (
        document_count <= 0
        or len(rows) != document_count
        or disagreement_count < 0
        or disagreement_count > document_count
        or int(value["disagreement_review_required_count"]) != disagreement_count
        or false_automatic < 0
        or selected_disagreements < 0
        or selected_disagreements > disagreement_count
    ):
        raise ValueError("independent SPDX count invariants failed")
    identities = []
    for row in rows:
        body = dict(row)
        claimed = body.pop("row_hash", None)
        if claimed is None or content_hash(body) != claimed:
            raise ValueError("independent SPDX row hash mismatch")
        identities.append(body.get("document_identity"))
    if None in identities or len(set(identities)) != len(identities):
        raise ValueError("independent SPDX document identities are not unique")
    semantic_body = {
        "schema_version": 2,
        "contract_role": M336F_LICENSE_SEMANTIC_CONTRACT,
        "document_count": document_count,
        "production_reference_agreement": ratio_string(
            document_count - disagreement_count, document_count
        ),
        "disagreement_count": disagreement_count,
        "disagreement_review_required_count": disagreement_count,
        "false_automatic_license_identity_count": false_automatic,
        "selected_root_unresolved_disagreement_count": selected_disagreements,
        "rows": rows,
        "status": (
            "PASS"
            if disagreement_count == 0
            and false_automatic == 0
            and selected_disagreements == 0
            else "FAIL"
        ),
    }
    semantic = {**semantic_body, "report_hash": content_hash(semantic_body)}
    timings = tuple(
        sorted(
            (
                (
                    "license_reference_compilation",
                    str(value["java_reference_compilation_seconds"]),
                ),
                (
                    "license_reference_evaluation",
                    str(value["java_reference_spdx_match_seconds"]),
                ),
                (
                    "license_production_evaluation",
                    str(value["production_spdx_match_seconds"]),
                ),
            )
        )
    )
    peak = int(value["peak_java_reference_bytes"])
    if peak <= 0:
        raise ValueError("independent SPDX telemetry has no peak-memory evidence")
    return M336FLicenseEvaluationSplit(semantic, timings, peak)
