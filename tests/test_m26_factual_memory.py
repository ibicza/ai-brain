from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import (
    FactApprovalError,
    FactMemory,
    FactQueryError,
    FactWorkflowError,
)
from ai_brain.stage2.facts.models import (
    Cardinality,
    ClaimStatus,
    EvidenceLocationKind,
    EvidenceRelation,
    ExtractionMethod,
    FactAnswerBundle,
    ProposalSource,
    ProposalStatus,
    QueryStatus,
    ReplayStatus,
    SourceKind,
    TemporalMode,
)
from ai_brain.stage2.facts.persistence import FactDatabase, FactMemoryIntegrityError
from ai_brain.stage2.facts.rendering import render_answer
from ai_brain.stage2.facts.sources import SourceIntegrityError
from ai_brain.stage2.facts.values import FactValue, FactValueKind


class Clock:
    def __init__(self, value: str = "2026-01-01T00:00:00Z") -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


@pytest.fixture
def fact_memory(tmp_path: Path) -> tuple[FactMemory, Clock]:
    clock = Clock()
    memory = FactMemory.initialize(tmp_path / "facts", clock=clock)
    memory.add_entity(
        entity_id="city.alpha",
        entity_type="CITY",
        canonical_label_ru="Альфа",
        canonical_label_en="Alpha",
        aliases_ru=("Город Альфа",),
        aliases_en=("Alpha City",),
        provenance=({"kind": "SYNTHETIC"},),
    )
    memory.add_predicate(
        predicate_id="population",
        canonical_name_ru="население",
        canonical_name_en="population",
        subject_entity_type="CITY",
        object_kind=FactValueKind.INTEGER,
        cardinality=Cardinality.SINGLE,
        temporal_mode=TemporalMode.VALID_INTERVAL,
    )
    return memory, clock


def _source_evidence(
    memory: FactMemory,
    *,
    value: int,
    suffix: str,
    family: str | None = None,
    method: ExtractionMethod = ExtractionMethod.DETERMINISTIC,
    reviewer: str | None = None,
) -> tuple[str, str]:
    text = f"population={value}"
    source = memory.add_source(
        content=text,
        source_kind=SourceKind.LOCAL_DOCUMENT,
        title=f"Synthetic source {suffix}",
        source_family=family or f"family-{suffix}",
        trust_tier="T1",
        source_id=f"source.{suffix}",
        locator=f"local:{suffix}",
    )
    evidence = memory.add_evidence(
        source_id=source.source_id,
        relation=EvidenceRelation.SUPPORTS,
        location_kind=EvidenceLocationKind.CHAR_SPAN,
        location={"start": 11, "end": len(text)},
        extraction_method=method,
        extraction_confidence=Decimal(1),
        reviewer=reviewer,
        approved=True,
        evidence_id=f"evidence.{suffix}",
    )
    return source.source_id, evidence.evidence_id


