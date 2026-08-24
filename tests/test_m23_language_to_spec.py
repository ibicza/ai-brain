from __future__ import annotations

import inspect
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import torch

from ai_brain.language_to_spec.approval import (
    Approval,
    ApprovalDecision,
    edit_proposal,
    store_approved_language_rule,
)
from ai_brain.language_to_spec.clarification import clarification_for, resolve_one_round
from ai_brain.language_to_spec.deterministic import parse_controlled_language
from ai_brain.language_to_spec.generator import (
    DEFAULT_SPLIT_COUNTS,
    generate_language_dataset,
    load_language_rows,
)
from ai_brain.language_to_spec.json_control import valid_control_answers
from ai_brain.language_to_spec.model import (
    TypedLanguageToSpecParser,
    TypedParserConfig,
    encode_texts,
    train_typed_parser,
)
from ai_brain.language_to_spec.schema import (
    LanguageProposal,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    build_family_specification,
    canonical_specification_json,
    proposal_from_json,
    proposal_to_json,
    strict_specification_from_json,
    validate_specification,
)
from ai_brain.rules.blackbox import PublicAcquisitionTask, acquire_public_task
from ai_brain.rules.grammar import blackbox_candidate_pool
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.statuses import VerificationStatus

ROOT = Path(__file__).resolve().parents[1]


def test_exact_program_specification_and_proposal_schema() -> None:
    spec = build_family_specification(
        SemanticFamily.MERGE_TWO, sources=("A", "B"), destination="C"
    )
    row = json.loads(json.dumps(asdict(spec)))
    assert strict_specification_from_json(row) == spec
    with pytest.raises(ValueError, match="schema mismatch"):
        strict_specification_from_json({**row, "extra": True})
    proposal = LanguageProposal(
        ParseStatus.SUPPORTED,
        "en",
        "Move A and B into C.",
        spec,
        SemanticFamily.MERGE_TWO,
        confidence=1.0,
        parser_name="test",
    )
    assert proposal_from_json(proposal_to_json(proposal)) == proposal


@pytest.mark.parametrize(
    ("ru", "en"),
    [
        (
            "Перемести все элементы из A и B в C. Не изменяй D. Заверши работу, когда A и B опустеют.",
            "Move every item from A and B into C. Leave D unchanged. Stop when A and B are empty.",
        ),
        ("Очисти A.", "Clear all items from A."),
    ],
)
def test_ru_en_equivalent_prompts_emit_equal_specifications(ru: str, en: str) -> None:
    ru_result = parse_controlled_language(ru, language="ru")
    en_result = parse_controlled_language(en, language="en")
    assert ru_result.status == en_result.status == ParseStatus.SUPPORTED
    assert canonical_specification_json(
        ru_result.specification
    ) == canonical_specification_json(en_result.specification)


def test_variable_permutation_and_preserve_extraction() -> None:
    result = parse_controlled_language(
        "Move every item from D and B into A. Leave C unchanged. Stop when D and B are empty.",
        language="en",
    )
    assert result.status == ParseStatus.SUPPORTED
    assert result.specification.transfers == (("D", "A"), ("B", "A"))
    assert result.specification.preserve == ("C",)


def test_negation_scope_and_contradiction_are_not_accepted() -> None:
    contradiction = parse_controlled_language(
        "Move all items from A into C, but leave A unchanged.", language="en"
    )
    assert contradiction.status == ParseStatus.CONTRADICTORY
    assert contradiction.issues[0].code == ValidationCode.PRESERVE_TRANSFER_CONFLICT
    ambiguous = parse_controlled_language(
        "Перемести всё из A в C, затем очисти его.", language="ru"
    )
    assert ambiguous.status == ParseStatus.AMBIGUOUS
    assert ambiguous.issues[0].code == ValidationCode.AMBIGUOUS_PRONOUN


def test_missing_destination_and_unsupported_operation() -> None:
    missing = parse_controlled_language("Move every item from A.", language="en")
    assert missing.status == ParseStatus.AMBIGUOUS
    assert missing.issues[0].code == ValidationCode.MISSING_DESTINATION
    unsupported = parse_controlled_language(
        "Swap the contents of A and B.", language="en"
    )
    assert unsupported.status == ParseStatus.UNSUPPORTED
    assert unsupported.issues[0].code == ValidationCode.UNSUPPORTED_OPERATION


