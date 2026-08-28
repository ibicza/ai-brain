from __future__ import annotations

import dataclasses
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.catalog import EducationalCatalogV2
from ai_brain.stage2.education.exercise_generation import verify_presented_exercise
from ai_brain.stage2.education.explanations import (
    render_explanation,
    verify_explanation,
)
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.independent_evaluation import (
    evaluate_independent_fixtures,
)
from ai_brain.stage2.education.models import (
    EducationalDimension,
    EducationalRouteKind,
    ExerciseFamily,
    ExplanationMode,
    TutorSessionStatus,
)
from ai_brain.stage2.education.persistence import (
    EducationalSessionStore,
    EducationalStoreIntegrityError,
)
from ai_brain.stage2.education.service import (
    EducationalService,
    verify_educational_route_receipt,
)
from ai_brain.stage2.education.version import (
    DERIVATION_GRAPH_SCHEMA_VERSION,
    EDUCATIONAL_LAYER_VERSION,
    EDUCATIONAL_SCHEMA_VERSION,
    EXERCISE_SCHEMA_VERSION,
    GRADING_SCHEMA_VERSION,
    HINT_POLICY_VERSION,
    SESSION_STORE_SCHEMA_VERSION,
    TUTOR_SESSION_SCHEMA_VERSION,
)
from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

ROOT = Path(__file__).resolve().parents[1]
CHEMISTRY_ROOT = ROOT / "artifacts" / "domains" / "chemistry" / "m29"
CATALOG_PATH = ROOT / "artifacts" / "education" / "m30" / "catalog_v4.json"
FIXTURES = ROOT / "tests" / "fixtures" / "m292_synthetic_student_errors.jsonl"


@pytest.fixture(scope="module")
def chemistry(tmp_path_factory) -> ChemistryDomainService:
    target = tmp_path_factory.mktemp("m291-chemistry") / "domain"
    shutil.copytree(CHEMISTRY_ROOT, target)
    return ChemistryDomainService.open(target)


@pytest.fixture(scope="module")
def catalog(chemistry) -> EducationalCatalogV2:
    return EducationalCatalogV2.load(CATALOG_PATH, chemistry)


def test_v4_versions_are_explicit() -> None:
    assert EDUCATIONAL_LAYER_VERSION == "1.3.0"
    assert {
        EDUCATIONAL_SCHEMA_VERSION,
        DERIVATION_GRAPH_SCHEMA_VERSION,
        EXERCISE_SCHEMA_VERSION,
        GRADING_SCHEMA_VERSION,
        TUTOR_SESSION_SCHEMA_VERSION,
        SESSION_STORE_SCHEMA_VERSION,
    } == {4}
    assert HINT_POLICY_VERSION == "4.0"


def test_runtime_import_boundary_has_one_direct_executor() -> None:
    education = ROOT / "src" / "ai_brain" / "stage2" / "education"
    direct = []
    for path in education.glob("*.py"):
        if "registry.execute(" in path.read_text(encoding="utf-8"):
            direct.append(path.name)
    assert direct == ["compiler.py"]
    service_text = (education / "service.py").read_text(encoding="utf-8")
    assert "education.compiler" not in service_text


def test_catalog_has_genuine_semantic_diversity_and_disjoint_splits(
    catalog, chemistry
) -> None:
    verified = catalog.verify(chemistry)
    assert verified["entry_count"] == 2_000
    assert verified["distinct_semantic_keys"] == 2_000
    assert len({entry.graph.graph_hash for entry in catalog.entries}) == 2_000
    for manifest in catalog.split_manifests:
        assert manifest["status"] == "TESTED"
        assert not set(manifest["development"]) & set(manifest["final_validation"])
        assert manifest["intersection_count"] == 0


def test_trusted_catalog_and_fixture_bytes_are_platform_stable_lf() -> None:
    for path in (CATALOG_PATH, FIXTURES):
        payload = path.read_bytes()
        assert b"\r\n" not in payload
        assert payload.endswith(b"\n")
        assert not payload.endswith(b"\n\n")


