"""Language-independent semantic identities for held-out application tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from ai_brain.stage2.facts.canonical import content_hash


@dataclass(frozen=True)
class HeldoutTaskSemanticKey:
    operation_type: str
    target_record_id: str
    requested_unknown: str | None
    normalized_givens: tuple[tuple[str, str], ...]
    units: tuple[tuple[str, str], ...]
    conditions: tuple[str, ...]
    expected_answer_semantics: str
    semantic_hash: str


def make_semantic_key(
    *,
    operation_type: str,
    target_record_id: str,
    requested_unknown: str | None = None,
    givens=(),
    units=(),
    conditions=(),
    expected_answer_semantics: str,
) -> HeldoutTaskSemanticKey:
    value = HeldoutTaskSemanticKey(
        operation_type.strip().upper(),
        target_record_id.strip(),
        requested_unknown.strip() if requested_unknown else None,
        tuple(
            sorted(
                (str(key).strip(), str(item).strip())
                for key, item in dict(givens).items()
            )
        ),
        tuple(
            sorted(
                (str(key).strip(), str(item).strip())
                for key, item in dict(units).items()
            )
        ),
        tuple(sorted({str(item).strip() for item in conditions})),
        expected_answer_semantics.strip(),
        "",
    )
    return replace(value, semantic_hash=content_hash(_without_hash(value)))


def verify_semantic_uniqueness(
    values: tuple[HeldoutTaskSemanticKey, ...],
) -> dict[str, object]:
    hashes = tuple(item.semantic_hash for item in values)
    for item in values:
        if item.semantic_hash != content_hash(_without_hash(item)):
            raise ValueError("held-out semantic key hash mismatch")
    if len(set(hashes)) != len(hashes):
        raise ValueError("duplicate held-out task semantic meaning")
    clusters: dict[str, list[str]] = {}
    for item in values:
        cluster = content_hash(
            {
                "operation_type": item.operation_type,
                "target_record_id": item.target_record_id,
                "requested_unknown": item.requested_unknown,
                "units": item.units,
                "conditions": item.conditions,
                "expected_answer_semantics": item.expected_answer_semantics,
            }
        )
        clusters.setdefault(cluster, []).append(item.semantic_hash)
    near = tuple(
        tuple(items) for _, items in sorted(clusters.items()) if len(items) > 1
    )
    report = {
        "status": "UNIQUE",
        "semantic_key_count": len(values),
        "near_duplicate_cluster_count": len(near),
        "near_duplicate_clusters": near,
    }
    return {**report, "report_hash": content_hash(report)}


def _without_hash(value):
    row = asdict(value)
    row.pop("semantic_hash")
    return row
