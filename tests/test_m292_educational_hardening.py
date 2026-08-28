from __future__ import annotations

import dataclasses
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from ai_brain.stage2.domains.chemistry.models import ChemistryReplayStatus
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education import currentness
from ai_brain.stage2.education.catalog import EducationalCatalogV2
from ai_brain.stage2.education.currentness import EducationalIntegrityError
from ai_brain.stage2.education.exercise_generation import (
    instantiate_variant,
    make_semantic_key,
    present_exercise,
    public_exercise,
)
from ai_brain.stage2.education.explanations import render_check_explanation
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.independent_evaluation import (
    evaluate_independent_fixtures,
)
from ai_brain.stage2.education.models import (
    ExerciseFamily,
    GradingStatus,
    HintLevel,
    TutorSession,
)
from ai_brain.stage2.education.persistence import (
    EducationalSessionStore,
    EducationalStoreIntegrityError,
)
from ai_brain.stage2.education.service import EducationalService
from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage2.facts.models import ClaimStatus, SourceStatus

ROOT = Path(__file__).resolve().parents[1]
CHEMISTRY_ROOT = ROOT / "artifacts" / "domains" / "chemistry" / "m29"
CATALOG_PATH = ROOT / "artifacts" / "education" / "m30" / "catalog_v4.json"
FIXTURES = ROOT / "tests" / "fixtures" / "m292_synthetic_student_errors.jsonl"


@pytest.fixture(scope="module")
def chemistry(tmp_path_factory) -> ChemistryDomainService:
    target = tmp_path_factory.mktemp("m292-chemistry") / "domain"
    shutil.copytree(CHEMISTRY_ROOT, target)
    return ChemistryDomainService.open(target)


@pytest.fixture(scope="module")
def catalog(chemistry) -> EducationalCatalogV2:
    return EducationalCatalogV2.load(CATALOG_PATH, chemistry)


def test_operation_only_rehashed_mutations_are_rejected(catalog) -> None:
    seen = set()
    for entry in catalog.entries:
        for node in entry.graph.nodes:
            if node.operation is None or node.kind in seen:
                continue
            seen.add(node.kind)
            replacement = "ADD" if node.operation != "ADD" else "MULTIPLY"
            tampered = _replace_node(entry.graph, node, operation=replacement)
            with pytest.raises(ValueError, match="operation"):
                verify_derivation_graph(tampered)
    assert {item.value for item in seen} == {
        "ADD",
        "AVOGADRO_RELATION",
        "FINAL_RESULT",
        "FORMULA_COMPOSITION",
        "FORMULA_PARSE",
        "MOLE_RELATION",
        "MULTIPLY",
        "ROUND_DISPLAY",
        "UNIT_NORMALIZATION",
    }


def test_post_startup_stale_dependencies_fail_before_any_write(
    chemistry, catalog, tmp_path
) -> None:
    service = EducationalService(
        chemistry,
        EducationalSessionStore.initialize(tmp_path / "stale-store"),
        catalog,
    )
    before = _store_counts(service.store)
    original = chemistry.manifest["fact_memory_snapshot_hash"]
    chemistry.manifest["fact_memory_snapshot_hash"] = "0" * 64
    try:
        with pytest.raises(ValueError, match="STALE_FACT_MEMORY"):
            service.create_exercise(
                ExerciseFamily.MOLAR_MASS_SIMPLE,
                seed=11,
                language="en",
                session_id="m292-stale",
            )
    finally:
        chemistry.manifest["fact_memory_snapshot_hash"] = original
    assert _store_counts(service.store) == before
    assert service.execution_monitor.count == 0


