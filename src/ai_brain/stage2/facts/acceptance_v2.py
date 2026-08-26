"""Deterministic M-26.1 factual-integrity acceptance battery."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage2.facts.memory import FactApprovalError, FactMemory
from ai_brain.stage2.facts.migration import (
    FactMemoryMigrationError,
    create_v1_compatibility_fixture,
    migrate_v1_to_v2,
)
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    Cardinality,
    ConflictResolutionKind,
    EvidenceLocationKind,
    EvidenceRelation,
    ExtractionMethod,
    ProposalSource,
    SourceKind,
    TemporalMode,
)
from ai_brain.stage2.facts.values import FactValue, FactValueKind
from ai_brain.stage2.facts.version import FACT_MEMORY_SCHEMA_VERSION


class AcceptanceClock:
    def __init__(self) -> None:
        self.value = "2026-01-01T00:00:00Z"

    def __call__(self) -> str:
        return self.value


def run_m261_acceptance(output_dir: Path) -> dict[str, Any]:
    root = output_dir.resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("M-26.1 acceptance target must be empty")
    root.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []

    def record(name: str, expected: Any, actual: Any) -> None:
        cases.append(
            {
                "name": name,
                "expected": expected,
                "actual": actual,
                "passed": expected == actual,
            }
        )

    memory, _ = _scenario(root / "01-one-support")
    _commit(memory, "one", 100)
    record("one_supporting_source", "SUPPORTED:1", _claim_summary(memory))

    memory, _ = _scenario(root / "02-two-support")
    rows = (_evidence(memory, "a", 100), _evidence(memory, "b", 100))
    _commit(memory, "two", 100, rows)
    record("two_independent_supports", "CORROBORATED:2", _claim_summary(memory))

    memory, _ = _scenario(root / "03-mirrored")
    rows = (
        _evidence(memory, "a", 100, family="mirror"),
        _evidence(memory, "b", 100, family="mirror"),
    )
    _commit(memory, "mirror", 100, rows)
    record("mirrored_support", "SUPPORTED:1", _claim_summary(memory))

    memory, _ = _scenario(root / "04-support-contradiction")
    rows = (
        _evidence(memory, "support", 100),
        _evidence(
            memory,
            "contradiction",
            100,
            relation=EvidenceRelation.CONTRADICTS,
        ),
    )
    _commit(memory, "mixed", 100, rows)
    answer = _query(memory).claims[0]
    record(
        "support_plus_contradiction",
        "SUPPORTED:CONTESTED:1:1",
        f"{answer.status}:{answer.evidence_conflict_state}:"
        f"{answer.independent_supporting_source_family_count}:"
        f"{answer.independent_contradicting_source_family_count}",
    )

    memory, _ = _scenario(root / "05-two-supports-contradiction")
    rows = (
        _evidence(memory, "support-a", 100),
        _evidence(memory, "support-b", 100),
        _evidence(
            memory,
            "contradiction",
            100,
            relation=EvidenceRelation.CONTRADICTS,
        ),
    )
    _commit(memory, "mixed-two", 100, rows)
    answer = _query(memory).claims[0]
    record(
        "two_supports_plus_contradiction",
        "2:1:CONTESTED",
        f"{answer.independent_supporting_source_family_count}:"
        f"{answer.independent_contradicting_source_family_count}:"
        f"{answer.evidence_conflict_state}",
    )

    memory, clock = _scenario(root / "06-support-retracted")
    support = _evidence(memory, "support", 100)
    contradiction = _evidence(
        memory,
        "contradiction",
        100,
        relation=EvidenceRelation.CONTRADICTS,
    )
    _commit(memory, "freshness", 100, (support, contradiction))
    clock.value = "2026-02-01T00:00:00Z"
    _retract_source(memory, support[0])
    record("supporting_source_retracted", "STALE_ONLY", _query(memory).answer_status)

    memory, clock = _scenario(root / "07-contradiction-retracted")
    support = _evidence(memory, "support", 100)
    contradiction = _evidence(
        memory,
        "contradiction",
        100,
        relation=EvidenceRelation.CONTRADICTS,
    )
    _commit(memory, "freshness", 100, (support, contradiction))
    clock.value = "2026-02-01T00:00:00Z"
    _retract_source(memory, contradiction[0])
    record(
        "contradicting_source_retracted",
        "EXACT_SINGLE:STALE",
        f"{_query(memory).answer_status}:"
        f"{_query(memory).claims[0].contradiction_freshness_state}",
    )

    memory, _ = _scenario(root / "08-model-only")
    model = _evidence(
        memory,
        "model",
        100,
        source_kind=SourceKind.MODEL_INFERENCE,
    )
    record("model_source_only", "REJECTED", _approval_result(memory, "model", (model,)))

    memory, _ = _scenario(root / "09-model-official")
    model = _evidence(
        memory,
        "model",
        100,
        source_kind=SourceKind.MODEL_INFERENCE,
    )
    official = _evidence(memory, "official", 100)
    record(
        "model_plus_official_support",
        "COMMITTED",
        _approval_result(
            memory,
            "model-official",
            (model, official),
            proposal_source=ProposalSource.MODEL_EXTRACTION,
        ),
    )

    memory, _ = _scenario(root / "10-blank-reviewer")
    record("blank_reviewer", "REJECTED", _bad_actor_result(memory, "", "HUMAN"))

    memory, _ = _scenario(root / "11-lowercase-model")
    record(
        "lowercase_model_actor_bypass",
        "REJECTED",
        _bad_actor_result(memory, "model", "HUMAN"),
    )

    memory, clock = _scenario(root / "12-future-claim")
    claim_id = _commit(memory, "future", 100)
    clock.value = "2026-02-01T00:00:00Z"
    memory.retract_claim(
        claim_id,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="future retraction",
    )
    historical = _query(memory, known_at="2026-01-15T00:00:00Z")
    record(
        "known_at_before_claim_retraction",
        "EXACT_SINGLE:NONE",
        f"{historical.answer_status}:{historical.claims[0].transaction_to or 'NONE'}",
    )

    memory, clock = _scenario(root / "13-future-source")
    support = _evidence(memory, "future-source", 100)
    _commit(memory, "future-source", 100, (support,))
    clock.value = "2026-02-01T00:00:00Z"
    _retract_source(memory, support[0])
    record(
        "known_at_before_source_retraction",
        "CURRENT",
        _query(memory, known_at="2026-01-15T00:00:00Z")
        .claims[0]
        .support_freshness_state,
    )

    memory, clock = _scenario(root / "14-before-resolution")
    first = _commit(memory, "first", 100)
    _commit(memory, "second", 200)
    clock.value = "2026-02-01T00:00:00Z"
    memory.retract_claim(
        first,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="resolve later",
    )
    record(
        "known_at_before_conflict_resolution",
        "CONFLICT",
        _query(memory, known_at="2026-01-15T00:00:00Z").answer_status,
    )

    memory, _ = _scenario(root / "15-unresolved")
    _commit(memory, "first", 100)
    _commit(memory, "second", 200)
    record("unresolved_conflict", "CONFLICT", _query(memory).answer_status)

    memory, clock = _scenario(root / "16-source-conflict")
    support = _evidence(memory, "first", 100)
    _commit(memory, "first", 100, (support,))
    _commit(memory, "second", 200)
    clock.value = "2026-02-01T00:00:00Z"
    _retract_source(memory, support[0])
    result = _query(memory)
    record(
        "source_retracted_conflict",
        "CONFLICT:SOURCE_RETRACTED_OR_UNAVAILABLE_SIDE",
        f"{result.answer_status}:"
        f"{'SOURCE_RETRACTED_OR_UNAVAILABLE_SIDE' if 'SOURCE_RETRACTED_OR_UNAVAILABLE_SIDE' in result.warnings else 'MISSING'}",
    )

    memory, clock = _scenario(root / "17-claim-resolution")
    first = _commit(memory, "first", 100)
    second = _commit(memory, "second", 200)
    clock.value = "2026-02-01T00:00:00Z"
    memory.retract_claim(
        first,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="explicit retraction",
    )
    record(
        "claim_retraction_resolution",
        f"EXACT_SINGLE:{second}:RESOLVED_CONFLICT_HISTORY",
        _resolved_summary(memory),
    )

    memory, clock = _scenario(root / "18-supersession")
    first = _commit(memory, "first", 100)
    second = _commit(memory, "second", 200)
    clock.value = "2026-02-01T00:00:00Z"
    memory.supersede_claim(
        first,
        second,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="explicit replacement",
    )
    record(
        "supersession_resolution",
        f"EXACT_SINGLE:{second}:RESOLVED_CONFLICT_HISTORY",
        _resolved_summary(memory),
    )

    memory, clock = _scenario(root / "19-manual")
    first_support = _evidence(memory, "first-support", 100)
    first_contradiction = _evidence(
        memory,
        "first-contradiction",
        100,
        relation=EvidenceRelation.CONTRADICTS,
    )
    first = _commit(memory, "first", 100, (first_support, first_contradiction))
    second = _commit(memory, "second", 200)
    conflict = memory.conflicts()[0]
    retained_evidence_id = memory.get_claim(second).supporting_evidence_ids[0]
    clock.value = "2026-02-01T00:00:00Z"
    memory.resolve_conflict(
        conflict.conflict_group_id,
        resolution_kind=ConflictResolutionKind.MANUAL_RESOLUTION,
        selected_claim_ids=(second,),
        remaining_claim_ids=(second,),
        evidence_ids=(retained_evidence_id, first_contradiction[1]),
        actor_identity="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason=f"manual evidence rejects {first}",
    )
    record(
        "manual_resolution",
        f"EXACT_SINGLE:{second}:RESOLVED_CONFLICT_HISTORY",
        _resolved_summary(memory),
    )

    memory, _ = _scenario(root / "20-overlap-allowed", overlap=True)
    _commit(memory, "first", 100)
    _commit(memory, "second", 200)
    record("overlap_allowed", "0", str(len(memory.conflicts())))

    memory, _ = _scenario(root / "21-overlap-forbidden")
    _commit(memory, "first", 100)
    _commit(memory, "second", 200)
    record("overlap_forbidden", "1", str(len(memory.conflicts())))

    memory, _ = _scenario(root / "22-details")
    _commit(memory, "details", 100)
    record(
        "include_evidence_true",
        "FULL:1",
        f"{_query(memory).provenance_detail_mode}:"
        f"{len(_query(memory).claims[0].supporting_source_citations)}",
    )
    compact = _query(memory, include_evidence=False)
    record(
        "include_evidence_false",
        "REFERENCES_ONLY:0:1",
        f"{compact.provenance_detail_mode}:"
        f"{len(compact.claims[0].supporting_source_citations)}:"
        f"{len(compact.claims[0].supporting_evidence_ids)}",
    )

    memory, clock = _scenario(root / "24-source-current")
    support = _evidence(memory, "source", 100)
    clock.value = "2026-02-01T00:00:00Z"
    _retract_source(memory, support[0])
    record("current_source_status", "RETRACTED", memory.get_source(support[0]).status)
    record(
        "source_status_as_of",
        "ACTIVE",
        memory.get_source_at(support[0], "2026-01-15T00:00:00Z").status,
    )

    memory, _ = _scenario(root / "26-duplicate-polarity")
    claim_id = _commit(memory, "first", 100)
    support = _evidence(memory, "second-support", 100)
    contradiction = _evidence(
        memory,
        "second-contradiction",
        100,
        relation=EvidenceRelation.CONTRADICTS,
    )
    _commit(memory, "second", 100, (support, contradiction))
    state = memory.get_claim_state(claim_id)
    record(
        "duplicate_mixed_polarity",
        "2:1:CONTESTED",
        f"{len(state.supporting_evidence_ids)}:"
        f"{len(state.contradicting_evidence_ids)}:"
        f"{state.evidence_conflict_state}",
    )

    source_v1 = root / "27-v1"
    target_current = root / "27-current"
    create_v1_compatibility_fixture(memory.root, source_v1)
    manifest = migrate_v1_to_v2(source_v1, target_current)
    record(
        "v1_to_current_migration",
        f"VALID:{FACT_MEMORY_SCHEMA_VERSION}:TRUE",
        f"{manifest['integrity']['status']}:{manifest['target_schema_version']}:"
        f"{str(manifest['source_unchanged']).upper()}",
    )

    corrupt_v1 = root / "28-v1-corrupt"
    corrupt_v2 = root / "28-v2-corrupt"
    create_v1_compatibility_fixture(memory.root, corrupt_v1)
    blob = next(item for item in (corrupt_v1 / "blobs").rglob("*") if item.is_file())
    blob.write_bytes(b"corrupt")
    try:
        migrate_v1_to_v2(corrupt_v1, corrupt_v2)
        rollback = "FAILED_OPEN"
    except FactMemoryMigrationError:
        rollback = "ROLLED_BACK" if not corrupt_v2.exists() else "PARTIAL_TARGET"
    record("migration_corrupt_source_rollback", "ROLLED_BACK", rollback)

    failures = [item for item in cases if not item["passed"]]
    result = {
        "status": "PASS" if not failures else "FAIL",
        "case_count": len(cases),
        "correct_count": len(cases) - len(failures),
        "accuracy": format((len(cases) - len(failures)) / len(cases), ".4f"),
        "cases": cases,
        "failures": failures,
    }
    (root / "acceptance_result.json").write_text(
        canonical_json(result) + "\n",
        encoding="utf-8",
    )
    return result


def _scenario(
    root: Path, *, overlap: bool = False
) -> tuple[FactMemory, AcceptanceClock]:
    clock = AcceptanceClock()
    memory = FactMemory.initialize(root, clock=clock)
    memory.add_entity(
        entity_id="city.alpha",
        entity_type="CITY",
        canonical_label_ru="Альфа",
        canonical_label_en="Alpha",
    )
    memory.add_predicate(
        predicate_id="population",
        canonical_name_ru="население",
        canonical_name_en="population",
        subject_entity_type="CITY",
        object_kind=FactValueKind.INTEGER,
        cardinality=Cardinality.SINGLE,
        temporal_mode=TemporalMode.VALID_INTERVAL,
        overlapping_intervals_permitted=overlap,
    )
    return memory, clock


def _evidence(
    memory: FactMemory,
    suffix: str,
    value: int,
    *,
    relation: EvidenceRelation = EvidenceRelation.SUPPORTS,
    source_kind: SourceKind = SourceKind.OFFICIAL_PRIMARY,
    family: str | None = None,
) -> tuple[str, str]:
    text = f"population={value}"
    source = memory.add_source(
        content=text,
        source_kind=source_kind,
        title=f"M-26.1 source {suffix}",
        source_family=family or f"family-{suffix}",
        trust_tier="T1",
        source_id=f"source.{suffix}",
        locator=f"acceptance:{suffix}",
    )
    evidence = memory.add_evidence(
        source_id=source.source_id,
        relation=relation,
        location_kind=EvidenceLocationKind.CHAR_SPAN,
        location={"start": 11, "end": len(text)},
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence=Decimal(1),
        reviewer="acceptance-reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
        approved=True,
        evidence_id=f"evidence.{suffix}",
    )
    return source.source_id, evidence.evidence_id


def _commit(
    memory: FactMemory,
    suffix: str,
    value: int,
    rows: tuple[tuple[str, str], ...] | None = None,
) -> str:
    evidence_rows = rows or (_evidence(memory, suffix, value),)
    proposal = memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create(FactValueKind.INTEGER, value),
        valid_from="2025-01-01",
        source_ids=tuple(item[0] for item in evidence_rows),
        evidence_ids=tuple(item[1] for item in evidence_rows),
        proposal_id=f"proposal.{suffix}",
    )
    memory.prepare_for_review(
        proposal.proposal_id,
        reviewer="acceptance-reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    approval = memory.approve_proposal(
        proposal.proposal_id,
        reviewer_identity="acceptance-approver",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    return memory.commit_proposal(proposal.proposal_id, approval.approval_id).claim_id


def _query(memory: FactMemory, **overrides):
    fields = {
        "subject": "city.alpha",
        "predicate_id": "population",
        "valid_at_value": "2025-06-01",
    }
    fields.update(overrides)
    return memory.query(memory.make_query(**fields))


def _claim_summary(memory: FactMemory) -> str:
    answer = _query(memory).claims[0]
    return f"{answer.status}:{answer.independent_supporting_source_family_count}"


def _retract_source(memory: FactMemory, source_id: str) -> None:
    memory.retract_source(
        source_id,
        actor="publisher",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="acceptance withdrawal",
    )


def _approval_result(
    memory: FactMemory,
    suffix: str,
    rows: tuple[tuple[str, str], ...],
    *,
    proposal_source: ProposalSource = ProposalSource.STRUCTURED_JSON,
) -> str:
    proposal = memory.receive_proposal(
        source=proposal_source,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create("INTEGER", 100),
        valid_from="2025-01-01",
        source_ids=tuple(item[0] for item in rows),
        evidence_ids=tuple(item[1] for item in rows),
        proposal_id=f"proposal.{suffix}",
    )
    memory.prepare_for_review(
        proposal.proposal_id,
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    try:
        approval = memory.approve_proposal(
            proposal.proposal_id,
            reviewer_identity="approver",
            reviewer_identity_type=ActorIdentityType.HUMAN,
        )
    except FactApprovalError:
        return "REJECTED"
    memory.commit_proposal(proposal.proposal_id, approval.approval_id)
    return "COMMITTED"


def _bad_actor_result(memory: FactMemory, identity: str, actor_type: str) -> str:
    row = _evidence(memory, "actor", 100)
    proposal = memory.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create("INTEGER", 100),
        valid_from="2025-01-01",
        source_ids=(row[0],),
        evidence_ids=(row[1],),
    )
    memory.prepare_for_review(
        proposal.proposal_id,
        reviewer="human",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    try:
        memory.approve_proposal(
            proposal.proposal_id,
            reviewer_identity=identity,
            reviewer_identity_type=actor_type,
        )
    except (FactApprovalError, ValueError):
        return "REJECTED"
    return "APPROVED"


def _resolved_summary(memory: FactMemory) -> str:
    result = _query(memory)
    warning = (
        "RESOLVED_CONFLICT_HISTORY"
        if "RESOLVED_CONFLICT_HISTORY" in result.warnings
        else "MISSING"
    )
    return f"{result.answer_status}:{result.selected_claim_ids[0]}:{warning}"
