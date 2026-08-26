from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactApprovalError, FactMemory
from ai_brain.stage2.facts.migration import (
    FactMemoryMigrationError,
    create_v1_compatibility_fixture,
    migrate_v1_to_v2,
)
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    Cardinality,
    ClaimStatus,
    ConflictResolutionKind,
    ConflictResolutionStatus,
    EvidenceConflictState,
    EvidenceLocationKind,
    EvidenceRelation,
    ExtractionMethod,
    ProposalSource,
    ProvenanceDetailMode,
    QueryStatus,
    SourceKind,
    SourceStatus,
    TemporalMode,
)
from ai_brain.stage2.facts.persistence import FactMemoryIntegrityError
from ai_brain.stage2.facts.sources import SourceIntegrityError
from ai_brain.stage2.facts.values import FactValue, FactValueKind


class Clock:
    def __init__(self, value: str = "2026-01-01T00:00:00Z") -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


@pytest.fixture
def memory(tmp_path: Path) -> tuple[FactMemory, Clock]:
    clock = Clock()
    result = FactMemory.initialize(tmp_path / "facts", clock=clock)
    result.add_entity(
        entity_id="city.alpha",
        entity_type="CITY",
        canonical_label_ru="Альфа",
        canonical_label_en="Alpha",
    )
    result.add_predicate(
        predicate_id="population",
        canonical_name_ru="население",
        canonical_name_en="population",
        subject_entity_type="CITY",
        object_kind=FactValueKind.INTEGER,
        cardinality=Cardinality.SINGLE,
        temporal_mode=TemporalMode.VALID_INTERVAL,
    )
    return result, clock


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
        title=f"Source {suffix}",
        source_family=family or f"family-{suffix}",
        trust_tier="T1",
        source_id=f"source.{suffix}",
        locator=f"local:{suffix}",
    )
    evidence = memory.add_evidence(
        source_id=source.source_id,
        relation=relation,
        location_kind=EvidenceLocationKind.CHAR_SPAN,
        location={"start": 11, "end": len(text)},
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extraction_confidence=Decimal(1),
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
        approved=True,
        evidence_id=f"evidence.{suffix}",
    )
    return source.source_id, evidence.evidence_id


