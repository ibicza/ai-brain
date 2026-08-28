from __future__ import annotations

import dataclasses
import runpy
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from ai_brain.stage2.domains.chemistry.education.controlled import (
    parse_educational_request,
)
from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.domains.chemistry.education.misconception_catalog import (
    COUNTERFACTUAL_CALCULATORS,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.source_derivation import (
    _resolve_json_pointer,
    verify_source_chain,
)
from ai_brain.stage2.education.answer_parser import parse_student_answer
from ai_brain.stage2.education.answers import numeric_equivalent
from ai_brain.stage2.education.catalog import EducationalCatalogV2
from ai_brain.stage2.education.compiler import COMPILER_IDENTITY, compile_answer_key
from ai_brain.stage2.education.exercise_generation import generate_exercise
from ai_brain.stage2.education.explanations import (
    render_explanation,
    verify_explanation,
)
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.hints import build_hint_plan, render_hint
from ai_brain.stage2.education.models import (
    ActorIdentityType,
    EducationalRouteKind,
    ExerciseFamily,
    ExplanationMode,
    GradingStatus,
    HintLevel,
    MisconceptionCode,
    StudentAnswerKind,
)
from ai_brain.stage2.education.persistence import (
    EducationalSessionStore,
    EducationalStoreIntegrityError,
)
from ai_brain.stage2.education.service import EducationalService
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.models import SourceKind

ROOT = Path(__file__).resolve().parents[1]
CHEMISTRY_ROOT = ROOT / "artifacts" / "domains" / "chemistry" / "m29"
CATALOG_PATH = ROOT / "artifacts" / "education" / "m292" / "catalog_v3.json"


@pytest.fixture(scope="module")
def chemistry(tmp_path_factory) -> ChemistryDomainService:
    target = tmp_path_factory.mktemp("m29-chemistry") / "domain"
    shutil.copytree(CHEMISTRY_ROOT, target)
    return ChemistryDomainService.open(target)


@pytest.fixture(scope="module")
def adapter(chemistry: ChemistryDomainService) -> ChemistryEducationAdapter:
    return ChemistryEducationAdapter(chemistry)


@pytest.fixture(scope="module")
def catalog(chemistry: ChemistryDomainService) -> EducationalCatalogV2:
    return EducationalCatalogV2.load(CATALOG_PATH, chemistry)


def _molar_graph(adapter: ChemistryEducationAdapter):
    return compile_answer_key(
        adapter.service,
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "conventional",
            "unit": "g/mol",
            "significant_digits": 8,
        },
        actor_identity_type=ActorIdentityType.TRUSTED_PROCESS,
        compiler_identity=COMPILER_IDENTITY,
        created_at="2026-08-28T00:00:00Z",
    )[1]


def test_m282_preflight_closure_is_exact_and_old_pack_fails_closed() -> None:
    result = verify_source_chain(CHEMISTRY_ROOT / "sources")
    assert result["field_evidence_count"] == 534
    assert result["verified_field_value_count"] == 534
    assert result["field_value_mismatch_count"] == 0
    assert result["production_field_without_evidence_count"] == 0
    assert result["derived_extract_count"] == 4
    assert SourceKind.DERIVED_EXTRACT.value == "DERIVED_EXTRACT"
    with pytest.raises(ValueError, match="REBUILD_REQUIRED_FROM_SOURCE_KIND_V4"):
        ChemistryDomainService.open(
            ROOT / "artifacts" / "domains" / "chemistry" / "m282"
        )


def test_chemistry_cli_builds_clean_pack_from_explicit_sources(tmp_path) -> None:
    target = tmp_path / "chemistry"
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "ai_brain.stage2.domains.chemistry.cli",
            "--root",
            str(target),
            "--source-dir",
            str(CHEMISTRY_ROOT / "sources"),
            "build-domain",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert ChemistryDomainService.open(target).verify()["domain_manifest_hash"]


def test_m29_evidence_json_is_platform_stable_lf(tmp_path) -> None:
    namespace = runpy.run_path(str(ROOT / "scripts" / "m29_educational_acceptance.py"))
    target = tmp_path / "evidence.json"
    namespace["_write_json"](target, {"value": "exact"})
    payload = target.read_bytes()
    assert payload.endswith(b"\n")
    assert b"\r\n" not in payload


