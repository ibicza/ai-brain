from __future__ import annotations

import inspect
import random
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import torch

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language_to_spec.approval import (
    Approval,
    ApprovalDecision,
    store_approved_language_rule,
)
from ai_brain.language_to_spec.binding import acquire_with_concrete_binding
from ai_brain.language_to_spec.equivalence import (
    reversed_merge_order,
    semantic_specification_equal,
    structural_specification_equal,
)
from ai_brain.language_to_spec.fair_clarification import (
    clarification_from_raw,
    resolve_clarification_state,
)
from ai_brain.language_to_spec.fair_data import (
    FAIR_SPLIT_COUNTS,
    generate_fair_language_dataset,
)
from ai_brain.language_to_spec.fair_deterministic import (
    frozen_lexicon_items,
    holdout_lexicon_items,
    parse_fair_controlled_language,
)
from ai_brain.language_to_spec.fair_model import (
    FactorizedLanguageToSpecParserV2,
    InputTooLongError,
    StructuredPrediction,
    _decode_factorized,
    apply_calibration,
    build_candidate,
    calibrate_fail_closed,
    clause_order_augment,
    encode_texts_v2,
    make_config,
)
from ai_brain.language_to_spec.generator import load_language_rows
from ai_brain.language_to_spec.schema import (
    VARIABLES,
    LanguageProposal,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    build_family_specification,
    canonical_specification_json,
)
from ai_brain.rules.ast import parse_canonical_dsl, program_variables
from ai_brain.rules.memory import RuleMemory

ROOT = Path(__file__).resolve().parents[1]
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "m23_ru_en_bpe_8k.json"