def _commit(
    memory: FactMemory,
    suffix: str,
    value: int,
    evidence: tuple[tuple[str, str], ...] | None = None,
    *,
    proposal_source: ProposalSource = ProposalSource.STRUCTURED_JSON,
    valid_from: str = "2025-01-01",
) -> str:
    rows = evidence or (_evidence(memory, suffix, value),)
    proposal = memory.receive_proposal(
        source=proposal_source,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create(FactValueKind.INTEGER, value),
        valid_from=valid_from,
        source_ids=tuple(item[0] for item in rows),
        evidence_ids=tuple(item[1] for item in rows),
        proposal_id=f"proposal.{suffix}",
    )
    memory.prepare_for_review(
        proposal.proposal_id,
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    approval = memory.approve_proposal(
        proposal.proposal_id,
        reviewer_identity="approver",
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


def test_support_and_contradiction_are_separate(memory) -> None:
    facts, _ = memory
    support = _evidence(facts, "support", 100)
    contradiction = _evidence(
        facts,
        "contradiction",
        100,
        relation=EvidenceRelation.CONTRADICTS,
    )
    claim_id = _commit(facts, "mixed", 100, (support, contradiction))
    claim = facts.get_claim(claim_id)
    answer = _query(facts).claims[0]
    assert claim.status == ClaimStatus.SUPPORTED
    assert claim.source_family_support_set == ("family-support",)
    assert claim.source_family_contradiction_set == ("family-contradiction",)
    assert answer.independent_supporting_source_family_count == 1
    assert answer.independent_contradicting_source_family_count == 1
    assert answer.evidence_conflict_state == EvidenceConflictState.CONTESTED
    assert "CONTRADICTING_EVIDENCE_PRESENT" in _query(facts).warnings


def test_duplicate_merge_preserves_mixed_polarity(memory) -> None:
    facts, _ = memory
    claim_id = _commit(facts, "duplicate-first", 100)
    support = _evidence(facts, "duplicate-support", 100)
    contradiction = _evidence(
        facts,
        "duplicate-contradiction",
        100,
        relation=EvidenceRelation.CONTRADICTS,
    )
    assert _commit(facts, "duplicate-second", 100, (support, contradiction)) == claim_id
    state = facts.get_claim_state(claim_id)
    assert len(state.supporting_evidence_ids) == 2
    assert len(state.contradicting_evidence_ids) == 1
    assert state.status == ClaimStatus.CORROBORATED
    assert state.evidence_conflict_state == EvidenceConflictState.CONTESTED


def test_contradiction_freshness_cannot_mask_stale_support(memory) -> None:
    facts, clock = memory
    support = _evidence(facts, "fresh-support", 100)
    contradiction = _evidence(
        facts,
        "fresh-contradiction",
        100,
        relation=EvidenceRelation.CONTRADICTS,
    )
    _commit(facts, "freshness", 100, (support, contradiction))
    clock.value = "2026-02-01T00:00:00Z"
    facts.retract_source(
        support[0],
        actor="publisher",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="withdrawn",
    )
    assert _query(facts).answer_status == QueryStatus.STALE_ONLY
    detailed = _query(facts, include_retracted=True)
    assert detailed.claims[0].support_freshness_state == "STALE"
    assert detailed.claims[0].contradiction_freshness_state == "CURRENT"


def test_retracted_contradiction_leaves_support_active(memory) -> None:
    facts, clock = memory
    support = _evidence(facts, "active-support", 100)
    contradiction = _evidence(
        facts,
        "stale-contradiction",
        100,
        relation=EvidenceRelation.CONTRADICTS,
    )
    _commit(facts, "contradiction-retracted", 100, (support, contradiction))
    clock.value = "2026-02-01T00:00:00Z"
    facts.retract_source(
        contradiction[0],
        actor="publisher",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="withdrawn contradiction",
    )
    result = _query(facts)
    assert result.answer_status == QueryStatus.EXACT_SINGLE
    assert result.claims[0].contradiction_freshness_state == "STALE"
    assert "CONTRADICTING_EVIDENCE_PRESENT" in result.warnings


@pytest.mark.parametrize(
    ("identity", "actor_type"),
    [
        ("", ActorIdentityType.HUMAN),
        ("   ", ActorIdentityType.HUMAN),
        ("model", ActorIdentityType.HUMAN),
        ("Model", ActorIdentityType.HUMAN),
        ("reviewer", ActorIdentityType.MODEL),
    ],
)
def test_untrusted_approval_actor_matrix(memory, identity, actor_type) -> None:
    facts, _ = memory
    rows = (_evidence(facts, f"actor-{len(facts.database.audit_replay())}", 100),)
    proposal = facts.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create("INTEGER", 100),
        valid_from="2025-01-01",
        source_ids=(rows[0][0],),
        evidence_ids=(rows[0][1],),
    )
    facts.prepare_for_review(
        proposal.proposal_id,
        reviewer="human",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    with pytest.raises(FactApprovalError):
        facts.approve_proposal(
            proposal.proposal_id,
            reviewer_identity=identity,
            reviewer_identity_type=actor_type,
        )


def test_actor_type_case_trick_is_not_parsed(memory) -> None:
    facts, _ = memory
    with pytest.raises(FactApprovalError):
        facts.retract_source(
            "missing",
            actor="reviewer",
            actor_identity_type="model",
            reason="case trick",
        )
    assert facts.database.audit_replay()[-1]["event_type"] == "FACT_ACTOR_REJECTED"


def test_model_inference_only_cannot_be_trusted(memory) -> None:
    facts, _ = memory
    model = _evidence(
        facts,
        "model-only",
        100,
        source_kind=SourceKind.MODEL_INFERENCE,
    )
    proposal = facts.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create("INTEGER", 100),
        valid_from="2025-01-01",
        source_ids=(model[0],),
        evidence_ids=(model[1],),
    )
    facts.prepare_for_review(
        proposal.proposal_id,
        reviewer="human",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    with pytest.raises(FactApprovalError, match="non-model support"):
        facts.approve_proposal(
            proposal.proposal_id,
            reviewer_identity="human",
            reviewer_identity_type=ActorIdentityType.HUMAN,
        )


def test_model_origin_with_independent_official_support_is_allowed(memory) -> None:
    facts, _ = memory
    model = _evidence(
        facts,
        "model-plus-model",
        100,
        source_kind=SourceKind.MODEL_INFERENCE,
    )
    official = _evidence(facts, "model-plus-official", 100)
    claim_id = _commit(
        facts,
        "model-plus",
        100,
        (model, official),
        proposal_source=ProposalSource.MODEL_EXTRACTION,
    )
    assert facts.get_claim(claim_id).status == ClaimStatus.SUPPORTED


def test_historical_query_hides_future_claim_and_source_events(memory) -> None:
    facts, clock = memory
    claim_id = _commit(facts, "future", 100)
    source_id = (
        facts.get_claim(claim_id)
        .supporting_evidence_ids[0]
        .replace("evidence", "source")
    )
    clock.value = "2026-02-01T00:00:00Z"
    facts.retract_claim(
        claim_id,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="future correction",
    )
    facts.retract_source(
        source_id,
        actor="publisher",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="future source event",
    )
    historical = _query(facts, known_at="2026-01-15T00:00:00Z")
    assert historical.answer_status == QueryStatus.EXACT_SINGLE
    assert historical.claims[0].transaction_to is None
    assert historical.claims[0].support_freshness_state == "CURRENT"
    assert not any("RETRACT" in warning for warning in historical.warnings)


def test_source_current_and_as_of_apis_are_explicit(memory) -> None:
    facts, clock = memory
    _, source_id = _evidence(facts, "source-api", 100)
    source_id = source_id.replace("evidence", "source")
    clock.value = "2026-02-01T00:00:00Z"
    facts.retract_source(
        source_id,
        actor="publisher",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="withdrawn",
    )
    assert facts.get_source_record(source_id).status == SourceStatus.ACTIVE
    assert facts.get_source(source_id).status == SourceStatus.RETRACTED
    assert (
        facts.get_source_at(source_id, "2026-01-15T00:00:00Z").status
        == SourceStatus.ACTIVE
    )


def test_conflict_resolution_is_bitemporal(memory) -> None:
    facts, clock = memory
    first = _commit(facts, "conflict-first", 100)
    second = _commit(facts, "conflict-second", 200)
    clock.value = "2026-02-01T00:00:00Z"
    facts.retract_claim(
        first,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="explicitly withdrawn",
    )
    historical = _query(facts, known_at="2026-01-15T00:00:00Z")
    current = _query(facts)
    assert historical.answer_status == QueryStatus.CONFLICT
    assert current.answer_status == QueryStatus.EXACT_SINGLE
    assert current.selected_claim_ids == (second,)
    assert "RESOLVED_CONFLICT_HISTORY" in current.warnings
    assert facts.conflicts_at("2026-01-15T00:00:00Z")[0].resolution_status == (
        ConflictResolutionStatus.UNRESOLVED
    )
    assert facts.conflicts(unresolved_only=False)[0].resolution_status == (
        ConflictResolutionStatus.RESOLVED
    )


def test_source_retraction_does_not_resolve_conflict(memory) -> None:
    facts, clock = memory
    first_support = _evidence(facts, "source-conflict-first", 100)
    first = _commit(facts, "source-conflict-a", 100, (first_support,))
    second = _commit(facts, "source-conflict-b", 200)
    clock.value = "2026-02-01T00:00:00Z"
    facts.retract_source(
        first_support[0],
        actor="publisher",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="withdrawn",
    )
    result = _query(facts)
    assert result.answer_status == QueryStatus.CONFLICT
    assert set(result.selected_claim_ids) == {first, second}
    assert "SOURCE_RETRACTED_OR_UNAVAILABLE_SIDE" in result.warnings


def test_manual_resolution_requires_evidence(memory) -> None:
    facts, _ = memory
    _commit(facts, "manual-first", 100)
    second = _commit(facts, "manual-second", 200)
    conflict = facts.conflicts()[0]
    with pytest.raises(FactApprovalError, match="requires evidence"):
        facts.resolve_conflict(
            conflict.conflict_group_id,
            resolution_kind=ConflictResolutionKind.MANUAL_RESOLUTION,
            selected_claim_ids=(second,),
            remaining_claim_ids=(second,),
            evidence_ids=(),
            actor_identity="reviewer",
            actor_identity_type=ActorIdentityType.HUMAN,
            reason="unsupported winner",
        )


def test_overlapping_intervals_permitted_is_enforced(tmp_path: Path) -> None:
    clock = Clock()
    facts = FactMemory.initialize(tmp_path / "overlap", clock=clock)
    facts.add_entity(
        entity_id="city.alpha",
        entity_type="CITY",
        canonical_label_ru="Альфа",
        canonical_label_en="Alpha",
    )
    facts.add_predicate(
        predicate_id="population",
        canonical_name_ru="население",
        canonical_name_en="population",
        subject_entity_type="CITY",
        object_kind=FactValueKind.INTEGER,
        cardinality=Cardinality.SINGLE,
        temporal_mode=TemporalMode.VALID_INTERVAL,
        overlapping_intervals_permitted=True,
    )
    _commit(facts, "allowed-first", 100)
    _commit(facts, "allowed-second", 200)
    assert not facts.conflicts()
    assert _query(facts).answer_status == QueryStatus.EXACT_MULTI


def test_evidence_detail_omission_retains_references(memory) -> None:
    facts, _ = memory
    _commit(facts, "details", 100)
    full = _query(facts, include_evidence=True)
    compact = _query(facts, include_evidence=False)
    assert full.claims[0].supporting_source_citations
    assert not compact.claims[0].supporting_source_citations
    assert compact.claims[0].supporting_evidence_ids
    assert compact.claims[0].supporting_evidence_hashes
    assert compact.claims[0].supporting_source_ids
    assert compact.claims[0].supporting_source_hashes
    assert compact.provenance_detail_mode == ProvenanceDetailMode.REFERENCES_ONLY
    assert "EVIDENCE_DETAILS_OMITTED" in compact.warnings


def test_answer_receipt_binds_known_at_and_version(memory) -> None:
    facts, _ = memory
    _commit(facts, "receipt", 100)
    bundle = _query(facts, known_at="2026-01-15T00:00:00Z")
    with pytest.raises(FactMemoryIntegrityError, match="hash mismatch"):
        facts.replay_answer(replace(bundle, known_at="2026-01-16T00:00:00Z"))
    with pytest.raises(FactMemoryIntegrityError, match="schema-v2"):
        facts.replay_answer(replace(bundle, answer_schema_version=1))


def test_conflict_resolution_hash_tamper_fails_closed(memory) -> None:
    facts, _ = memory
    first = _commit(facts, "tamper-first", 100)
    _commit(facts, "tamper-second", 200)
    facts.retract_claim(
        first,
        actor="reviewer",
        actor_identity_type=ActorIdentityType.HUMAN,
        reason="withdrawn",
    )
    with facts.database.connect() as connection:
        row = connection.execute(
            "SELECT event_id, payload_json FROM conflict_resolution_events WHERE new_status = 'RESOLVED'"
        ).fetchone()
        payload = json.loads(row[1])
        payload["reason"] = "tampered"
        connection.execute(
            "UPDATE conflict_resolution_events SET payload_json = ? WHERE event_id = ?",
            (json.dumps(payload), row[0]),
        )
        connection.commit()
    with pytest.raises(FactMemoryIntegrityError, match="row hash mismatch"):
        facts.verify()


def test_v1_migration_is_non_destructive(memory, tmp_path: Path) -> None:
    facts, _ = memory
    _commit(facts, "migration", 100)
    _query(facts)
    source = tmp_path / "v1"
    target = tmp_path / "v2"
    fixture = create_v1_compatibility_fixture(facts.root, source)
    source_hash = fixture["fixture_tree_sha256"]
    manifest = migrate_v1_to_v2(source, target)
    assert manifest["source_unchanged"] is True
    assert manifest["source_root_hash"] == source_hash
    assert manifest["evidence_polarity_counts"]["SUPPORTS"] == 1
    assert FactMemory.open(target).verify()["status"] == "VALID"
    with pytest.raises(FactMemoryIntegrityError, match="explicit migration"):
        FactMemory.open(source)


def test_migration_corrupt_blob_rolls_back(memory, tmp_path: Path) -> None:
    facts, _ = memory
    _commit(facts, "migration-corrupt", 100)
    source = tmp_path / "v1-corrupt"
    target = tmp_path / "v2-corrupt"
    create_v1_compatibility_fixture(facts.root, source)
    blob = next(item for item in (source / "blobs").rglob("*") if item.is_file())
    blob.write_bytes(b"corrupt")
    with pytest.raises(FactMemoryMigrationError, match="source was left untouched"):
        migrate_v1_to_v2(source, target)
    assert not target.exists()


def test_migration_tampered_record_rolls_back_without_touching_source(
    memory, tmp_path: Path
) -> None:
    facts, _ = memory
    _commit(facts, "migration-row", 100)
    source = tmp_path / "v1-row-corrupt"
    target = tmp_path / "v2-row-corrupt"
    create_v1_compatibility_fixture(facts.root, source)
    database_path = source / "fact_memory.sqlite3"
    with sqlite3.connect(database_path) as connection:
        payload = json.loads(
            connection.execute("SELECT payload_json FROM entities LIMIT 1").fetchone()[
                0
            ]
        )
        payload["canonical_label_en"] = "tampered"
        connection.execute(
            "UPDATE entities SET payload_json = ? WHERE entity_id = ?",
            (json.dumps(payload), payload["entity_id"]),
        )
    tampered_database = database_path.read_bytes()
    blob_bytes = {
        item.relative_to(source): item.read_bytes()
        for item in (source / "blobs").rglob("*")
        if item.is_file()
    }

    with pytest.raises(FactMemoryMigrationError, match="row hash mismatch"):
        migrate_v1_to_v2(source, target)
    assert database_path.read_bytes() == tampered_database
    assert {
        item.relative_to(source): item.read_bytes()
        for item in (source / "blobs").rglob("*")
        if item.is_file()
    } == blob_bytes
    assert not target.exists()


def test_polarity_change_after_approval_fails_closed(memory) -> None:
    facts, _ = memory
    source, evidence = _evidence(facts, "polarity-tamper", 100)
    proposal = facts.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create("INTEGER", 100),
        valid_from="2025-01-01",
        source_ids=(source,),
        evidence_ids=(evidence,),
    )
    facts.prepare_for_review(
        proposal.proposal_id,
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    approval = facts.approve_proposal(
        proposal.proposal_id,
        reviewer_identity="approver",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    with facts.database.connect() as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM evidence WHERE evidence_id = ?",
                (evidence,),
            ).fetchone()[0]
        )
        payload["relation"] = EvidenceRelation.CONTRADICTS
        connection.execute(
            "UPDATE evidence SET relation = ?, payload_json = ? WHERE evidence_id = ?",
            (EvidenceRelation.CONTRADICTS, json.dumps(payload), evidence),
        )
        connection.commit()
    with pytest.raises(FactApprovalError):
        facts.commit_proposal(proposal.proposal_id, approval.approval_id)


@pytest.mark.parametrize(
    "tampered_relation",
    [EvidenceRelation.SUPPORTS, EvidenceRelation.CONTRADICTS],
)
def test_evidence_changed_after_approval_fails_closed(
    memory, tampered_relation: EvidenceRelation
) -> None:
    facts, _ = memory
    support = _evidence(facts, f"bound-support-{tampered_relation}", 100)
    rows = [support]
    if tampered_relation == EvidenceRelation.CONTRADICTS:
        rows.append(
            _evidence(
                facts,
                "bound-contradiction",
                100,
                relation=EvidenceRelation.CONTRADICTS,
            )
        )
    proposal = facts.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create("INTEGER", 100),
        valid_from="2025-01-01",
        source_ids=tuple(item[0] for item in rows),
        evidence_ids=tuple(item[1] for item in rows),
    )
    facts.prepare_for_review(
        proposal.proposal_id,
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    approval = facts.approve_proposal(
        proposal.proposal_id,
        reviewer_identity="approver",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    evidence_id = rows[-1][1]
    with facts.database.connect() as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()[0]
        )
        payload["excerpt_hash"] = "0" * 64
        connection.execute(
            "UPDATE evidence SET payload_json = ? WHERE evidence_id = ?",
            (json.dumps(payload), evidence_id),
        )
        connection.commit()
    with pytest.raises(SourceIntegrityError):
        facts.commit_proposal(proposal.proposal_id, approval.approval_id)


def test_approval_actor_type_tamper_fails_closed(memory) -> None:
    facts, _ = memory
    source, evidence = _evidence(facts, "approval-actor-tamper", 100)
    proposal = facts.receive_proposal(
        source=ProposalSource.STRUCTURED_JSON,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create("INTEGER", 100),
        valid_from="2025-01-01",
        source_ids=(source,),
        evidence_ids=(evidence,),
    )
    facts.prepare_for_review(
        proposal.proposal_id,
        reviewer="reviewer",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    approval = facts.approve_proposal(
        proposal.proposal_id,
        reviewer_identity="approver",
        reviewer_identity_type=ActorIdentityType.HUMAN,
    )
    with facts.database.connect() as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM approvals WHERE approval_id = ?",
                (approval.approval_id,),
            ).fetchone()[0]
        )
        payload["reviewer_identity_type"] = ActorIdentityType.MODEL
        connection.execute(
            "UPDATE approvals SET payload_json = ? WHERE approval_id = ?",
            (json.dumps(payload), approval.approval_id),
        )
        connection.commit()
    with pytest.raises(FactApprovalError):
        facts.commit_proposal(proposal.proposal_id, approval.approval_id)


def test_actor_and_resolution_events_are_hashed(memory) -> None:
    facts, _ = memory
    _commit(facts, "audit", 100)
    event_types = {item["event_type"] for item in facts.database.audit_replay()}
    assert "CLAIM_EVIDENCE_ATTACHED" in event_types
    assert facts.verify()["status"] == "VALID"
    assert content_hash({"schema": 2})