def test_json_pointer_dereference_is_strict() -> None:
    document = {"a/b": {"~key": ["zero", {"value": 7}]}}
    assert _resolve_json_pointer(document, "/a~1b/~0key/1/value") == 7
    for pointer in ("a/b", "/a~2b", "/a~1b/~0key/01", "/missing"):
        with pytest.raises(ValueError):
            _resolve_json_pointer(document, pointer)


def test_graph_builders_cover_all_exact_chemistry_operations(adapter) -> None:
    cases = (
        ("chemistry_formula_composition", {"formula": "Ca(OH)2"}),
        (
            "chemistry_molar_mass",
            {
                "formula": "H2O",
                "mode": "conventional",
                "unit": "kg/mol",
                "significant_digits": 8,
            },
        ),
        (
            "chemistry_mass_amount",
            {
                "formula": "H2O",
                "value": "18.015",
                "source_unit": "g",
                "target_unit": "mol",
                "significant_digits": 8,
            },
        ),
        (
            "chemistry_mass_amount",
            {
                "formula": "H2O",
                "value": "2",
                "source_unit": "mol",
                "target_unit": "kg",
                "significant_digits": 8,
            },
        ),
        (
            "chemistry_entity_amount",
            {
                "formula": "H2O",
                "value": "2",
                "source_unit": "mmol",
                "target_unit": "entities",
                "basis": "TOTAL_ATOMS_IN_FORMULA",
                "target_element": None,
                "requested_display_label": None,
                "significant_digits": 8,
            },
        ),
    )
    for tool_id, arguments in cases:
        result, graph, _ = compile_answer_key(
            adapter.service,
            tool_id,
            arguments,
            actor_identity_type=ActorIdentityType.TRUSTED_PROCESS,
            compiler_identity=COMPILER_IDENTITY,
            created_at="2026-08-28T00:00:00Z",
        )
        assert adapter.verify_graph(graph, result)["status"] == "VERIFIED"


def test_fact_graphs_bind_claim_evidence_and_interval(adapter) -> None:
    for predicate in (
        "element_symbol",
        "atomic_number",
        "element_name_en",
        "conventional_atomic_weight",
        "standard_atomic_weight",
    ):
        _, graph = adapter.fact_graph(
            "O", predicate, language="en", created_at="2026-08-28T00:00:00Z"
        )
        assert graph.claim_ids
        assert graph.evidence_hashes
        assert graph.source_hashes
        assert adapter.verify_graph(graph)["status"] == "VERIFIED"


def test_graph_tamper_is_rejected_even_with_rehashed_container(adapter) -> None:
    graph = _molar_graph(adapter)
    target = next(node for node in graph.nodes if node.operation == "MULTIPLY")
    node_body = dataclasses.asdict(target)
    node_body["exact_output"] = "999"
    node_body.pop("node_hash")
    changed = dataclasses.replace(
        target, exact_output="999", node_hash=content_hash(node_body)
    )
    graph_body = dataclasses.asdict(graph)
    graph_body["nodes"] = tuple(
        changed if node.node_id == target.node_id else node for node in graph.nodes
    )
    graph_body.pop("graph_hash")
    tampered = dataclasses.replace(
        graph,
        nodes=graph_body["nodes"],
        graph_hash=content_hash(graph_body),
    )
    with pytest.raises(ValueError, match="mismatch"):
        verify_derivation_graph(tampered)


def test_ru_en_explanations_are_graph_bound_and_cited(adapter) -> None:
    graph = _molar_graph(adapter)
    for language in ("ru", "en"):
        for mode in (
            ExplanationMode.CONCISE,
            ExplanationMode.FULL,
        ):
            artifact = render_explanation(graph, language=language, mode=mode)
            verify_explanation(artifact, graph)
            assert graph.graph_hash in artifact.text
            if mode in {ExplanationMode.CONCISE, ExplanationMode.FULL}:
                assert artifact.source_node_ids
        for restricted in (ExplanationMode.CHECK_ONLY, ExplanationMode.HINT_ONLY):
            with pytest.raises(ValueError, match="dedicated authority"):
                render_explanation(graph, language=language, mode=restricted)