def test_rehashed_presented_exercise_semantic_tamper_is_rejected(
    chemistry, catalog, tmp_path
) -> None:
    service = EducationalService(
        chemistry,
        EducationalSessionStore.initialize(tmp_path / "artifact-store"),
        catalog,
    )
    service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=12,
        language="en",
        session_id="m292-artifact",
    )
    with sqlite3.connect(service.store.database_path) as connection:
        key, payload = connection.execute(
            "SELECT artifact_hash,payload FROM artifacts "
            "WHERE artifact_kind='presented_exercise'"
        ).fetchone()
        row = json.loads(payload)
        row["question_text"] = "Checksum-valid but semantically forged question."
        body = dict(row)
        body.pop("presentation_hash")
        new_key = content_hash(body)
        row["presentation_hash"] = new_key
        encoded = canonical_json(row)
        connection.execute(
            "UPDATE artifacts SET artifact_hash=?,payload=?,payload_hash=? "
            "WHERE artifact_hash=?",
            (new_key, encoded, bytes_hash(encoded.encode("utf-8")), key),
        )
    with pytest.raises(EducationalStoreIntegrityError):
        service.store.verify()


def test_learner_service_does_not_return_internal_session(
    chemistry, catalog, tmp_path
) -> None:
    service = EducationalService(
        chemistry,
        EducationalSessionStore.initialize(tmp_path / "public-store"),
        catalog,
    )
    result = service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=13,
        language="en",
        session_id="m292-public",
    )
    assert not any(isinstance(item, TutorSession) for item in _flatten(result))
    serialized = json.dumps(dataclasses.asdict(result), sort_keys=True)
    assert not any(
        token in serialized
        for token in (
            "graph_hash",
            "receipt",
            "hidden_expected_answer",
            "counterfactual",
            "split_",
            "event_hash",
        )
    )


def test_split_manifests_declare_exact_truthful_universes(catalog) -> None:
    semantic = {entry.semantic_key.semantic_key_hash for entry in catalog.entries}
    axes = set()
    for manifest in catalog.split_manifests:
        assert manifest["axis"] not in {
            "TEMPLATE_HOLDOUT",
            "RU_EN_CROSS_LANGUAGE",
            "MISCONCEPTION_HOLDOUT",
        }
        assert manifest["axis"] not in axes
        axes.add(manifest["axis"])
        development = tuple(manifest["development"])
        final = tuple(manifest["final_validation"])
        assert development and final
        assert len(development) == len(set(development))
        assert len(final) == len(set(final))
        assert not set(development) & set(final)
        assert set(development) | set(final) == semantic
        assert manifest["intersection_count"] == len(set(development) & set(final))
        assert manifest["universe_kind"] == "semantic_key_hash"
        assert manifest["universe_count"] == len(semantic)
        assert manifest["universe_hash"] == content_hash(tuple(sorted(semantic)))


def test_diagnosis_metrics_abstain_honestly_and_fixtures_are_not_fake_reviewed(
    catalog,
) -> None:
    result = evaluate_independent_fixtures(catalog, FIXTURES)
    assert result["evaluation_kind"] == "SYNTHETIC_CROSS_IMPLEMENTATION"
    assert result["metric_formula_version"] == "m292-honest-abstention-v1"
    assert result["diagnosis_coverage"] + result["abstention_rate"] == 1.0
    assert "micro_precision" in result
    assert result["macro_precision_predicted_categories"] is not None
    assert any(
        row["precision"] is None
        for row in result["per_category"].values()
        if row["prediction_count"] == 0
    )
    first = json.loads(FIXTURES.read_text(encoding="utf-8").splitlines()[0])
    assert first["human_review_status"] == "NOT_REVIEWED"
    assert "fixture_reviewer" not in first


def test_complete_session_closure_is_authority_verified(
    chemistry, catalog, tmp_path
) -> None:
    service = EducationalService(
        chemistry,
        EducationalSessionStore.initialize(tmp_path / "authority-store"),
        catalog,
    )
    exercise = service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=44,
        language="en",
        session_id="m292-authority",
        created_at="2026-08-28T00:00:00Z",
    )
    submission = service.submit_answer(
        exercise.session.session_id,
        "0 g/mol",
        created_at="2026-08-28T00:01:00Z",
    )
    assert submission.feedback
    assert service.hint(
        exercise.session.session_id,
        level=HintLevel.ORIENT,
        created_at="2026-08-28T00:02:00Z",
    ).text
    assert service.show_solution(
        exercise.session.session_id,
        created_at="2026-08-28T00:03:00Z",
    ).text
    verified = service.verify()
    assert verified["educational_store_structural"]["status"] == (
        "STRUCTURALLY_VERIFIED"
    )
    assert verified["educational_store_authority"]["status"] == ("AUTHORITY_VERIFIED")


