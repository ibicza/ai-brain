from __future__ import annotations

import itertools
import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.rules.ast import (
    RegisterState,
    exact_closed_loop,
    render_canonical_program,
)
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import property_verify
from ai_brain.stage1.approval import approve_candidate
from ai_brain.stage1.audit import AuditLog
from ai_brain.stage1.controlled_language import parse_controlled_language
from ai_brain.stage1.execution import execute_rule
from ai_brain.stage1.known_family_compiler import compile_known_family
from ai_brain.stage1.models import ProposalStatus, SemanticFamily
from ai_brain.stage1.service import Stage1Service
from ai_brain.stage1.specifications import build_family_specification


def structural_specs():
    yield SemanticFamily.NOOP, (), None
    for source in "ABCD":
        yield SemanticFamily.CLEAR, (source,), None
    for source, destination in itertools.permutations("ABCD", 2):
        yield SemanticFamily.DRAIN, (source,), destination
    for first, second, destination in itertools.permutations("ABCD", 3):
        yield SemanticFamily.MERGE_TWO, (first, second), destination
    for first, second, third, destination in itertools.permutations("ABCD", 4):
        yield SemanticFamily.MERGE_THREE, (first, second, third), destination
    for dropped, source, destination in itertools.permutations("ABCD", 3):
        yield SemanticFamily.DROP_THEN_TRANSFER, (dropped, source), destination


def language_command(
    family: SemanticFamily,
    sources: tuple[str, ...],
    destination: str | None,
    language: str,
    *,
    extended: bool = False,
) -> str:
    changed = set(sources) | ({destination} if destination else set())
    preserve = [role for role in "ABCD" if role not in changed]
    if language == "en":
        move = "convey" if extended else "move"
        clear = "purge" if extended else "clear"
        preserve_text = (
            f"retain {', '.join(preserve)} untouched"
            if extended and preserve
            else f"leave {', '.join(preserve)} unchanged"
            if preserve
            else "no register is required to remain unchanged"
        )
        stop = "conclude" if extended else "stop"
        if family == SemanticFamily.NOOP:
            return "Leave all registers unchanged; stop immediately."
        if family == SemanticFamily.CLEAR:
            operation = f"{clear} every item from {sources[0]}"
        elif family == SemanticFamily.DROP_THEN_TRANSFER:
            operation = (
                f"first {clear} {sources[0]}, then {move} every item from "
                f"{sources[1]} into {destination}"
            )
        else:
            operation = (
                f"{move} every item from {' and '.join(sources)} into {destination}"
            )
        return (
            f"{operation}; {preserve_text}; {stop} when "
            f"{' and '.join(sources)} are empty."
        )
    move = "переправь" if extended else "перенеси"
    clear = "ликвидируй" if extended else "очисти"
    preserve_text = (
        f"сбереги {', '.join(preserve)} как есть"
        if extended and preserve
        else f"{', '.join(preserve)} не изменяй"
        if preserve
        else "нет регистра, который требуется сохранить без изменений"
    )
    stop = "закончи операцию" if extended else "остановись"
    if family == SemanticFamily.NOOP:
        return "Оставь все регистры без изменений; сразу остановись."
    if family == SemanticFamily.CLEAR:
        operation = f"{clear} все элементы из {sources[0]}"
    elif family == SemanticFamily.DROP_THEN_TRANSFER:
        operation = (
            f"сначала {clear} {sources[0]}, затем {move} все элементы из "
            f"{sources[1]} в {destination}"
        )
    else:
        operation = f"{move} все элементы из {' и '.join(sources)} в {destination}"
    return (
        f"{operation}; {preserve_text}; {stop}, когда {' и '.join(sources)} опустеют."
    )


def test_exact_89_structural_specifications() -> None:
    rows = list(structural_specs())
    assert len(rows) == 89
    for family, sources, destination in rows:
        specification = build_family_specification(
            family, sources=sources, destination=destination
        )
        program = compile_known_family(specification, family)
        assert property_verify(program, specification, large=True).accepted
        result = exact_closed_loop(
            program, RegisterState({"R0": 2, "R1": 3, "R2": 4, "R3": 1000})
        )
        assert not result["invalid"]
        assert result["actions"][-1] == "H"