def _commit(
    memory: FactMemory,
    *,
    value: int,
    suffix: str,
    valid_from: str = "2025-01-01",
    valid_to: str | None = None,
    family: str | None = None,
    source: ProposalSource = ProposalSource.STRUCTURED_JSON,
) -> tuple[str, str, str]:
    source_id, evidence_id = _source_evidence(
        memory, value=value, suffix=suffix, family=family
    )
    proposal = memory.receive_proposal(
        source=source,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create(FactValueKind.INTEGER, value),
        valid_from=valid_from,
        valid_to=valid_to,
        source_ids=(source_id,),
        evidence_ids=(evidence_id,),
        proposal_id=f"proposal.{suffix}",
    )
    reviewed = memory.prepare_for_review(proposal.proposal_id, reviewer="reviewer")
    approval = memory.approve_proposal(
        reviewed.proposal_id,
        reviewer_identity="reviewer",
    )
    claim = memory.commit_proposal(reviewed.proposal_id, approval.approval_id)
    return claim.claim_id, source_id, evidence_id


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (FactValueKind.INTEGER, True),
        (FactValueKind.DECIMAL, float("nan")),
        (FactValueKind.DECIMAL, "Infinity"),
        (FactValueKind.DATE, "2026-99-01"),
        (FactValueKind.DATETIME, "2026-01-01T00:00:00"),
        (FactValueKind.ENTITY_REF, "../../rule"),
    ],
)
def test_fact_value_rejects_unsafe_values(kind: FactValueKind, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        FactValue.create(kind, value)


def test_fact_value_is_deterministic_and_uses_decimal() -> None:
    first = FactValue.create(FactValueKind.QUANTITY, "01.2300", unit="m")
    second = FactValue.create(FactValueKind.QUANTITY, Decimal("1.23"), unit="m")
    assert first == second
    assert first.value == "1.23"
    assert content_hash(first) == content_hash(second)


def test_exact_entity_resolution_is_ambiguity_safe(fact_memory) -> None:
    memory, _ = fact_memory
    memory.add_entity(
        entity_id="company.alpha",
        entity_type="COMPANY",
        canonical_label_ru="Компания Альфа",
        canonical_label_en="Alpha Company",
        aliases_en=("Alpha",),
    )
    resolution = memory.resolve_entity("Alpha", "en")
    assert resolution.status.value == "AMBIGUOUS_ENTITY"
    assert set(resolution.entity_ids) == {"city.alpha", "company.alpha"}


def test_workflow_cannot_skip_or_self_approve_model_proposal(fact_memory) -> None:
    memory, _ = fact_memory
    source_id, evidence_id = _source_evidence(memory, value=10, suffix="model")
    proposal = memory.receive_proposal(
        source=ProposalSource.MODEL_EXTRACTION,
        subject_entity_id="city.alpha",
        predicate_id="population",
        object_value=FactValue.create("INTEGER", 10),
        valid_from="2025-01-01",
        source_ids=(source_id,),
        evidence_ids=(evidence_id,),
    )
    with pytest.raises(FactWorkflowError):
        memory.advance_proposal(proposal.proposal_id, ProposalStatus.REVIEWED)
    reviewed = memory.prepare_for_review(proposal.proposal_id, reviewer="human")
    with pytest.raises(FactApprovalError, match="cannot approve itself"):
        memory.approve_proposal(
            reviewed.proposal_id,
            reviewer_identity="model",
            reviewer_identity_type="MODEL",
        )


def test_exact_query_returns_evidence_bearing_receipt(fact_memory) -> None:
    memory, _ = fact_memory
    claim_id, source_id, evidence_id = _commit(memory, value=100, suffix="exact")
    query = memory.make_query(
        subject="Alpha City",
        predicate_id="population",
        valid_at_value="2025-06-01",
        language="en",
    )
    bundle = memory.query(query)
    assert bundle.answer_status == QueryStatus.EXACT_SINGLE
    assert bundle.selected_claim_ids == (claim_id,)
    assert bundle.claims[0].source_ids == (source_id,)
    assert bundle.claims[0].evidence_ids == (evidence_id,)
    assert bundle.claims[0].source_hashes
    assert bundle.claims[0].evidence_hashes
    assert memory.replay_answer(bundle) == ReplayStatus.CURRENT
    rendered = render_answer(bundle, language="ru")
    assert "Статус" in rendered and "Источник" in rendered


def test_duplicate_claim_merges_independent_evidence(fact_memory) -> None:
    memory, _ = fact_memory
    first, _, _ = _commit(memory, value=100, suffix="duplicate-a")
    second, _, _ = _commit(memory, value=100, suffix="duplicate-b")
    assert first == second
    claim = memory.get_claim(first)
    assert claim.status == ClaimStatus.CORROBORATED
    assert len(claim.evidence_ids) == 2
    assert len(claim.source_family_support_set) == 2


def test_mirrored_lineage_does_not_create_corroboration(fact_memory) -> None:
    memory, _ = fact_memory
    first, _, _ = _commit(memory, value=100, suffix="mirror-a", family="one-document")
    second, _, _ = _commit(memory, value=100, suffix="mirror-b", family="one-document")
    assert first == second
    assert memory.get_claim(first).status == ClaimStatus.SUPPORTED


def test_single_conflict_returns_all_claims_without_winner(fact_memory) -> None:
    memory, _ = fact_memory
    first, _, _ = _commit(memory, value=100, suffix="conflict-a")
    second, _, _ = _commit(memory, value=200, suffix="conflict-b")
    bundle = memory.query(
        memory.make_query(
            subject="city.alpha",
            predicate_id="population",
            valid_at_value="2025-06-01",
        )
    )
    assert bundle.answer_status == QueryStatus.CONFLICT
    assert set(bundle.selected_claim_ids) == {first, second}
    assert bundle.conflict_group_ids
    assert "UNRESOLVED_CONFLICT" in bundle.warnings


def test_source_retraction_cannot_silently_win_a_conflict(fact_memory) -> None:
    memory, clock = fact_memory
    first, first_source, _ = _commit(memory, value=100, suffix="stale-conflict-a")
    second, _, _ = _commit(memory, value=200, suffix="stale-conflict-b")
    clock.value = "2026-03-01T00:00:00Z"
    memory.retract_source(first_source, actor="publisher", reason="withdrawn")
    bundle = memory.query(
        memory.make_query(
            subject="city.alpha",
            predicate_id="population",
            valid_at_value="2025-06-01",
        )
    )
    assert bundle.answer_status == QueryStatus.CONFLICT
    assert set(bundle.selected_claim_ids) == {first, second}
    assert "SOURCE_RETRACTED_OR_UNAVAILABLE_SIDE" in bundle.warnings


def test_adjacent_intervals_do_not_conflict(fact_memory) -> None:
    memory, _ = fact_memory
    _commit(
        memory,
        value=100,
        suffix="adjacent-a",
        valid_from="2024-01-01",
        valid_to="2025-01-01",
    )
    _commit(
        memory,
        value=200,
        suffix="adjacent-b",
        valid_from="2025-01-01",
        valid_to="2026-01-01",
    )
    assert not memory.conflicts()
    boundary = memory.query(
        memory.make_query(
            subject="city.alpha",
            predicate_id="population",
            valid_at_value="2025-01-01",
        )
    )
    assert boundary.answer_status == QueryStatus.EXACT_SINGLE
    assert boundary.claims[0].value.value == "200"


def test_known_at_preserves_pre_retraction_history(fact_memory) -> None:
    memory, clock = fact_memory
    clock.value = "2026-01-01T00:00:00Z"
    claim_id, _, _ = _commit(memory, value=100, suffix="history")
    clock.value = "2026-02-01T00:00:00Z"
    memory.retract_claim(claim_id, actor="reviewer", reason="source correction")
    historical = memory.query(
        memory.make_query(
            subject="city.alpha",
            predicate_id="population",
            valid_at_value="2025-06-01",
            known_at="2026-01-15T00:00:00Z",
        )
    )
    current = memory.query(
        memory.make_query(
            subject="city.alpha",
            predicate_id="population",
            valid_at_value="2025-06-01",
        )
    )
    assert historical.answer_status == QueryStatus.EXACT_SINGLE
    assert current.answer_status == QueryStatus.RETRACTED_ONLY


def test_source_retraction_propagates_without_deletion(fact_memory) -> None:
    memory, clock = fact_memory
    claim_id, source_id, _ = _commit(memory, value=100, suffix="source-retract")
    clock.value = "2026-03-01T00:00:00Z"
    memory.retract_source(source_id, actor="publisher", reason="withdrawn")
    result = memory.query(
        memory.make_query(
            subject="city.alpha",
            predicate_id="population",
            valid_at_value="2025-06-01",
        )
    )
    assert result.answer_status == QueryStatus.STALE_ONLY
    assert memory.get_claim(claim_id).claim_id == claim_id
    assert [item.claim_id for item in memory.claims_affected_by_source(source_id)] == [
        claim_id
    ]


def test_changed_blob_and_query_receipt_fail_closed(fact_memory) -> None:
    memory, _ = fact_memory
    _, source_id, evidence_id = _commit(memory, value=100, suffix="tamper")
    source = memory.get_source(source_id)
    memory.database.blobs.path_for(source.snapshot_hash).write_text(
        "population=999", encoding="utf-8"
    )
    with pytest.raises(SourceIntegrityError):
        memory.verify_evidence(evidence_id)

    query = memory.make_query(subject="city.alpha", predicate_id="population")
    changed = replace(query, subject="other")
    result = memory.query(changed)
    assert result.answer_status == QueryStatus.INVALID_QUERY


def test_backup_restore_export_and_audit_chain(fact_memory, tmp_path: Path) -> None:
    memory, _ = fact_memory
    claim_id, _, _ = _commit(memory, value=100, suffix="backup")
    backup = tmp_path / "backup"
    memory.database.backup(backup)
    restored = FactMemory(FactDatabase.restore(backup, tmp_path / "restored"))
    assert restored.get_claim(claim_id).claim_id == claim_id
    assert restored.verify()["status"] == "VALID"
    manifest = restored.database.export(tmp_path / "export")
    assert manifest["files"]["claims.jsonl"]["count"] == 1
    assert restored.database.audit_replay(claim_id)


def test_corrupt_backup_is_rejected(fact_memory, tmp_path: Path) -> None:
    memory, _ = fact_memory
    backup = tmp_path / "bad-backup"
    memory.database.backup(backup)
    with (backup / "fact_memory.sqlite3").open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(Exception, match="hash mismatch"):
        FactDatabase.restore(backup, tmp_path / "bad-restore")


def test_trusted_fact_import_loads_no_torch() -> None:
    command = (
        "import sys; import ai_brain.stage2.facts; "
        "assert 'torch' not in sys.modules; print('NO_TORCH')"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "NO_TORCH"


def test_fact_value_cannot_embed_rule_or_execution_authority() -> None:
    from ai_brain.rules.specifications import ProgramSpecification

    with pytest.raises(TypeError):
        FactValue.create(FactValueKind.STRING, ProgramSpecification(()))
    fields = set(FactAnswerBundle.__dataclass_fields__)
    assert not fields & {"execute", "dispatch", "skill_id", "rule_id", "authority"}


def test_database_row_hash_tamper_is_detected(fact_memory) -> None:
    memory, _ = fact_memory
    with memory.database.connect() as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM entities WHERE entity_id = 'city.alpha'"
            ).fetchone()[0]
        )
        payload["canonical_label_en"] = "Changed"
        connection.execute(
            "UPDATE entities SET payload_json = ? WHERE entity_id = 'city.alpha'",
            (json.dumps(payload),),
        )
        connection.commit()
    with pytest.raises(FactMemoryIntegrityError, match="row hash mismatch"):
        memory.verify()