def test_fact_memory_staleness_blocks_every_trust_bearing_action(
    chemistry, catalog, tmp_path
) -> None:
    service = EducationalService(
        chemistry,
        EducationalSessionStore.initialize(tmp_path / "all-actions-store"),
        catalog,
    )
    exercise = service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=55,
        language="en",
        session_id="m292-all-actions",
        created_at="2026-08-28T00:00:00Z",
    )
    service.submit_answer(
        exercise.session.session_id,
        "0 g/mol",
        created_at="2026-08-28T00:01:00Z",
    )
    entry = catalog.select(ExerciseFamily.MOLAR_MASS_SIMPLE, seed=55)
    counts = _store_counts(service.store)
    head = service.store.get_session(exercise.session.session_id).session_hash
    executions = service.execution_monitor.count
    original = chemistry.manifest["fact_memory_snapshot_hash"]
    chemistry.manifest["fact_memory_snapshot_hash"] = "0" * 64
    try:
        rejected = (
            lambda: service.explain_tool(
                entry.compilation_receipt.tool_id,
                entry.compilation_receipt.canonical_arguments,
                language="en",
            ),
            lambda: service.create_exercise(
                ExerciseFamily.MOLAR_MASS_SIMPLE, seed=56, language="en"
            ),
            lambda: service.submit_answer(exercise.session.session_id, "0 g/mol"),
            lambda: service.hint(exercise.session.session_id),
            lambda: service.show_solution(exercise.session.session_id),
        )
        for action in rejected:
            with pytest.raises(EducationalIntegrityError) as caught:
                action()
            assert caught.value.status.value == "STALE_FACT_MEMORY"
            assert str(caught.value) == "STALE_FACT_MEMORY"
        replay = service.replay(exercise.session.session_id)
        assert replay.status == "STALE_FACT_MEMORY"
    finally:
        chemistry.manifest["fact_memory_snapshot_hash"] = original
    assert _store_counts(service.store) == counts
    assert service.store.get_session(exercise.session.session_id).session_hash == head
    assert service.execution_monitor.count == executions


def test_public_serialization_boundary_has_one_thousand_clean_probes(catalog) -> None:
    forbidden_names = {
        "graph_hash",
        "receipt_hash",
        "hidden_expected_answer",
        "hidden_answer_graph_hash",
        "counterfactuals",
        "split_memberships",
        "event_hash",
        "provenance_dependencies",
    }
    for index in range(1_000):
        entry = catalog.entries[index % len(catalog.entries)]
        instance = instantiate_variant(
            entry.internal_instance,
            entry.exercise_spec,
            entry.graph,
            seed=index,
            language=("ru", "en")[index % 2],
        )
        presented = present_exercise(
            instance, entry.exercise_spec, session_id=f"m292-public-{index}"
        )
        value = public_exercise(presented, session_status="PRESENTED")
        row = dataclasses.asdict(value)
        encoded = json.dumps(row, sort_keys=True)
        assert not forbidden_names & set(_nested_keys(row))
        assert entry.graph.graph_hash not in encoded
        assert entry.compilation_receipt.receipt_hash not in encoded
        assert (
            json.dumps(instance.hidden_expected_answer, sort_keys=True) not in encoded
        )