def test_public_presentation_and_precompiled_explanation_execute_nothing(
    chemistry, catalog, tmp_path
) -> None:
    service = EducationalService(
        chemistry,
        EducationalSessionStore.initialize(tmp_path / "store"),
        catalog,
    )
    presented, _ = service._create_exercise_internal(
        ExerciseFamily.MASS_AMOUNT,
        seed=1_111,
        language="en",
        created_at="2026-08-28T00:00:00Z",
    )
    verify_presented_exercise(presented)
    serialized = dataclasses.asdict(presented)
    assert not set(serialized) & {
        "hidden_expected_answer",
        "hidden_answer_graph_hash",
        "counterfactuals",
        "split_axis",
    }
    service.explain_tool(
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "conventional",
            "unit": "g/mol",
            "significant_digits": 3,
        },
        language="en",
    )
    assert service.execution_monitor.count == 0


def test_new_explanation_is_prepared_then_executes_once(catalog, tmp_path) -> None:
    copied = tmp_path / "chemistry"
    shutil.copytree(CHEMISTRY_ROOT, copied)
    service = EducationalService.open(
        copied, tmp_path / "store", catalog_path=CATALOG_PATH
    )
    decision, prepared, proposal = service._explain_tool_internal(
        "chemistry_molar_mass",
        {
            "formula": "O2",
            "mode": "interval",
            "unit": "g/mol",
            "significant_digits": 12,
        },
        language="en",
    )
    assert decision.route_decision_hash
    assert prepared.response_stage.value == "PREPARED"
    assert service.execution_monitor.count == 0
    _, graph, explanation, completed = service._confirm_explanation_internal(
        prepared, proposal, identity="test:user", language="en"
    )
    assert completed.response_stage.value == "COMPLETED"
    assert service.execution_monitor.count == 1
    assert isinstance(
        next(
            node for node in graph.nodes if node.node_id == graph.root_result_node_id
        ).exact_output,
        dict,
    )
    verify_explanation(explanation, graph)


def test_graph_v2_rejects_binding_dimension_rounding_and_source_mutations(
    catalog,
) -> None:
    graph = next(
        entry.graph
        for entry in catalog.entries
        if entry.exercise_spec.family == ExerciseFamily.MASS_AMOUNT
        and any(node.kind.value == "ROUND_DISPLAY" for node in entry.graph.nodes)
    )
    binding = next(node for node in graph.nodes if node.exact_inputs)
    tampered_binding = _replace_node(
        graph, binding, exact_inputs=(*binding.exact_inputs[:-1], "999")
    )
    with pytest.raises(ValueError, match="exact input"):
        verify_derivation_graph(tampered_binding)
    relation = next(node for node in graph.nodes if node.kind.value == "MOLE_RELATION")
    tampered_dimension = _replace_node(
        graph, relation, dimension=EducationalDimension.DIMENSIONLESS
    )
    with pytest.raises(ValueError, match="dimension"):
        verify_derivation_graph(tampered_dimension)
    rounding = next(node for node in graph.nodes if node.kind.value == "ROUND_DISPLAY")
    tampered_rounding = _replace_node(graph, rounding, display_output="999")
    with pytest.raises(ValueError, match="rounded display"):
        verify_derivation_graph(tampered_rounding)
    source = {**graph.source_result_artifact, "operation": "tampered"}
    body = dataclasses.asdict(graph)
    body["source_result_artifact"] = source
    body.pop("graph_hash")
    tampered_source = dataclasses.replace(
        graph, source_result_artifact=source, graph_hash=content_hash(body)
    )
    with pytest.raises(ValueError, match="source result"):
        verify_derivation_graph(tampered_source)


def test_explanation_extra_claim_is_rejected(catalog) -> None:
    graph = catalog.entries[150].graph
    explanation = render_explanation(graph, language="en", mode=ExplanationMode.FULL)
    body = dataclasses.asdict(explanation)
    body["text"] += "\nThe unsupported value is 999 mol."
    body.pop("explanation_hash")
    changed = dataclasses.replace(
        explanation,
        text=body["text"],
        explanation_hash=content_hash(body),
    )
    with pytest.raises(ValueError, match="unsupported content"):
        verify_explanation(changed, graph)
    with pytest.raises(ValueError, match="dedicated authority"):
        render_explanation(graph, language="en", mode=ExplanationMode.CHECK_ONLY)