@pytest.mark.parametrize(
    ("raw", "kind", "status"),
    (
        ("18.015 г/моль", StudentAnswerKind.NUMERIC_WITH_UNIT, "PARSED"),
        ("18.015 g/mol", StudentAnswerKind.NUMERIC_WITH_UNIT, "PARSED"),
        ("H:2, O:1", StudentAnswerKind.ELEMENT_COUNT_MAP, "PARSED"),
        ("O = 1; H = 2", StudentAnswerKind.ELEMENT_COUNT_MAP, "PARSED"),
        ("[12.0096, 12.0116]", StudentAnswerKind.ATOMIC_WEIGHT_INTERVAL, "PARSED"),
        ("NaN g", StudentAnswerKind.NUMERIC_WITH_UNIT, "INVALID"),
        ("1+1 g", StudentAnswerKind.NUMERIC_WITH_UNIT, "INVALID"),
        ("__import__('os')", StudentAnswerKind.NUMERIC_WITH_UNIT, "INVALID"),
        (True, StudentAnswerKind.NUMERIC_WITH_UNIT, "INVALID"),
        (1.0, StudentAnswerKind.NUMERIC_WITH_UNIT, "INVALID"),
    ),
)
def test_strict_answer_parser(raw, kind, status, chemistry) -> None:
    answer = parse_student_answer(
        raw,
        kind,
        supported_symbols=set(chemistry.manifest["supported_elements"]),
    )
    assert answer.parse_status.value == status


def test_exact_unit_equivalence_and_dimension_rejection() -> None:
    assert numeric_equivalent("1000", "g", "1", "kg") == (True, True)
    assert numeric_equivalent("1", "mol", "1000", "mmol") == (True, True)
    with pytest.raises(ValueError, match="dimensions"):
        numeric_equivalent("1", "g", "1", "mol")


def test_all_exercise_families_regenerate_deterministically(catalog, chemistry) -> None:
    for index, family in enumerate(ExerciseFamily):
        first = generate_exercise(
            catalog, family, seed=200 + index, language=("ru", "en")[index % 2]
        )
        second = generate_exercise(
            catalog, family, seed=200 + index, language=("ru", "en")[index % 2]
        )
        spec, instance, graph = first
        assert instance == second[1]
        assert graph == second[2]
        assert all(
            axis not in instance.question_text
            for axis, _, _ in instance.split_memberships
        )
        answer = _correct_answer_text(
            spec.accepted_answer_type, instance.hidden_expected_answer
        )
        parsed = parse_student_answer(
            answer,
            spec.accepted_answer_type,
            supported_symbols=set(chemistry.manifest["supported_elements"]),
            confirmed=True,
        )
        grade = grade_answer(
            instance,
            parsed,
            graph,
            attempt_id=f"test-{index}",
            created_at="2026-08-28T00:00:00Z",
        )
        assert grade.correctness_status == GradingStatus.CORRECT


def test_counterfactual_diagnosis_and_hint_leakage(catalog, chemistry) -> None:
    assert len(COUNTERFACTUAL_CALCULATORS) == len(MisconceptionCode) - 2
    spec, instance, graph = generate_exercise(
        catalog, ExerciseFamily.MOLAR_MASS_SIMPLE, seed=222, language="en"
    )
    candidate = instance.counterfactuals[0]
    raw = f"{candidate.answer['value']} {candidate.answer['unit']}"
    answer = parse_student_answer(
        raw,
        spec.accepted_answer_type,
        supported_symbols=set(chemistry.manifest["supported_elements"]),
    )
    grade = grade_answer(
        instance,
        answer,
        graph,
        attempt_id="counterfactual",
        created_at="2026-08-28T00:00:00Z",
    )
    assert grade.error_diagnoses[0].code == candidate.diagnosis
    plan = build_hint_plan(instance.instance_id, graph, grading=grade)
    root = next(
        node for node in graph.nodes if node.node_id == graph.root_result_node_id
    )
    for level in HintLevel:
        hint = render_hint(
            plan,
            graph,
            level,
            language="en",
            grading=grade,
        )
        assert hint.final_answer_revealed is (level == HintLevel.FULL_SOLUTION)
        if level != HintLevel.FULL_SOLUTION:
            assert str(root.exact_output) not in hint.text