@pytest.fixture(scope="module")
def fair_dataset(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    output = tmp_path_factory.mktemp("m231_fair")
    counts = {name: (600 if name == "train" else 60) for name in FAIR_SPLIT_COUNTS}
    manifest = generate_fair_language_dataset(
        output,
        tokenizer_path=TOKENIZER_PATH,
        split_counts=counts,
        seed=23_101,
    )
    return output, manifest


def test_language_family_parity_and_balance_regression(
    fair_dataset: tuple[Path, dict],
) -> None:
    _, manifest = fair_dataset
    matrix = manifest["splits"]["train"]["language_family"]
    for family in SemanticFamily:
        ru = matrix[f"ru|{family}"]
        en = matrix[f"en|{family}"]
        assert ru > 0 and en > 0
        assert abs(ru - en) / max(ru, en) <= 0.01
    assert manifest["splits"]["train"]["language_family_mutual_information_bits"] == 0
    validation = manifest["splits"]["validation_train_surface"]["language_family"]
    for family in SemanticFamily:
        assert validation[f"ru|{family}"] == validation[f"en|{family}"]


def test_clause_order_augmentation_preserves_visible_clause_multiset() -> None:
    row = {
        "text": "Move A into B. Preserve C and D. Stop when A is empty.",
        "prompt": "Move A into B. Preserve C and D. Stop when A is empty.",
    }
    augmented = clause_order_augment(row, random.Random(7), probability=1.0)
    expected = {"Move A into B.", "Preserve C and D.", "Stop when A is empty."}
    actual = {
        clause.strip() + "."
        for clause in augmented["text"].split(".")
        if clause.strip()
    }
    assert actual == expected
    assert augmented["text"] != row["text"]
    assert augmented["prompt"] == augmented["text"]


def test_every_supported_train_spec_is_bilingual(
    fair_dataset: tuple[Path, dict],
) -> None:
    path, manifest = fair_dataset
    assert manifest["all_supported_train_specs_bilingual"] is True
    rows = load_language_rows(path / "train.jsonl")
    languages_by_spec: dict[str, set[str]] = {}
    for row in rows:
        if row["status"] != str(ParseStatus.SUPPORTED):
            continue
        languages_by_spec.setdefault(row["answer"], set()).add(row["language"])
    assert languages_by_spec
    assert all(languages == {"ru", "en"} for languages in languages_by_spec.values())


def test_strict_explicitness_and_incomplete_is_ambiguous(
    fair_dataset: tuple[Path, dict],
) -> None:
    path, _ = fair_dataset
    supported = [
        row
        for row in load_language_rows(path / "train.jsonl")
        if row["status"] == str(ParseStatus.SUPPORTED)
    ]
    for row in supported:
        metadata = row["metadata"]
        assert metadata["strict_complete"]
        assert metadata["explicit_operation"]
        assert metadata["explicit_sources"]
        assert metadata["explicit_destination"]
        assert metadata["explicit_preserve"]
        assert metadata["explicit_termination"]
        assert metadata["explicit_order"]
    incomplete = load_language_rows(path / "test_ambiguous.jsonl")
    assert all(row["status"] == str(ParseStatus.AMBIGUOUS) for row in incomplete)
    assert all(not row["metadata"]["strict_complete"] for row in incomplete)


def test_lexical_template_holdout_and_visible_id_audits(
    fair_dataset: tuple[Path, dict],
) -> None:
    _, manifest = fair_dataset
    assert frozen_lexicon_items().isdisjoint(holdout_lexicon_items())
    assert manifest["lexical_holdout_absent_from_train_lexicon"]
    assert manifest["train_overlap_audit"]["test_lexical_holdout"]["lexical_items"] == 0
    assert manifest["train_overlap_audit"]["test_template_holdout"]["template_ids"] == 0
    assert manifest["model_visible_id_hits"] == 0


def test_bilingual_pairs_have_equal_targets(fair_dataset: tuple[Path, dict]) -> None:
    path, manifest = fair_dataset
    assert manifest["paired_targets_semantically_equal"]
    rows = load_language_rows(path / "test_cross_language.jsonl")
    pairs: dict[str, list[dict]] = {}
    for row in rows:
        pairs.setdefault(row["metadata"]["pair_id"], []).append(row)
    assert all(
        len(pair) == 2
        and {row["language"] for row in pair} == {"ru", "en"}
        and len({row["answer"] for row in pair}) == 1
        for pair in pairs.values()
    )


def test_byte_and_bpe_paths_are_distinct_and_never_truncate() -> None:
    text = "Перемести всё из A в B. Не изменяй C и D."
    byte_config = make_config(
        candidate_kind="factorized", encoding="byte", tokenizer_path=None
    )
    bpe_config = make_config(
        candidate_kind="factorized", encoding="bpe", tokenizer_path=TOKENIZER_PATH
    )
    byte_ids, _, byte_lengths = encode_texts_v2(
        [text], config=byte_config, device=torch.device("cpu")
    )
    bpe_ids, _, bpe_lengths = encode_texts_v2(
        [text], config=bpe_config, device=torch.device("cpu")
    )
    assert byte_config.vocab_size == 258
    assert (
        bpe_config.vocab_size == ByteLevelBpeTokenizer.load(TOKENIZER_PATH).vocab_size
    )
    assert byte_lengths != bpe_lengths
    assert byte_ids[0, 1].item() != bpe_ids[0, 1].item()
    with pytest.raises(InputTooLongError, match="configured maximum"):
        encode_texts_v2(
            [text],
            config=replace(byte_config, max_length=4),
            device=torch.device("cpu"),
        )


def test_calibration_fails_closed() -> None:
    config = replace(
        make_config(candidate_kind="catalog", encoding="byte", tokenizer_path=None),
        d_model=16,
        num_layers=1,
        num_heads=2,
        ffn_dim=32,
    )
    model = build_candidate(config)
    for parameter in model.parameters():
        parameter.data.zero_()
    rows = [
        {
            "text": "Move A into B.",
            "language": "en",
            "status": str(ParseStatus.SUPPORTED),
            "semantic_family": str(SemanticFamily.DRAIN),
            "canonical_specification": asdict(
                build_family_specification(
                    SemanticFamily.DRAIN, sources=("A",), destination="B"
                )
            ),
            "error_code": None,
            "metadata": {"role_assignment": "AB"},
        }
    ] * 8
    calibration = calibrate_fail_closed(
        model, rows, config=config, device=torch.device("cpu")
    )
    assert calibration.status == "FAILED"
    assert calibration.coverage == 0
    proposal = LanguageProposal(
        ParseStatus.SUPPORTED,
        "en",
        "Move A into B.",
        build_family_specification(
            SemanticFamily.DRAIN, sources=("A",), destination="B"
        ),
        SemanticFamily.DRAIN,
    )
    rejected = apply_calibration(
        StructuredPrediction(proposal, {"minimum": 1.0}, True), calibration
    )
    assert rejected.proposal.status == ParseStatus.AMBIGUOUS
    assert rejected.invalid_reason == "CALIBRATION_FAILED"


def _correct_factorized_logits() -> dict[str, torch.Tensor]:
    low = -9.0
    high = 9.0
    logits = {
        "status": torch.full((1, 4), low),
        "error": torch.full((1, 8), low),
        "family": torch.full((1, 6), low),
        "source_count": torch.full((1, 4), low),
        "source_slots": torch.full((1, 3, 4), low),
        "destination": torch.full((1, 5), low),
        "preserve": torch.full((1, 4), low),
        "termination": torch.full((1, 4), low),
        "order": torch.full((1, 2), low),
    }
    logits["status"][0, list(ParseStatus).index(ParseStatus.SUPPORTED)] = high
    logits["family"][0, list(SemanticFamily).index(SemanticFamily.DRAIN)] = high
    logits["source_count"][0, 1] = high
    logits["source_slots"][0, 0, VARIABLES.index("A")] = high
    logits["destination"][0, VARIABLES.index("B")] = high
    logits["preserve"][0, VARIABLES.index("C")] = high
    logits["preserve"][0, VARIABLES.index("D")] = high
    logits["termination"][0, VARIABLES.index("A")] = high
    logits["order"][0, 0] = high
    return logits


def test_every_factorized_head_affects_inference() -> None:
    base = _decode_factorized(_correct_factorized_logits(), ["x"], ["en"])[0]
    assert base.proposal.status == ParseStatus.SUPPORTED
    for head in (
        "family",
        "source_count",
        "source_slots",
        "destination",
        "preserve",
        "termination",
    ):
        logits = _correct_factorized_logits()
        if head == "family":
            logits["family"].fill_(-9)
            logits["family"][
                0, list(SemanticFamily).index(SemanticFamily.MERGE_TWO)
            ] = 9
        elif head == "source_count":
            logits["source_count"].fill_(-9)
            logits["source_count"][0, 2] = 9
        elif head == "source_slots":
            logits["source_slots"][0, 0].fill_(-9)
            logits["source_slots"][0, 0, VARIABLES.index("B")] = 9
        elif head == "destination":
            logits["destination"].fill_(-9)
            logits["destination"][0, VARIABLES.index("A")] = 9
        elif head == "preserve":
            logits["preserve"][0, VARIABLES.index("C")] = -9
        else:
            logits["termination"][0, VARIABLES.index("A")] = -9
        changed = _decode_factorized(logits, ["x"], ["en"])[0]
        assert (
            changed.proposal.status != ParseStatus.SUPPORTED
            or canonical_specification_json(changed.proposal.specification)
            != canonical_specification_json(base.proposal.specification)
        ), head
    logits = _correct_factorized_logits()
    logits["status"].fill_(-9)
    logits["status"][0, list(ParseStatus).index(ParseStatus.AMBIGUOUS)] = 9
    logits["error"][0, 0] = 9
    first = _decode_factorized(logits, ["x"], ["en"])[0]
    logits["error"][0, 0] = -9
    logits["error"][0, 1] = 9
    second = _decode_factorized(logits, ["x"], ["en"])[0]
    assert first.proposal.issues[0].code != second.proposal.issues[0].code
    drop = _correct_factorized_logits()
    drop["family"].fill_(-9)
    drop["family"][0, list(SemanticFamily).index(SemanticFamily.DROP_THEN_TRANSFER)] = 9
    drop["source_count"].fill_(-9)
    drop["source_count"][0, 2] = 9
    drop["source_slots"][0, 1, VARIABLES.index("B")] = 9
    drop["destination"].fill_(-9)
    drop["destination"][0, VARIABLES.index("C")] = 9
    drop["preserve"].fill_(-9)
    drop["preserve"][0, VARIABLES.index("D")] = 9
    drop["termination"].fill_(-9)
    drop["termination"][0, VARIABLES.index("A")] = 9
    drop["termination"][0, VARIABLES.index("B")] = 9
    assert (
        _decode_factorized(drop, ["x"], ["en"])[0].proposal.status
        == ParseStatus.SUPPORTED
    )
    drop["order"].fill_(-9)
    drop["order"][0, 1] = 9
    assert (
        _decode_factorized(drop, ["x"], ["en"])[0].proposal.status
        == ParseStatus.AMBIGUOUS
    )


def test_semantic_equivalence_commutative_merge_but_not_ordered_drop() -> None:
    merge = build_family_specification(
        SemanticFamily.MERGE_TWO, sources=("A", "B"), destination="C"
    )
    reversed_merge = reversed_merge_order(merge)
    assert not structural_specification_equal(merge, reversed_merge)
    assert semantic_specification_equal(merge, reversed_merge)
    ordered = build_family_specification(
        SemanticFamily.DROP_THEN_TRANSFER,
        sources=("A", "B"),
        destination="C",
    )
    reversed_order = replace(
        ordered, phase_constraints=tuple(reversed(ordered.phase_constraints))
    )
    assert not semantic_specification_equal(ordered, reversed_order)


def test_clarification_uses_parser_output_and_preserves_actions(
    fair_dataset: tuple[Path, dict],
) -> None:
    path, _ = fair_dataset
    rows = load_language_rows(path / "test_ambiguous.jsonl")
    row = next(
        item for item in rows if item["error_code"] == str(ValidationCode.UNCLEAR_ORDER)
    )
    calls = []

    def parser(text: str, language: str) -> LanguageProposal:
        calls.append((text, language))
        return parse_fair_controlled_language(
            text, language=language, lexicon_mode="train"
        )

    state = clarification_from_raw(row["text"], row["language"], parser)
    assert calls == [(row["text"], row["language"])]
    assert state.question is not None
    assert state.question.code == ValidationCode.UNCLEAR_ORDER
    assert len(state.partial.actions) == 2
    result = resolve_clarification_state(state, row["metadata"]["clarification_answer"])
    assert result.status == ParseStatus.SUPPORTED
    assert len(result.specification.phase_constraints) == 2


def test_concrete_binding_preserves_roles_and_property_equivalence() -> None:
    specification = build_family_specification(
        SemanticFamily.MERGE_TWO, sources=("A", "B"), destination="C"
    )
    audit = acquire_with_concrete_binding(specification)
    assert audit.template_found
    assert audit.binding_found
    assert dict(audit.binding) == {
        "SOURCE_1": "A",
        "SOURCE_2": "B",
        "DESTINATION": "C",
    }
    assert audit.property_verified
    candidate, _ = parse_canonical_dsl(audit.acquisition.candidate_ast)
    assert program_variables(candidate) == {"A", "B", "C"}


def test_approval_boundary_rejects_every_unsafe_path_and_allows_approve() -> None:
    original = build_family_specification(
        SemanticFamily.DRAIN, sources=("A",), destination="B"
    )
    proposal = LanguageProposal(
        ParseStatus.SUPPORTED,
        "en",
        "Move A into B.",
        original,
        SemanticFamily.DRAIN,
    )
    acquisition = acquire_with_concrete_binding(original).acquisition
    memory = RuleMemory()
    signature = canonical_specification_json(original)
    for decision in (
        ApprovalDecision.REJECT,
        ApprovalDecision.ASK_CLARIFICATION,
        ApprovalDecision.EDIT_SPECIFICATION,
    ):
        with pytest.raises(ValueError, match="APPROVE"):
            store_approved_language_rule(
                memory=memory,
                proposal=proposal,
                acquisition=acquisition,
                approval=Approval(decision, "tester", "TRUSTED_SUPERVISOR", signature),
            )
    with pytest.raises(ValueError, match="does not match"):
        store_approved_language_rule(
            memory=memory,
            proposal=proposal,
            acquisition=acquisition,
            approval=Approval(
                ApprovalDecision.APPROVE,
                "tester",
                "TRUSTED_SUPERVISOR",
                signature + "-wrong",
            ),
        )
    edited_spec = build_family_specification(
        SemanticFamily.DRAIN, sources=("A",), destination="C"
    )
    edited = replace(proposal, specification=edited_spec)
    with pytest.raises(ValueError, match="stale|not verified"):
        store_approved_language_rule(
            memory=memory,
            proposal=edited,
            acquisition=acquisition,
            approval=Approval(
                ApprovalDecision.APPROVE,
                "tester",
                "TRUSTED_SUPERVISOR",
                canonical_specification_json(edited_spec),
            ),
        )
    failed_calibration = replace(
        proposal,
        status=ParseStatus.AMBIGUOUS,
        specification=None,
    )
    unsupported = replace(
        proposal,
        status=ParseStatus.UNSUPPORTED,
        specification=None,
    )
    for blocked in (failed_calibration, unsupported):
        with pytest.raises(ValueError, match="supported complete"):
            store_approved_language_rule(
                memory=memory,
                proposal=blocked,
                acquisition=acquisition,
                approval=Approval(
                    ApprovalDecision.APPROVE,
                    "tester",
                    "TRUSTED_SUPERVISOR",
                    signature,
                ),
            )
    assert not memory.records
    approved_memory = RuleMemory()
    stored = store_approved_language_rule(
        memory=approved_memory,
        proposal=proposal,
        acquisition=acquisition,
        approval=Approval(
            ApprovalDecision.APPROVE,
            "tester",
            "TRUSTED_SUPERVISOR",
            signature,
        ),
    )
    assert stored.rule_id in approved_memory.records


def test_m231_has_no_hidden_target_access() -> None:
    modules = (
        acquire_with_concrete_binding,
        FactorizedLanguageToSpecParserV2,
        generate_fair_language_dataset,
    )
    source = "\n".join(inspect.getsource(item) for item in modules)
    assert "HiddenTarget" not in source
    assert "target.program" not in source
    assert "m223a_evaluator_process" not in source