def test_rehashed_grading_closure_passes_structure_but_fails_authority(
    chemistry, catalog, tmp_path
) -> None:
    service = EducationalService(
        chemistry,
        EducationalSessionStore.initialize(tmp_path / "forged-grade-store"),
        catalog,
    )
    exercise = service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=66,
        language="en",
        session_id="m292-forged-grade",
        created_at="2026-08-28T00:00:00Z",
    )
    service.submit_answer(
        exercise.session.session_id,
        "0 g/mol",
        created_at="2026-08-28T00:01:00Z",
    )
    session = service.store.get_session(exercise.session.session_id)
    graph = service.store.get_artifact(
        session.graph_hash, expected_kind="derivation_graph"
    )
    grade = service.store.get_artifact(
        session.grading_result_hashes[-1], expected_kind="grading_result"
    )
    grade_body = dataclasses.asdict(grade)
    old_grade_hash = grade_body.pop("result_hash")
    grade_body.update(
        {
            "correctness_status": GradingStatus.CORRECT,
            "score": "1",
            "correct_nodes": (graph.root_result_node_id,),
            "incorrect_nodes": (),
            "first_incorrect_node": None,
            "error_diagnoses": (),
            "unit_comparison": "SAME",
            "rounding_comparison": "EXACT",
        }
    )
    forged_grade = dataclasses.replace(
        grade,
        **grade_body,
        result_hash=content_hash(grade_body),
    )
    old_check = service.store.artifacts("explanation")[0]
    forged_check = render_check_explanation(graph, forged_grade, language="en")
    with sqlite3.connect(service.store.database_path) as connection:
        _replace_artifact(
            connection,
            old_grade_hash,
            forged_grade.result_hash,
            dataclasses.asdict(forged_grade),
        )
        _replace_artifact(
            connection,
            old_check.explanation_hash,
            forged_check.explanation_hash,
            dataclasses.asdict(forged_check),
        )
        event_row = connection.execute(
            "SELECT payload FROM events WHERE session_id=? AND sequence=3",
            (session.session_id,),
        ).fetchone()
        event = json.loads(event_row[0])
        event["payload"] = {
            "grading_result_hash": forged_grade.result_hash,
            "check_explanation_hash": forged_check.explanation_hash,
            "solved": True,
        }
        event_body = dict(event)
        event_body.pop("event_hash")
        event["event_hash"] = content_hash(event_body)
        connection.execute(
            "UPDATE events SET event_hash=?,payload=? "
            "WHERE session_id=? AND sequence=3",
            (
                event["event_hash"],
                canonical_json(event),
                session.session_id,
            ),
        )
        session_row = json.loads(
            connection.execute(
                "SELECT payload FROM sessions WHERE session_id=?",
                (session.session_id,),
            ).fetchone()[0]
        )
        session_row["grading_result_hashes"] = [forged_grade.result_hash]
        session_row["status"] = "SOLVED"
        session_row["last_event_hash"] = event["event_hash"]
        session_body = dict(session_row)
        session_body.pop("session_hash")
        session_row["session_hash"] = content_hash(session_body)
        connection.execute(
            "UPDATE sessions SET payload=?,session_hash=? WHERE session_id=?",
            (
                canonical_json(session_row),
                session_row["session_hash"],
                session.session_id,
            ),
        )
    assert service.store.verify()["status"] == "STRUCTURALLY_VERIFIED"
    with pytest.raises(ValueError, match="grading result is not reproducible"):
        service.verify()