def test_query_ids_are_unique_and_old_answers_become_stale(fact_memory) -> None:
    memory, _ = fact_memory
    _commit(memory, value=100, suffix="query-receipt")
    query = memory.make_query(subject="city.alpha", predicate_id="population")
    bundle = memory.query(query)
    with pytest.raises(FactQueryError, match="already used"):
        memory.query(query)
    memory.add_entity(
        entity_id="city.beta",
        entity_type="CITY",
        canonical_label_ru="Бета",
        canonical_label_en="Beta",
    )
    assert memory.replay_answer(bundle) == ReplayStatus.STALE_SNAPSHOT


def test_write_transaction_rolls_back_and_supersession_cycles_fail(fact_memory) -> None:
    memory, _ = fact_memory
    with (
        pytest.raises(RuntimeError, match="crash"),
        memory.database.write() as connection,
    ):
        connection.execute(
            """INSERT INTO entity_aliases
               VALUES ('temporary', 'en', 'city.alpha', 'Temporary')"""
        )
        raise RuntimeError("simulated crash before commit")
    with memory.database.connect() as connection:
        assert not connection.execute(
            "SELECT 1 FROM entity_aliases WHERE normalized_alias = 'temporary'"
        ).fetchall()

    first, _, _ = _commit(memory, value=100, suffix="cycle-a")
    second, _, _ = _commit(memory, value=200, suffix="cycle-b")
    memory.supersede_claim(first, second, actor="reviewer", reason="new version")
    with pytest.raises(ValueError, match="cycle"):
        memory.supersede_claim(second, first, actor="reviewer", reason="bad cycle")


def test_synthetic_generator_has_required_coverage(tmp_path: Path) -> None:
    from ai_brain.stage2.facts.benchmark import generate_synthetic_corpus

    manifest = generate_synthetic_corpus(
        tmp_path / "synthetic",
        claim_count=100,
        entity_count=20,
        predicate_count=25,
        source_count=10,
    )
    assert manifest["accepted_claim_count"] == 100
    assert manifest["temporal_update_count"] == 10
    assert manifest["intentional_conflict_count"] == 5
    assert manifest["duplicate_support_count"] == 5
    assert set(manifest["value_kind_counts"]) == {item.value for item in FactValueKind}
    assert FactMemory.open(tmp_path / "synthetic").verify()["status"] == "VALID"
