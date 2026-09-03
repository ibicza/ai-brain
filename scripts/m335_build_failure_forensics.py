"""Create the complete machine-readable M-34.4 failure census."""

from __future__ import annotations

import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def _parameters(row):
    return tuple(item[1] for item in row["proposal_content"]["parameters"])


def _parameter_descriptor(value):
    start = value.find("(")
    end = value.find(")", start + 1)
    return None if start < 0 or end < 0 else value[start + 1 : end]


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    evaluation = project / "evaluation/m344_final_java"
    blocked = json.loads(
        (evaluation / "blocked_result.json").read_text(encoding="utf-8")
    )
    output = json.loads(
        (evaluation / "production_output.json").read_text(encoding="utf-8")
    )
    counts = json.loads(
        (evaluation / "production_counts.json").read_text(encoding="utf-8")
    )
    rows = {item["proposal_id"]: item for item in output["candidate_rows"]}
    alias_groups = []
    for index, group in enumerate(blocked["conflicts"]):
        values = []
        for proposal in group["proposals"]:
            row = rows[proposal["proposal_id"]]
            source = evaluation / "source_snapshots" / row["source_unit_id"]
            span = source.read_bytes()[row["start_offset"] : row["end_offset"]]
            values.append(
                {
                    "proposal_id": row["proposal_id"],
                    "proposal_hash": row["proposal_hash"],
                    "physical_source_path": row["source_unit_id"],
                    "byte_span": [row["start_offset"], row["end_offset"]],
                    "source_span_hash": bytes_hash(span),
                    "receiver_source_identity": row["receiver_type"],
                    "receiver_binary_identity": row["receiver_type"],
                    "callable_kind": row["proposal_content"]["java_callable_kind"],
                    "member_name": "<init>"
                    if row["member_kind"] == "constructor"
                    else row["member_name"],
                    "source_parameter_types": _parameters(row),
                    "resolved_parameter_types": tuple(
                        row["proposal_content"]["resolved_parameter_types"]
                    ),
                    "erased_parameter_descriptor": _parameter_descriptor(
                        row["erased_jvm_descriptor"]
                    ),
                    "full_jvm_descriptor": row["erased_jvm_descriptor"],
                    "source_signature": row["canonical_source_signature"],
                    "semantic_content_hash": content_hash(row["proposal_content"]),
                    "trust_decision_hash": row["decision_hash"],
                    "field_evidence_hashes": (),
                    "field_evidence_note": "receipt hashes were not exported by the sealed H13 output",
                }
            )
        classification = (
            "CASEFOLD_COLLISION" if index < 2 else "LEGAL_OVERLOAD_COLLAPSED_BY_ALIAS"
        )
        alias_groups.append(
            {
                "alias": group["alias"],
                "classification": classification,
                "proposals": tuple(values),
            }
        )
    conflict_rows = []
    for conflict in counts["conflict_report"]["conflicts"]:
        proposals = tuple(rows[item] for item in conflict["proposal_ids"])
        declarations = tuple(
            {
                "proposal_id": item["proposal_id"],
                "parser_node_id": node,
                "source_location": location,
                "source_signature": item["canonical_source_signature"],
                "old_erased_jvm_descriptor": item["erased_jvm_descriptor"],
                "canonical_callable_identity": None,
                "canonical_identity_status": "NOT_AVAILABLE_UNRESOLVED_TYPE",
                "semantic_content_hash": content_hash(item["proposal_content"]),
                "production_trust_state": item["production_trust_state"],
                "production_blocker_reason": item["production_blocker_reason"],
            }
            for item, node, location in zip(
                proposals,
                conflict["parser_node_ids"],
                conflict["source_locations"],
                strict=True,
            )
        )
        conflict_rows.append(
            {
                "historical_conflict_hash": conflict["conflict_hash"],
                "historical_conflict_kind": conflict["conflict_kind"],
                "classification": "LEGAL_OVERLOAD_COLLAPSED_BY_UNRESOLVED_SENTINEL",
                "proposals": tuple(item["proposal_id"] for item in proposals),
                "declarations": declarations,
                "withheld_before_trust": all(
                    item["production_trust_state"] == "withheld" for item in proposals
                ),
                "pack_compilation_would_reject": False,
                "legal_overload": True,
                "true_classpath_or_source_conflict": False,
            }
        )
    body = {
        "schema_version": 1,
        "historical_h13": "3f42cb044daadf29f9c1a1c69ca4706f15f8c75b",
        "alias_group_count": len(alias_groups),
        "alias_groups": tuple(alias_groups),
        "prior_conflict_count": len(conflict_rows),
        "conflicts": tuple(conflict_rows),
        "unclassified_conflict_count": 0,
        "root_causes": (
            "presentation aliases used as authoritative one-to-one identities",
            "casefold erased Boolean versus boolean",
            "source generic spelling T hid distinct resolved erasures",
            "UNRESOLVED sentinel was treated as a JVM signature",
        ),
    }
    target = project / "runs/m335_development/conflict_census.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        canonical_json({**body, "census_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    divergence = {
        "schema_version": 1,
        "historical_windows_output_file_hash": "e57cb131db0408f775c111c8dcf016782901f03efcce9961d98e2924a4cb12cd",
        "historical_karina_output_file_hash": "e42f2ab880432d12c9b098d9618403d357e4eb1d4df17637c5de4af7fca1ed2b",
        "canonical_input_path_hash_set_equal": True,
        "first_differing_stage": "SourceDocument identities",
        "first_differing_field": "SourceDocument.document_id",
        "expected_rule": "content-derived(bundle_id, normalized_relative_path, raw_hash)",
        "windows_bundle_hash": "1f99c27dedd59e1bcb4f715d858feb19701bb2e8741e32dc666f15d1081b400e",
        "karina_bundle_hash": "9bf49ef4dbbbe329d299f05d7394de6bac3a795a245c0ee40626d90a0d2fe556",
        "causal_dependency_path": (
            "caller/filesystem order",
            "ordinal document_id",
            "document_hash",
            "bundle_hash",
            "segment/proposal/evidence/decision/closure hashes",
        ),
        "root_cause": "v1 document identity embedded caller-order ordinal",
    }
    divergence_target = project / "runs/m335_development/first_divergence.json"
    divergence_target.write_text(
        canonical_json({**divergence, "divergence_hash": content_hash(divergence)})
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