def test_currentness_core_reports_each_dependency_reason(
    chemistry, catalog, monkeypatch
) -> None:
    fact_entry = next(
        entry
        for entry in catalog.entries
        if entry.exercise_spec.family == ExerciseFamily.FACT_RETRIEVAL
    )
    numeric_entry = next(
        entry
        for entry in catalog.entries
        if entry.exercise_spec.family == ExerciseFamily.MOLAR_MASS_SIMPLE
    )

    def status(entry=fact_entry, *, receipt=None, instance=None):
        return currentness.evaluate_dependency_currentness(
            chemistry,
            entry.graph,
            receipt or entry.compilation_receipt,
            instance or entry.internal_instance,
            entry.exercise_spec,
        ).status.value

    with monkeypatch.context() as scoped:
        scoped.setitem(chemistry.manifest, "domain_version", "stale-domain")
        assert status() == "STALE_DOMAIN"
    with monkeypatch.context() as scoped:
        scoped.setitem(chemistry.manifest, "fact_memory_snapshot_hash", "0" * 64)
        assert status() == "STALE_FACT_MEMORY"
    with monkeypatch.context() as scoped:
        scoped.setitem(chemistry.manifest, "source_chain_hash", "0" * 64)
        assert status() == "STALE_SOURCE_CHAIN"

    tool_receipt = _rehash_dataclass(
        numeric_entry.compilation_receipt,
        tool_implementation_manifest_hash="0" * 64,
        hash_field="receipt_hash",
    )
    assert status(numeric_entry, receipt=tool_receipt) == "STALE_TOOL"
    receipt = _rehash_dataclass(
        fact_entry.compilation_receipt,
        exact_result_hash="0" * 64,
        hash_field="receipt_hash",
    )
    assert status(receipt=receipt) == "STALE_COMPILATION_RECEIPT"

    original_claim = chemistry.memory.get_claim_state
    with monkeypatch.context() as scoped:
        scoped.setattr(
            chemistry.memory,
            "get_claim_state",
            lambda claim_id: dataclasses.replace(
                original_claim(claim_id), status=ClaimStatus.RETRACTED
            ),
        )
        assert status() == "STALE_CLAIM"
    with monkeypatch.context() as scoped:
        scoped.setattr(
            chemistry.memory,
            "verify_evidence",
            lambda evidence_id: (_ for _ in ()).throw(KeyError(evidence_id)),
        )
        assert status() == "STALE_EVIDENCE"
    original_source = chemistry.memory.get_source_state
    with monkeypatch.context() as scoped:
        scoped.setattr(
            chemistry.memory,
            "get_source_state",
            lambda source_id: dataclasses.replace(
                original_source(source_id), status=SourceStatus.RETRACTED
            ),
        )
        assert status() == "STALE_SOURCE"
    with monkeypatch.context() as scoped:
        scoped.setattr(
            currentness,
            "replay_chemistry_result",
            lambda *args: ChemistryReplayStatus.RETRACTED_UPSTREAM_SOURCE,
        )
        assert status(numeric_entry) == "STALE_UPSTREAM_SOURCE"

    expected = dict(numeric_entry.internal_instance.hidden_expected_answer)
    expected["value"] = "999"
    semantic = make_semantic_key(
        numeric_entry.exercise_spec.family,
        numeric_entry.internal_instance.structured_givens,
        expected,
        numeric_entry.graph,
    )
    instance = _rehash_dataclass(
        numeric_entry.internal_instance,
        hidden_expected_answer=expected,
        semantic_key_hash=semantic.semantic_key_hash,
        hash_field="instance_hash",
    )
    assert status(numeric_entry, instance=instance) == "STALE_ANSWER_KEY"


def _nested_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _nested_keys(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _nested_keys(item)


def _replace_artifact(connection, old_hash, new_hash, row) -> None:
    payload = canonical_json(row)
    connection.execute(
        "UPDATE artifacts SET artifact_hash=?,payload=?,payload_hash=? "
        "WHERE artifact_hash=?",
        (new_hash, payload, bytes_hash(payload.encode("utf-8")), old_hash),
    )


def _rehash_dataclass(value, *, hash_field, **changes):
    provisional = dataclasses.replace(value, **changes, **{hash_field: ""})
    body = dataclasses.asdict(provisional)
    body.pop(hash_field)
    return dataclasses.replace(provisional, **{hash_field: content_hash(body)})


def _replace_node(graph, node, **changes):
    provisional = dataclasses.replace(node, **changes, node_hash="")
    node_body = dataclasses.asdict(provisional)
    node_body.pop("node_hash")
    changed = dataclasses.replace(provisional, node_hash=content_hash(node_body))
    nodes = tuple(
        changed if item.node_id == node.node_id else item for item in graph.nodes
    )
    graph_body = dataclasses.asdict(graph)
    graph_body["nodes"] = nodes
    graph_body.pop("graph_hash")
    return dataclasses.replace(graph, nodes=nodes, graph_hash=content_hash(graph_body))


def _store_counts(store) -> tuple[int, int, int]:
    with sqlite3.connect(store.database_path) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("artifacts", "events", "sessions")
        )


def _flatten(value):
    if isinstance(value, tuple):
        for item in value:
            yield from _flatten(item)
    else:
        yield value
