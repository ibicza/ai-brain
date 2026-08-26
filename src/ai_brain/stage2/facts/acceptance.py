"""Deterministic human-readable M-26 acceptance corpus and batteries."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import canonical_json, validate_interval
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import (
    Cardinality,
    EvidenceLocationKind,
    EvidenceRelation,
    ExtractionMethod,
    ProposalSource,
    QueryStatus,
    SourceKind,
    SourceStatus,
    TemporalMode,
)
from ai_brain.stage2.facts.values import FactValue, FactValueKind


class AcceptanceClock:
    def __init__(self) -> None:
        self.value = "2026-01-01T00:00:00Z"

    def __call__(self) -> str:
        return self.value


def build_acceptance_pack(root: Path) -> tuple[FactMemory, dict[str, str]]:
    if root.exists() and any(root.iterdir()):
        raise ValueError("acceptance pack target must be empty")
    clock = AcceptanceClock()
    memory = FactMemory.initialize(root, clock=clock)
    for index in range(20):
        memory.add_entity(
            entity_id=f"place.{index:02d}",
            entity_type="PLACE",
            canonical_label_ru=f"Место {index:02d}",
            canonical_label_en=f"Place {index:02d}",
            aliases_ru=("Общее имя" if index in {18, 19} else f"П-{index:02d}",),
            aliases_en=("Shared Alias" if index in {18, 19} else f"P-{index:02d}",),
            provenance=({"kind": "M26_SYNTHETIC", "seed": 26},),
        )
    definitions = (
        (
            "population",
            FactValueKind.INTEGER,
            Cardinality.SINGLE,
            TemporalMode.VALID_INTERVAL,
        ),
        ("status", FactValueKind.ENUM, Cardinality.SINGLE, TemporalMode.VALID_INTERVAL),
        ("tags", FactValueKind.STRING, Cardinality.MULTI, TemporalMode.ATEMPORAL),
        ("launch_date", FactValueKind.DATE, Cardinality.MULTI, TemporalMode.EVENT),
        ("length", FactValueKind.QUANTITY, Cardinality.SINGLE, TemporalMode.ATEMPORAL),
        ("ratio", FactValueKind.DECIMAL, Cardinality.SINGLE, TemporalMode.ATEMPORAL),
        ("enabled", FactValueKind.BOOLEAN, Cardinality.SINGLE, TemporalMode.ATEMPORAL),
        (
            "owner",
            FactValueKind.ENTITY_REF,
            Cardinality.SINGLE,
            TemporalMode.VALID_INTERVAL,
        ),
        ("note", FactValueKind.STRING, Cardinality.SINGLE, TemporalMode.ATEMPORAL),
        ("founded", FactValueKind.DATE, Cardinality.SINGLE, TemporalMode.ATEMPORAL),
    )
    for predicate_id, kind, cardinality, temporal_mode in definitions:
        memory.add_predicate(
            predicate_id=predicate_id,
            canonical_name_ru=f"RU {predicate_id}",
            canonical_name_en=f"EN {predicate_id}",
            subject_entity_type="PLACE",
            object_kind=kind,
            cardinality=cardinality,
            temporal_mode=temporal_mode,
        )
    claims: dict[str, str] = {}
    claims["population_old"] = _commit(
        memory,
        "old",
        "place.00",
        "population",
        FactValue.create("INTEGER", 100),
        valid_from="2020-01-01",
        valid_to="2024-01-01",
    )
    claims["population_current"] = _commit(
        memory,
        "current",
        "place.00",
        "population",
        FactValue.create("INTEGER", 120),
        valid_from="2024-01-01",
    )
    claims["tag_a"] = _commit(
        memory, "tag-a", "place.01", "tags", FactValue.create("STRING", "red")
    )
    claims["tag_b"] = _commit(
        memory, "tag-b", "place.01", "tags", FactValue.create("STRING", "round")
    )
    claims["conflict_a"] = _commit(
        memory,
        "conflict-a",
        "place.02",
        "status",
        FactValue.create("ENUM", "OPEN"),
        valid_from="2025-01-01",
    )
    claims["conflict_b"] = _commit(
        memory,
        "conflict-b",
        "place.02",
        "status",
        FactValue.create("ENUM", "CLOSED"),
        valid_from="2025-01-01",
    )
    claims["duplicate"] = _commit(
        memory, "duplicate-a", "place.03", "note", FactValue.create("STRING", "same")
    )
    duplicate = _commit(
        memory, "duplicate-b", "place.03", "note", FactValue.create("STRING", "same")
    )
    if duplicate != claims["duplicate"]:
        raise AssertionError("duplicate claim did not merge")
    claims["quantity"] = _commit(
        memory,
        "quantity",
        "place.04",
        "length",
        FactValue.create("QUANTITY", "12.50", unit="m", original_unit="metres"),
    )
    claims["event"] = _commit(
        memory,
        "event",
        "place.05",
        "launch_date",
        FactValue.create("DATE", "2025-04-02"),
        valid_from="2025-04-02",
    )
    claims["retracted"] = _commit(
        memory, "retracted", "place.06", "note", FactValue.create("STRING", "withdraw")
    )
    memory.retract_claim(
        claims["retracted"], actor="acceptance", reason="synthetic correction"
    )
    claims["source_retracted"] = _commit(
        memory,
        "source-retracted",
        "place.07",
        "note",
        FactValue.create("STRING", "source"),
    )
    memory.retract_source(
        "source.source-retracted", actor="publisher", reason="synthetic withdrawal"
    )
    claims["source_unavailable"] = _commit(
        memory,
        "source-unavailable",
        "place.08",
        "note",
        FactValue.create("STRING", "offline"),
    )
    memory.set_source_status(
        "source.source-unavailable",
        status=SourceStatus.UNAVAILABLE,
        actor="operator",
        reason="synthetic outage",
    )
    claims["superseded_old"] = _commit(
        memory, "super-old", "place.09", "note", FactValue.create("STRING", "old")
    )
    claims["superseded_new"] = _commit(
        memory, "super-new", "place.09", "note", FactValue.create("STRING", "new")
    )
    memory.supersede_claim(
        claims["superseded_old"],
        claims["superseded_new"],
        actor="acceptance",
        reason="synthetic replacement",
    )
    for index in range(10, 18):
        claims[f"extra_{index}"] = _commit(
            memory,
            f"extra-{index}",
            f"place.{index:02d}",
            "founded",
            FactValue.create("DATE", f"20{index:02d}-01-01"),
        )
    return memory, claims


def run_acceptance(root: Path) -> dict[str, Any]:
    memory, claims = build_acceptance_pack(root)
    cases: list[tuple[str, QueryStatus, QueryStatus]] = []

    def check(name: str, expected: QueryStatus, **query_fields: Any) -> None:
        actual = memory.query(memory.make_query(**query_fields)).answer_status
        cases.append((name, expected, actual))

    check(
        "current_exact",
        QueryStatus.EXACT_SINGLE,
        subject="place.00",
        predicate_id="population",
        valid_at_value="2025-01-01",
    )
    check(
        "historical_valid_at",
        QueryStatus.EXACT_SINGLE,
        subject="place.00",
        predicate_id="population",
        valid_at_value="2022-01-01",
    )
    check(
        "bitemporal",
        QueryStatus.EXACT_SINGLE,
        subject="place.00",
        predicate_id="population",
        valid_at_value="2022-01-01",
        known_at="2026-01-01T00:00:00Z",
    )
    check("multi", QueryStatus.EXACT_MULTI, subject="place.01", predicate_id="tags")
    check(
        "corroborated",
        QueryStatus.EXACT_SINGLE,
        subject="place.03",
        predicate_id="note",
    )
    check("conflict", QueryStatus.CONFLICT, subject="place.02", predicate_id="status")
    check(
        "retracted", QueryStatus.RETRACTED_ONLY, subject="place.06", predicate_id="note"
    )
    check(
        "source_retracted",
        QueryStatus.STALE_ONLY,
        subject="place.07",
        predicate_id="note",
    )
    check(
        "source_unavailable",
        QueryStatus.STALE_ONLY,
        subject="place.08",
        predicate_id="note",
    )
    check(
        "supersession",
        QueryStatus.EXACT_SINGLE,
        subject="place.09",
        predicate_id="note",
    )
    check(
        "quantity", QueryStatus.EXACT_SINGLE, subject="place.04", predicate_id="length"
    )
    check(
        "event", QueryStatus.EXACT_MULTI, subject="place.05", predicate_id="launch_date"
    )
    check("no_fact", QueryStatus.NO_FACT, subject="place.10", predicate_id="population")
    check(
        "unknown_entity",
        QueryStatus.UNKNOWN_ENTITY,
        subject="missing",
        predicate_id="note",
    )
    check(
        "ambiguous_alias",
        QueryStatus.AMBIGUOUS_ENTITY,
        subject="Shared Alias",
        predicate_id="note",
    )
    check(
        "unknown_predicate",
        QueryStatus.UNKNOWN_PREDICATE,
        subject="place.00",
        predicate_id="missing",
    )
    try:
        FactValue.create(FactValueKind.QUANTITY, "1")
    except ValueError:
        cases.append(("invalid_unit", "REJECTED", "REJECTED"))
    else:
        cases.append(("invalid_unit", "REJECTED", "ACCEPTED"))
    try:
        validate_interval("2026-02-01", "2026-01-01")
    except ValueError:
        cases.append(("invalid_interval", "REJECTED", "REJECTED"))
    else:
        cases.append(("invalid_interval", "REJECTED", "ACCEPTED"))
    failures = [name for name, expected, actual in cases if expected != actual]
    result = {
        "status": "PASS" if not failures else "FAIL",
        "case_count": len(cases),
        "correct_count": len(cases) - len(failures),
        "accuracy": f"{(len(cases) - len(failures)) / len(cases):.4f}",
        "failures": failures,
        "cases": [
            {"name": name, "expected": expected, "actual": actual}
            for name, expected, actual in cases
        ],
        "claim_ids": claims,
        "memory_snapshot_hash": memory.database.snapshot_hash(),
        "integrity": memory.verify(),
    }
    (root / "acceptance_result.json").write_text(
        canonical_json(result) + "\n", encoding="utf-8"
    )
    return result


def _commit(
    memory: FactMemory,
    suffix: str,
    entity_id: str,
    predicate_id: str,
    value: FactValue,
    *,
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> str:
    source = memory.add_source(
        content={
            "subject": entity_id,
            "predicate": predicate_id,
            "value": value.to_dict(),
        },
        source_kind=SourceKind.LOCAL_DOCUMENT,
        title=f"M-26 acceptance source {suffix}",
        source_family=f"acceptance-family-{suffix}",
        trust_tier="SYNTHETIC_T1",
        locator=f"acceptance:{suffix}",
        source_id=f"source.{suffix}",
    )
    evidence = memory.add_evidence(
        source_id=source.source_id,
        relation=EvidenceRelation.SUPPORTS,
        location_kind=EvidenceLocationKind.JSON_POINTER,
        location={"pointer": "/value"},
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence=Decimal(1),
        reviewer="acceptance-generator",
        approved=True,
        evidence_id=f"evidence.{suffix}",
    )
    proposal = memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id=entity_id,
        predicate_id=predicate_id,
        object_value=value,
        valid_from=valid_from,
        valid_to=valid_to,
        source_ids=(source.source_id,),
        evidence_ids=(evidence.evidence_id,),
        proposal_id=f"proposal.{suffix}",
    )
    memory.prepare_for_review(proposal.proposal_id, reviewer="acceptance-reviewer")
    approval = memory.approve_proposal(
        proposal.proposal_id, reviewer_identity="acceptance-reviewer"
    )
    return memory.commit_proposal(proposal.proposal_id, approval.approval_id).claim_id