def test_checksum_valid_semantic_store_tamper_is_rejected(
    chemistry, catalog, tmp_path
) -> None:
    service = EducationalService.open(
        chemistry.root, tmp_path / "store", catalog_path=CATALOG_PATH
    )
    service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=4,
        language="en",
        created_at="2026-08-28T00:00:00Z",
    )
    with sqlite3.connect(service.store.database_path) as connection:
        row = connection.execute(
            "SELECT artifact_hash,payload FROM artifacts WHERE artifact_kind='exercise_instance_internal'"
        ).fetchone()
        payload = json.loads(row[1])
        payload["hidden_expected_answer"] = {"value": "999", "unit": "g/mol"}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        connection.execute(
            "UPDATE artifacts SET payload=?,payload_hash=? WHERE artifact_hash=?",
            (encoded, bytes_hash(encoded.encode()), row[0]),
        )
    with pytest.raises(EducationalStoreIntegrityError, match="hash mismatch"):
        service.store.verify()


def test_independent_diagnosis_is_conservative(catalog) -> None:
    result = evaluate_independent_fixtures(catalog, FIXTURES)
    assert result["fixture_count"] == 1_200
    assert result["wrong_confident_diagnosis"] == 0
    assert result["wrong_targeted_hints"] == 0
    assert result["grading_status_mismatch_count"] == 0
    assert result["macro_precision_predicted_categories"] is not None
    assert result["macro_recall"] < 0.5


def test_terminal_session_transitions_are_rejected(catalog) -> None:
    from ai_brain.stage2.education.sessions import (
        apply_event,
        make_event,
        start_session,
    )

    instance = catalog.entries[500].internal_instance
    session, _ = start_session(
        instance, session_id="terminal", created_at="2026-08-28T00:00:00Z"
    )
    terminal = dataclasses.replace(session, status=TutorSessionStatus.ABANDONED)
    body = dataclasses.asdict(terminal)
    body.pop("session_hash")
    terminal = dataclasses.replace(terminal, session_hash=content_hash(body))
    event = make_event(
        terminal.session_id,
        sequence=2,
        event_type="ANSWER_SUBMITTED",
        payload={"student_answer_hash": "a" * 64},
        previous_event_hash=terminal.last_event_hash,
        created_at="2026-08-28T00:01:00Z",
    )
    with pytest.raises(ValueError, match="state transition"):
        apply_event(terminal, event)


def test_controlled_route_receipt_binds_public_session(
    chemistry, catalog, tmp_path
) -> None:
    service = EducationalService(
        chemistry,
        EducationalSessionStore.initialize(tmp_path / "route-store"),
        catalog,
    )
    route, receipt, result = service._handle_controlled_internal(
        "Give me a molar-mass exercise.", language="en", seed=77
    )
    assert route.kind == EducationalRouteKind.GENERATE_EXERCISE
    assert receipt.session_id == result.session.session_id
    verify_educational_route_receipt(receipt)
    tampered = dataclasses.replace(receipt, session_id="another-session")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_educational_route_receipt(tampered)


def test_admin_compile_cli_uses_disposable_chemistry_copy(
    monkeypatch, tmp_path, capsys
) -> None:
    from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
    from ai_brain.stage2.education import catalog_compiler, cli

    original = tmp_path / "frozen-chemistry"
    original.mkdir()
    (original / "marker.txt").write_text("frozen", encoding="utf-8")
    opened = []
    monkeypatch.setattr(
        ChemistryDomainService,
        "open",
        lambda path: opened.append(Path(path)) or object(),
    )
    monkeypatch.setattr(
        catalog_compiler,
        "compile_catalog_v2",
        lambda service, output, entry_count, audit_path: {
            "status": "COMPILED",
            "entry_count": entry_count,
        },
    )
    cli.main(
        [
            "--chemistry-root",
            str(original),
            "compile-catalog",
            "--output",
            str(tmp_path / "catalog.json"),
            "--audit",
            str(tmp_path / "audit.jsonl"),
            "--entry-count",
            "2000",
        ]
    )
    assert '"status":"COMPILED"' in capsys.readouterr().out
    assert len(opened) == 1
    assert opened[0] != original
    assert not opened[0].exists()
    assert (original / "marker.txt").read_text(encoding="utf-8") == "frozen"


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