def test_clarification_targets_field_and_resolves_once() -> None:
    proposal = parse_controlled_language("Move every item from A.", language="en")
    question = clarification_for(proposal)
    assert question is not None
    assert question.code == ValidationCode.MISSING_DESTINATION
    assert "A" in question.question
    resolved = resolve_one_round(proposal, "C")
    assert resolved.status == ParseStatus.SUPPORTED
    assert resolved.specification.transfers == (("A", "C"),)


def test_approval_is_required_and_edit_requires_matching_reverification() -> None:
    proposal = parse_controlled_language(
        "Move every item from A into B. Leave C and D unchanged.", language="en"
    )
    acquisition = acquire_public_task(
        PublicAcquisitionTask(
            "approval-test", "full_spec", proposal.specification, candidate_budget=8
        ),
        blackbox_candidate_pool(8),
    )
    assert acquisition.status == VerificationStatus.PROPERTY_VERIFIED
    memory = RuleMemory()
    with pytest.raises(ValueError, match="APPROVE"):
        store_approved_language_rule(
            memory=memory,
            proposal=proposal,
            acquisition=acquisition,
            approval=Approval(
                ApprovalDecision.REJECT,
                "tester",
                "TRUSTED_SUPERVISOR",
                canonical_specification_json(proposal.specification),
            ),
        )
    assert not memory.records
    edited = edit_proposal(
        proposal,
        replace(proposal.specification, preserve=("A", "C", "D")),
    )
    assert validate_specification(edited.specification)
    with pytest.raises(ValueError, match="validation failed"):
        store_approved_language_rule(
            memory=memory,
            proposal=edited,
            acquisition=acquisition,
            approval=Approval(
                ApprovalDecision.APPROVE,
                "tester",
                "TRUSTED_SUPERVISOR",
                canonical_specification_json(edited.specification),
            ),
        )
    assert not memory.records


def test_language_frontend_has_no_hidden_evaluator_import() -> None:
    package = ROOT / "src" / "ai_brain" / "language_to_spec"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in package.glob("*.py")
    )
    assert "m223a_evaluator_process" not in source
    assert "HiddenTarget" not in source
    assert "target.program" not in source


def test_heldout_isolation_and_no_model_visible_ids(tmp_path: Path) -> None:
    counts = {name: (240 if name == "train" else 24) for name in DEFAULT_SPLIT_COUNTS}
    manifest = generate_language_dataset(tmp_path, split_counts=counts)
    assert manifest["normalized_text_globally_unique"] is True
    assert manifest["model_visible_sample_id_hits"] == 0
    assert (
        manifest["train_overlap_audit"]["test_lexical_holdout"]["lexical_family"] == 0
    )
    train = load_language_rows(tmp_path / "train.jsonl")
    lexical = load_language_rows(tmp_path / "test_lexical_holdout.jsonl")
    assert {row["lexical_family"] for row in train} == {"train"}
    assert {row["lexical_family"] for row in lexical} == {"holdout"}
    assert not any("sample" in row["text"].casefold() for row in train + lexical)


def test_json_control_outputs_are_strict_schema_values() -> None:
    answers = valid_control_answers()
    assert len(answers) > 90
    for answer in answers:
        payload = json.loads(answer)
        ParseStatus(payload["status"])
        if payload["specification"] is not None:
            strict_specification_from_json(payload["specification"])


def test_typed_parser_forward_and_tiny_training_smoke(tmp_path: Path) -> None:
    config = TypedParserConfig(
        max_bytes=192, d_model=32, num_layers=1, num_heads=4, ffn_dim=64, dropout=0.0
    )
    model = TypedLanguageToSpecParser(config)
    ids, mask = encode_texts(
        ["Move A into B.", "Перемести A в B."],
        max_bytes=config.max_bytes,
        device=torch.device("cpu"),
    )
    outputs = model(ids, mask)
    assert outputs["status"].shape == (2, 4)
    assert outputs["phase_kind"].shape == (2, 3, 3)

    data_dir = tmp_path / "data"
    counts = {name: (60 if name == "train" else 12) for name in DEFAULT_SPLIT_COUNTS}
    generate_language_dataset(data_dir, split_counts=counts)
    result = train_typed_parser(
        train_path=data_dir / "train.jsonl",
        validation_path=data_dir / "validation.jsonl",
        output_dir=tmp_path / "run",
        seed=23,
        steps=2,
        batch_size=4,
        cpu=True,
        config=config,
    )
    assert Path(result["checkpoint"]).exists()
    assert result["parameter_count"] > 0


def test_parser_public_signature_cannot_accept_evaluator_target() -> None:
    signature = inspect.signature(parse_controlled_language)
    assert set(signature.parameters) == {"text", "language"}