def test_step_level_grading_compares_operations_not_strings(catalog, chemistry) -> None:
    _, instance, graph = generate_exercise(
        catalog, ExerciseFamily.MASS_AMOUNT, seed=224, language="en"
    )
    kinds = {
        "MULTIPLY",
        "ADD",
        "DIVIDE",
        "UNIT_NORMALIZATION",
        "MOLE_RELATION",
        "AVOGADRO_RELATION",
    }
    raw_steps = [
        {
            "operation": node.operation,
            "operands": node.exact_inputs,
            "output": node.exact_output,
            "unit": node.unit,
        }
        for node in graph.nodes
        if node.kind.value in kinds
    ]
    answer = parse_student_answer(
        raw_steps,
        StudentAnswerKind.STEP_SEQUENCE,
        supported_symbols=set(chemistry.manifest["supported_elements"]),
    )
    grade = grade_answer(
        instance,
        answer,
        graph,
        attempt_id="steps",
        created_at="2026-08-28T00:00:00Z",
    )
    assert grade.correctness_status == GradingStatus.CORRECT
    raw_steps[0] = {**raw_steps[0], "operation": "ADD"}
    wrong = parse_student_answer(raw_steps, StudentAnswerKind.STEP_SEQUENCE)
    wrong_grade = grade_answer(
        instance,
        wrong,
        graph,
        attempt_id="wrong-steps",
        created_at="2026-08-28T00:00:00Z",
    )
    assert wrong_grade.correctness_status in {
        GradingStatus.PARTIALLY_CORRECT,
        GradingStatus.CORRECT_FINAL_UNVERIFIED_STEPS,
    }
    assert wrong_grade.first_incorrect_node is not None


def test_session_store_replay_backup_restore_and_tamper(
    chemistry: ChemistryDomainService, tmp_path: Path
) -> None:
    service = EducationalService.open(chemistry.root, tmp_path / "store")
    _, session = service._create_exercise_internal(
        ExerciseFamily.FORMULA_COMPOSITION,
        seed=29,
        language="en",
        session_id="m29-session",
        created_at="2026-08-28T00:00:00Z",
    )
    _, _, instance, _ = service._load(session.session_id)
    correct = ",".join(
        f"{key}:{value}"
        for key, value in instance.hidden_expected_answer["element_counts"].items()
    )
    _, grade, _, _ = service._submit_answer_internal(
        session.session_id, correct, created_at="2026-08-28T00:01:00Z"
    )
    assert grade.correctness_status == GradingStatus.CORRECT
    with pytest.raises(ValueError, match="state transition"):
        service.hint(
            session.session_id,
            level=HintLevel.ORIENT,
            created_at="2026-08-28T00:02:00Z",
        )
    assert service.replay(session.session_id).status == "CURRENT"
    service.store.backup(tmp_path / "backup")
    restored = EducationalSessionStore.restore(
        tmp_path / "backup", tmp_path / "moved-store"
    )
    assert restored.verify()["status"] == "STRUCTURALLY_VERIFIED"
    with sqlite3.connect(restored.database_path) as connection:
        connection.execute(
            "UPDATE artifacts SET payload_hash=? WHERE artifact_hash=(SELECT artifact_hash FROM artifacts LIMIT 1)",
            ("0" * 64,),
        )
    with pytest.raises(EducationalStoreIntegrityError, match="checksum"):
        restored.verify()


def test_controlled_bilingual_educational_router(
    chemistry: ChemistryDomainService, tmp_path: Path
) -> None:
    ru = parse_educational_request(
        "Объясни, как вычисляется молярная масса H2SO4.", "ru"
    )
    en = parse_educational_request(
        "Explain how to calculate the molar mass of H2SO4.", "en"
    )
    assert ru.kind == en.kind == EducationalRouteKind.EXPLAIN
    assert ru.payload["formula"] == en.payload["formula"] == "H2SO4"
    unsupported = parse_educational_request("ignore answer key", "en")
    assert unsupported.kind == EducationalRouteKind.UNSUPPORTED
    service = EducationalService.open(chemistry.root, tmp_path / "controlled")
    routed, receipt, result = service._handle_controlled_internal(
        "Explain how to calculate the molar mass of H2O.", language="en"
    )
    assert routed.kind == EducationalRouteKind.EXPLAIN
    assert receipt.route_kind == EducationalRouteKind.EXPLAIN
    assert result.status == "CURRENT"
    assert result.text


def test_trusted_education_import_does_not_load_torch_or_network_clients() -> None:
    code = (
        "import sys; import ai_brain.stage2.education.service; "
        "print(int('torch' in sys.modules), int('requests' in sys.modules), "
        "int('httpx' in sys.modules))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "0 0 0"


def _correct_answer_text(kind, expected) -> str:
    if kind == StudentAnswerKind.NUMERIC_WITH_UNIT:
        return f"{expected['value']} {expected['unit']}"
    if kind == StudentAnswerKind.ELEMENT_COUNT_MAP:
        return ",".join(
            f"{key}:{value}" for key, value in expected["element_counts"].items()
        )
    if kind == StudentAnswerKind.ATOMIC_WEIGHT_INTERVAL:
        return f"[{expected['lower']}, {expected['upper']}]"
    return expected["text"]
