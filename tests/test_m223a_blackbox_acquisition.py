from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_brain.rules import blackbox
from ai_brain.rules.blackbox import (
    PublicAcquisitionTask,
    acquire_public_task,
    safe_rule_route,
    specification_signature,
)
from ai_brain.rules.grammar import blackbox_candidate_pool, generic_transfer_one
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import property_verify
from scripts import m223a_evaluator_process as evaluator


def _transfer_spec() -> ProgramSpecification:
    return ProgramSpecification(
        transfers=(("A", "B"),),
        preserve=("C", "D"),
        terminate_when_empty=("A",),
        allowed_variables=("A", "B"),
        allowed_primitives=("HALT", "MOVE_ONE"),
        phase_constraints=(("MOVE_ONE", "A", "B"),),
    )


def test_acquisition_import_and_source_firewall() -> None:
    paths = (
        ROOT / "scripts" / "m223a_acquisition_process.py",
        ROOT / "src" / "ai_brain" / "rules" / "blackbox.py",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "m223_hidden_evaluator" not in source
    assert "HiddenTarget" not in source
    assert "target.program" not in source
    assert "fingerprint(target" not in source


def test_acquisition_signature_has_no_hidden_target() -> None:
    signature = str(inspect.signature(acquire_public_task))
    assert "HiddenTarget" not in signature
    assert set(inspect.signature(acquire_public_task).parameters) == {
        "task",
        "candidates",
    }


def test_full_spec_calls_property_verify_with_public_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _transfer_spec()
    seen = []
    original = blackbox.property_verify

    def recording_verify(program, supplied_spec, *, large=False):
        seen.append((program, supplied_spec, large))
        return original(program, supplied_spec, large=large)

    monkeypatch.setattr(blackbox, "property_verify", recording_verify)
    result = acquire_public_task(
        PublicAcquisitionTask("opaque", "full_spec", spec, candidate_budget=6),
        blackbox_candidate_pool(6),
    )
    assert result.status == VerificationStatus.PROPERTY_VERIFIED
    assert seen
    assert all(item[1] is spec for item in seen)
    assert result.candidates_to_first_verified == 3


def test_acquisition_runs_before_evaluator_sees_target_ast() -> None:
    request = PublicAcquisitionTask(
        "opaque", "full_spec", _transfer_spec(), candidate_budget=6
    ).to_json()
    completed = subprocess.run(
        [sys.executable, "scripts/m223a_acquisition_process.py", "acquire"],
        cwd=ROOT,
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
    )
    output = json.loads(completed.stdout)
    assert output["candidate_ast"]
    target = generic_transfer_one("A", "B", name="evaluator_only_after_return")
    assert evaluator._semantic_correct(blackbox.parse_result_program(output), target)


def test_rule_memory_requires_nonempty_spec_and_verifier_evidence() -> None:
    program = generic_transfer_one("A", "B", name="verified")
    spec = _transfer_spec()
    with pytest.raises(ValueError, match="non-empty"):
        RuleMemory().add(
            program,
            ProgramSpecification(),
            VerificationStatus.PROPERTY_VERIFIED,
            verification_evidence=property_verify(program, spec),
        )
    with pytest.raises(ValueError, match="verifier evidence"):
        RuleMemory().add(program, spec, VerificationStatus.PROPERTY_VERIFIED)
    RuleMemory().add(
        program,
        spec,
        VerificationStatus.PROPERTY_VERIFIED,
        verification_evidence=property_verify(program, spec),
    )


def test_balanced_public_benchmark_has_no_hidden_behavior() -> None:
    manifest = evaluator.build_benchmark()
    assert manifest["heldout_templates"] == 200
    assert manifest["clause_count_distribution"] == {1: 50, 2: 50, 3: 50, 4: 50}
    assert manifest["max_family_fraction"] <= 0.25
    assert manifest["unique_program_templates"] == 6
    assert manifest["structurally_unique_200_templates"] is False
    assert all(value == 0 for value in manifest["public_forbidden_key_hits"].values())
    public_row = json.loads(
        evaluator.PUBLIC_PATH.read_text(encoding="utf-8").splitlines()[0]
    )
    serialized = json.dumps(public_row)
    for forbidden in (
        "program",
        "fingerprint",
        "semantic_hash",
        "family",
        "clause_count",
    ):
        assert f'"{forbidden}"' not in serialized


def test_false_accept_uses_independent_verifier_and_counterexample() -> None:
    source = (ROOT / "scripts" / "m223a_evaluator_process.py").read_text(
        encoding="utf-8"
    )
    assert "known_incorrect and verifier_accepted" in source
    assert "accepted = mutant_fp == target_fp" not in source


def test_practical_novelty_router_never_uses_nearest_wrong_rule() -> None:
    known = _transfer_spec()
    view = (
        {
            "rule_id": "rule-known",
            "specification_signature": specification_signature(known),
        },
    )
    assert safe_rule_route(known, view)["route"] == "RULE_MEMORY"
    novel = ProgramSpecification(drops=("A",), terminate_when_empty=("A",))
    assert safe_rule_route(novel, view) == {
        "route": "CEGIS",
        "rule_id": None,
        "confidence": 0.0,
    }


def test_persisted_blackbox_run_uses_production_path_and_independent_scorer() -> None:
    analysis_path = evaluator.ANALYSIS_PATH
    if not analysis_path.exists():
        pytest.skip("M-22.3a benchmark has not been run yet")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert analysis["processes"]["process_ids_distinct"] is True
    assert len(analysis["score"]["rows"]) >= 200
    assert analysis["score"]["summary"]["semantic_correct"] >= 0.95
    assert analysis["mutation"]["summary"]["total_mutations"] >= 10_000
    assert analysis["mutation"]["summary"]["known_incorrect_count"] >= 10_000
    assert analysis["mutation"]["summary"]["unique_target_programs"] >= 100
    assert analysis["mutation"]["summary"]["false_accept_count"] == 0
    assert len(analysis["memory"]["sequential_rows"]) == 100
    assert analysis["memory"]["sequential_100_retention"] == 1.0
    assert analysis["decision"] == "OUTCOME B"


def test_final_scoring_entrypoint_is_evaluator_only() -> None:
    acquisition_source = (ROOT / "scripts" / "m223a_acquisition_process.py").read_text(
        encoding="utf-8"
    )
    evaluator_source = (ROOT / "scripts" / "m223a_evaluator_process.py").read_text(
        encoding="utf-8"
    )
    assert "score_acquisition" not in acquisition_source
    assert (
        '"command", choices=("build", "run-all", "score", "finalize", "build-report")'
        in evaluator_source
    )