@pytest.mark.parametrize("language", ("en", "ru"))
@pytest.mark.parametrize("extended", (False, True))
def test_all_structural_specs_parse_bilingually(language: str, extended: bool) -> None:
    for family, sources, destination in structural_specs():
        outcome = parse_controlled_language(
            language_command(family, sources, destination, language, extended=extended),
            language,
        )
        assert outcome.status == ProposalStatus.SUPPORTED_FOR_REVIEW
        assert outcome.family == family
        assert outcome.specification == build_family_specification(
            family, sources=sources, destination=destination
        )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Copy A into B; leave C and D unchanged; stop when A is empty.",
            "UNSUPPORTED",
        ),
        (
            "Move every item from A; leave C and D unchanged; stop when A is empty.",
            "CLARIFICATION_REQUIRED",
        ),
        (
            "Move A into B; leave it unchanged; stop when A is empty.",
            "CLARIFICATION_REQUIRED",
        ),
        ("Move A into B and preserve A; stop when A is empty.", "CONTRADICTORY"),
        ("Please make the state better.", "UNSUPPORTED"),
    ],
)
def test_negative_language_battery(text: str, expected: str) -> None:
    assert parse_controlled_language(text, "en").status == expected


def test_bounded_clarification_preserves_action(tmp_path: Path) -> None:
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    proposal = service.propose_language(
        "Move every item from A; leave C and D unchanged; stop when A is empty.",
        language="en",
    )
    assert proposal.status == ProposalStatus.CLARIFICATION_REQUIRED
    updated = service.clarify(proposal, "destination=B")
    assert updated.status == ProposalStatus.EDITED
    assert updated.specification is not None
    assert updated.specification.transfers == (("A", "B"),)
    with pytest.raises(ValueError, match="not awaiting clarification"):
        service.clarify(updated, "destination=C")


def test_pronoun_and_order_clarifications_are_semantic(tmp_path: Path) -> None:
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    pronoun = service.propose_language(
        "Move every item from A into B; leave it unchanged; stop when A is empty.",
        language="en",
    )
    resolved = service.clarify(pronoun, "reference=C")
    assert resolved.specification is not None
    assert resolved.specification.preserve == ("C",)

    order = service.propose_language(
        "Clear A and move every item from B into C; leave D unchanged; "
        "stop when A and B are empty.",
        language="en",
    )
    assert service.clarify(order, "order=A,B").status == ProposalStatus.EDITED
    assert service.clarify(order, "order=B,A").status == ProposalStatus.CONTRADICTORY


def complete_merge(service: Stage1Service):
    proposal = service.propose_language(
        "Move every item from A and B into C; leave D unchanged; "
        "stop when A and B are empty.",
        language="en",
    )
    proposal, _ = service.review(proposal)
    proposal, candidate = service.verify(proposal)
    proposal, approval = service.approve(
        proposal, candidate, identity="acceptance-user"
    )
    proposal, record = service.install(proposal, candidate, approval)
    return proposal, candidate, approval, record


def test_end_to_end_mandatory_example_and_audit(tmp_path: Path) -> None:
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    proposal, _, _, record = complete_merge(service)
    proposal, result = service.execute(
        proposal, record.rule_id, {"R0": 2, "R1": 3, "R2": 4, "R3": 5}
    )
    assert result.final_state == {"R0": 0, "R1": 0, "R2": 9, "R3": 5}
    assert proposal.status == ProposalStatus.EXECUTED
    events = service.audit.replay()
    assert [item.sequence for item in events] == list(range(1, len(events) + 1))
    assert events[-1].event_type == "RULE_EXECUTED"


def test_trusted_canonical_dsl_path(tmp_path: Path) -> None:
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    specification = build_family_specification(
        SemanticFamily.DRAIN, sources=("C",), destination="A"
    )
    dsl = render_canonical_program(compile_known_family(specification))
    proposal = service.propose_dsl(dsl, asdict(specification))
    proposal, _ = service.review(proposal)
    proposal, candidate = service.verify(proposal)
    assert candidate.compiler_name == "trusted_canonical_dsl_v1"
    assert candidate.verification_evidence["accepted"]


def test_generic_cegis_fallback_is_public_and_verified(tmp_path: Path) -> None:
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    specification = build_family_specification(SemanticFamily.CLEAR, sources=("A",))
    proposal = service.propose_form(asdict(specification))
    proposal = replace(proposal, semantic_family=None)
    proposal, _ = service.review(proposal)
    _, candidate = service.verify(proposal)
    assert candidate.compiler_name == "frozen_public_generic_cegis"
    assert candidate.verification_evidence["accepted"]


def test_approval_security_rejects_stale_and_tampered_data(tmp_path: Path) -> None:
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    proposal = service.propose_language(
        "Clear every item from A; leave B, C and D unchanged; stop when A is empty.",
        language="en",
    )
    proposal, _ = service.review(proposal)
    proposal, candidate = service.verify(proposal)
    approval = approve_candidate(proposal, candidate, identity="reviewer")
    with pytest.raises(ValueError, match="Stale candidate"):
        approve_candidate(
            replace(proposal, revision=proposal.revision + 1),
            candidate,
            identity="reviewer",
        )
    approved, _ = service.approve(proposal, candidate, identity="reviewer")
    with pytest.raises(ValueError, match="candidate_hash mismatch"):
        service.install(
            approved,
            candidate,
            replace(approval, candidate_hash="0" * 64),
        )
    with pytest.raises(ValueError, match="evidence_hash mismatch"):
        service.install(
            approved,
            replace(candidate, verification_evidence={"accepted": False}),
            approval,
        )
    with pytest.raises(ValueError, match="candidate_hash mismatch"):
        service.install(
            approved,
            replace(candidate, candidate_dsl=candidate.candidate_dsl + "\n"),
            approval,
        )
    with pytest.raises(ValueError, match="Explicit APPROVE"):
        service.install(
            approved,
            candidate,
            replace(approval, decision="REJECT"),
        )


def test_rule_memory_atomic_backup_corruption_and_recovery(tmp_path: Path) -> None:
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    _, _, _, record = complete_merge(service)
    memory = RuleMemory.load(service.memory_path)
    memory.save(service.memory_path)
    backup = service.memory_path.with_suffix(".json.bak")
    assert backup.exists()
    service.memory_path.write_text('{"broken":', encoding="utf-8")
    recovered = RuleMemory.load_with_backup(service.memory_path)
    assert record.rule_id in recovered.records
    with pytest.raises(ValueError, match="Corrupt RuleMemory"):
        RuleMemory.load(service.memory_path)


def test_rule_memory_100_semantic_versions(tmp_path: Path) -> None:
    specification = build_family_specification(
        SemanticFamily.DRAIN, sources=("A",), destination="B"
    )
    program = compile_known_family(specification)
    evidence = {"accepted": True, "status": VerificationStatus.PROPERTY_VERIFIED}
    memory = RuleMemory()
    active_rule_id = ""
    for index in range(100):
        if index:
            memory.deprecate(active_rule_id)
        record = memory.add(
            program,
            specification,
            VerificationStatus.PROPERTY_VERIFIED,
            provenance=f"acceptance-version-{index + 1}",
            verification_evidence=evidence,
        )
        active_rule_id = record.rule_id
    path = tmp_path / "scale_memory.json"
    memory.save(path)
    loaded = RuleMemory.load(path)
    assert len(loaded.records) == 100
    assert len(loaded.active_records()) == 1
    assert [item.version for item in loaded.records.values()] == list(range(1, 101))
    result = execute_rule(
        path,
        loaded.active_records()[0].rule_id,
        {"R0": 1000, "R1": 2, "R2": 3, "R3": 4},
    )
    assert result.final_state == {"R0": 0, "R1": 1002, "R2": 3, "R3": 4}


def test_audit_tamper_is_detected(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.append("ONE", {"value": 1})
    audit.append("TWO", {"value": 2})
    text = audit.path.read_text(encoding="utf-8").replace('"value": 1', '"value": 9')
    audit.path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="Audit hash mismatch"):
        audit.replay()


def test_trusted_stage1_import_does_not_initialize_torch() -> None:
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-c",
        "import sys; import ai_brain.stage1; assert 'torch' not in sys.modules",
    ]
    result = subprocess.run(
        command, cwd=root, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_production_package_has_no_research_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "ai_brain" / "stage1"
    banned = (
        "torch",
        "fair_model",
        "training",
        "tokenizer",
        "hidden",
        "datasets",
        "runs",
    )
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not any(
            f"import {term}" in text or f"from ai_brain.{term}" in text
            for term in banned
        )


def test_rule_memory_checksum_rejects_silent_tampering(tmp_path: Path) -> None:
    service = Stage1Service(
        memory_path=tmp_path / "memory.json", audit_path=tmp_path / "audit.jsonl"
    )
    complete_merge(service)
    row = json.loads(service.memory_path.read_text(encoding="utf-8"))
    row["records"][0]["provenance"] = "tampered"
    service.memory_path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        RuleMemory.load(service.memory_path)
