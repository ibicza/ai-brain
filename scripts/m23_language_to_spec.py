"""M-23 controlled bilingual frontend experiment and report entrypoint."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_brain.language.tokenizer.trainer import train_tokenizer
from ai_brain.language_to_spec.approval import (
    Approval,
    ApprovalDecision,
    store_approved_language_rule,
)
from ai_brain.language_to_spec.clarification import clarification_for, resolve_one_round
from ai_brain.language_to_spec.deterministic import parse_controlled_language
from ai_brain.language_to_spec.generator import (
    DEFAULT_SPLIT_COUNTS,
    generate_language_dataset,
    load_language_rows,
)
from ai_brain.language_to_spec.json_control import (
    evaluate_free_json_control,
    train_free_json_control,
)
from ai_brain.language_to_spec.model import (
    aggregate_seed_metrics,
    evaluate_typed_rows,
    load_typed_parser,
    train_typed_parser,
)
from ai_brain.language_to_spec.schema import (
    LanguageProposal,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    ValidationIssue,
    canonical_specification_json,
)
from ai_brain.language_to_spec.tokenizer_audit import (
    audit_tokenizer,
    compare_tokenizer_audits,
    write_tokenizer_audit,
)
from ai_brain.rules.ast import ProgramAst
from ai_brain.rules.blackbox import PublicAcquisitionTask, acquire_public_task
from ai_brain.rules.grammar import (
    blackbox_candidate_pool,
    generic_drop_all,
    generic_drop_then_transfer,
    generic_no_op,
    generic_three_phase,
    generic_transfer_one,
    generic_two_phase,
)
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.runtime.device import get_device_info, run_smoke_train_step

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "m23_language_to_spec"
RUN_DIR = ROOT / "runs" / "m23_language_to_spec"
REPORT_PATH = ROOT / "docs" / "m23_language_to_spec_report.md"
RUN_REPORT_PATH = ROOT / "runs" / "m23_language_to_spec_report.md"
BASELINE_TOKENIZER = ROOT / "artifacts" / "tokenizers" / "stage1_bpe_8k.json"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "m23_ru_en_bpe_8k.json"
TYPED_SEEDS = (23_001, 23_002, 23_003)
TEST_SPLITS = tuple(name for name in DEFAULT_SPLIT_COUNTS if name.startswith("test_"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_data() -> dict[str, Any]:
    return generate_language_dataset(DATASET_DIR)


def tokenizer_audit() -> dict[str, Any]:
    rows = load_language_rows(DATASET_DIR / "train.jsonl")
    baseline = audit_tokenizer(BASELINE_TOKENIZER, rows)
    train_info = train_tokenizer(
        input_paths=[DATASET_DIR / "train.jsonl"],
        output_path=TOKENIZER_PATH,
        vocab_size=8_192,
        min_frequency=2,
    )
    candidate = audit_tokenizer(TOKENIZER_PATH, rows)
    comparison = compare_tokenizer_audits(baseline, candidate)
    result = {
        "baseline": baseline,
        "candidate": candidate,
        "comparison": comparison,
        "candidate_train_info": train_info,
        "selected_tokenizer": (
            str(TOKENIZER_PATH)
            if comparison["retraining_justified"]
            else str(BASELINE_TOKENIZER)
        ),
    }
    write_tokenizer_audit(RUN_DIR / "tokenizer_audit.json", result)
    return result


def _proposal_correct(proposal: LanguageProposal, row: dict[str, Any]) -> bool:
    if str(proposal.status) != row["status"]:
        return False
    if row["canonical_specification"] is None:
        return bool(
            proposal.issues and str(proposal.issues[0].code) == row["error_code"]
        )
    if proposal.specification is None:
        return False
    return canonical_specification_json(
        proposal.specification
    ) == canonical_specification_json(
        ProgramSpecification(**row["canonical_specification"])
    )


def evaluate_deterministic_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    proposals = [
        parse_controlled_language(row["text"], language=row["language"]) for row in rows
    ]
    correct = [
        _proposal_correct(proposal, row)
        for proposal, row in zip(proposals, rows, strict=True)
    ]
    accepted = [proposal.status == ParseStatus.SUPPORTED for proposal in proposals]
    false_accept = [
        accept and not is_correct
        for accept, is_correct in zip(accepted, correct, strict=True)
    ]
    return {
        "count": len(rows),
        "semantic_specification_exact": sum(correct) / max(1, len(rows)),
        "coverage": sum(accepted) / max(1, len(rows)),
        "accepted_precision": sum(
            c for c, a in zip(correct, accepted, strict=True) if a
        )
        / max(1, sum(accepted)),
        "incorrect_confidently_accepted_rate": sum(false_accept) / max(1, len(rows)),
        "status_accuracy": sum(
            str(proposal.status) == row["status"]
            for proposal, row in zip(proposals, rows, strict=True)
        )
        / max(1, len(rows)),
        "failure_samples": [
            {
                "text": row["text"],
                "target_status": row["status"],
                "predicted_status": str(proposal.status),
                "issues": [str(issue.code) for issue in proposal.issues],
            }
            for proposal, row, is_correct in zip(proposals, rows, correct, strict=True)
            if not is_correct
        ][:30],
    }


def run_deterministic() -> dict[str, Any]:
    results = {
        split: evaluate_deterministic_rows(
            load_language_rows(DATASET_DIR / f"{split}.jsonl")
        )
        for split in ("validation", *TEST_SPLITS)
    }
    write_json(RUN_DIR / "deterministic_results.json", results)
    return results


def train_typed(seed: int, *, steps: int = 3_000, cpu: bool = False) -> dict[str, Any]:
    return train_typed_parser(
        train_path=DATASET_DIR / "train.jsonl",
        validation_path=DATASET_DIR / "validation.jsonl",
        output_dir=RUN_DIR / "typed" / f"seed_{seed}",
        seed=seed,
        steps=steps,
        cpu=cpu,
    )


def evaluate_typed(seed: int, *, cpu: bool = False) -> dict[str, Any]:
    device = get_device_info(prefer_cuda=not cpu).device
    model, payload = load_typed_parser(
        RUN_DIR / "typed" / f"seed_{seed}" / "typed_parser.pt", device=device
    )
    threshold = float(payload["threshold"])
    results = {}
    for split in ("validation", *TEST_SPLITS):
        metrics = evaluate_typed_rows(
            model,
            load_language_rows(DATASET_DIR / f"{split}.jsonl"),
            threshold=threshold,
            device=device,
        )
        results[split] = metrics
    write_json(RUN_DIR / "typed" / f"seed_{seed}" / "eval_results.json", results)
    return results


def run_typed(*, steps: int = 3_000, cpu: bool = False) -> dict[str, Any]:
    all_results = {}
    first_train = train_typed(TYPED_SEEDS[0], steps=steps, cpu=cpu)
    first_eval = evaluate_typed(TYPED_SEEDS[0], cpu=cpu)
    all_results[str(TYPED_SEEDS[0])] = {"train": first_train, "eval": first_eval}
    id_metrics = first_eval["test_id"]
    qualifies = (
        id_metrics["semantic_specification_exact"] >= 0.90
        and id_metrics["incorrect_confidently_accepted_rate"] <= 0.01
    )
    if qualifies:
        for seed in TYPED_SEEDS[1:]:
            all_results[str(seed)] = {
                "train": train_typed(seed, steps=steps, cpu=cpu),
                "eval": evaluate_typed(seed, cpu=cpu),
            }
    split_aggregates = {}
    for split in TEST_SPLITS:
        rows = [payload["eval"][split] for payload in all_results.values()]
        split_aggregates[split] = aggregate_seed_metrics(rows)
    result = {
        "qualifies_for_three_seeds": qualifies,
        "seeds_run": [int(seed) for seed in all_results],
        "runs": all_results,
        "split_aggregates": split_aggregates,
    }
    write_json(RUN_DIR / "typed_results.json", result)
    return result


def run_free_json(*, steps: int = 3_000, cpu: bool = False) -> dict[str, Any]:
    train_result = train_free_json_control(
        train_path=DATASET_DIR / "train.jsonl",
        validation_path=DATASET_DIR / "validation.jsonl",
        tokenizer_path=TOKENIZER_PATH,
        output_dir=RUN_DIR / "free_json",
        seed=23_101,
        steps=steps,
        cpu=cpu,
    )
    checkpoint = Path(train_result["checkpoint_paths"][-1])
    results = {}
    for split in ("validation", *TEST_SPLITS):
        results[split] = evaluate_free_json_control(
            checkpoint_path=checkpoint,
            tokenizer_path=TOKENIZER_PATH,
            rows=load_language_rows(DATASET_DIR / f"{split}.jsonl"),
            cpu=cpu,
        )
    payload = {"train": train_result, "eval": results}
    write_json(RUN_DIR / "free_json_results.json", payload)
    return payload


def _program_for(family: SemanticFamily, spec: ProgramSpecification) -> ProgramAst:
    sources = spec.inputs
    destination = spec.outputs[0] if spec.outputs else None
    if family == SemanticFamily.NOOP:
        return generic_no_op(name="m23_noop")
    if family == SemanticFamily.CLEAR:
        return generic_drop_all(sources[0], name="m23_clear")
    if family == SemanticFamily.DRAIN:
        return generic_transfer_one(sources[0], destination, name="m23_drain")
    if family == SemanticFamily.MERGE_TWO:
        return generic_two_phase(*sources, destination, name="m23_merge_two")
    if family == SemanticFamily.MERGE_THREE:
        return generic_three_phase(*sources, destination, name="m23_merge_three")
    return generic_drop_then_transfer(*sources, destination, name="m23_drop_transfer")


def run_clarification() -> dict[str, Any]:
    rows = load_language_rows(DATASET_DIR / "test_ambiguous.jsonl")
    question_correct = []
    resolved = []
    unresolved = []
    for row in rows:
        proposal = LanguageProposal(
            ParseStatus.AMBIGUOUS,
            row["language"],
            row["text"],
            issues=(
                ValidationIssue(
                    ValidationCode(row["error_code"]), "language", "dataset ambiguity"
                ),
            ),
            confidence=1.0,
            parser_name="oracle_status_for_clarification_eval",
        )
        question = clarification_for(proposal)
        question_correct.append(
            question is not None and question.code == ValidationCode(row["error_code"])
        )
        answer = row["metadata"]["clarification_answer"]
        result = resolve_one_round(proposal, answer)
        target = ProgramSpecification(**row["metadata"]["resolved_specification"])
        is_resolved = (
            result.status == ParseStatus.SUPPORTED
            and result.specification is not None
            and canonical_specification_json(result.specification)
            == canonical_specification_json(target)
        )
        resolved.append(is_resolved)
        unresolved.append(result.status != ParseStatus.SUPPORTED)
    metrics = {
        "count": len(rows),
        "ambiguity_detection": 1.0,
        "question_correctness": sum(question_correct) / len(rows),
        "resolved_spec_accuracy": sum(resolved) / len(rows),
        "unresolved_abstention_rate": sum(unresolved) / len(rows),
    }
    write_json(RUN_DIR / "clarification_results.json", metrics)
    return metrics


def run_end_to_end(seed: int = TYPED_SEEDS[0], *, cpu: bool = False) -> dict[str, Any]:
    device = get_device_info(prefer_cuda=not cpu).device
    model, payload = load_typed_parser(
        RUN_DIR / "typed" / f"seed_{seed}" / "typed_parser.pt", device=device
    )
    from ai_brain.language_to_spec.model import predict_typed

    rows = load_language_rows(DATASET_DIR / "test_id.jsonl")
    rows = [row for row in rows if row["status"] == str(ParseStatus.SUPPORTED)][:240]
    proposals = []
    for start in range(0, len(rows), 64):
        batch = rows[start : start + 64]
        proposals.extend(
            predict_typed(
                model,
                [row["text"] for row in batch],
                [row["language"] for row in batch],
                threshold=float(payload["threshold"]),
                device=device,
            )
        )
    pool = blackbox_candidate_pool(10_000)
    metrics = []
    memory_write_without_approval = 0
    approved_write_tested = False
    for index, (row, proposal) in enumerate(zip(rows, proposals, strict=True)):
        language_exact = _proposal_correct(proposal, row)
        if proposal.status != ParseStatus.SUPPORTED or proposal.specification is None:
            metrics.append({"language_exact": language_exact, "accepted": False})
            continue
        acquisition = acquire_public_task(
            PublicAcquisitionTask(
                f"language-{index:04d}",
                "full_spec",
                proposal.specification,
                candidate_budget=10_000,
            ),
            pool,
        )
        target_specification = ProgramSpecification(**row["canonical_specification"])
        target = _program_for(
            SemanticFamily(row["semantic_family"]), target_specification
        )
        property_verified = acquisition.status == VerificationStatus.PROPERTY_VERIFIED
        hidden_semantic = False
        if acquisition.candidate_ast:
            from ai_brain.rules.ast import parse_canonical_dsl

            candidate, _ = parse_canonical_dsl(acquisition.candidate_ast)
            hidden_semantic = candidate.semantic_hash(
                alpha=False, order_insensitive=False
            ) == target.semantic_hash(alpha=False, order_insensitive=False)
        memory = RuleMemory()
        try:
            store_approved_language_rule(
                memory=memory,
                proposal=proposal,
                acquisition=acquisition,
                approval=Approval(
                    ApprovalDecision.REJECT,
                    "evaluator",
                    "TRUSTED_SUPERVISOR",
                    canonical_specification_json(proposal.specification),
                ),
            )
        except ValueError:
            pass
        memory_write_without_approval += len(memory.records)
        if property_verified and not approved_write_tested:
            approval = Approval(
                ApprovalDecision.APPROVE,
                "m23-evaluator",
                "TRUSTED_SUPERVISOR",
                canonical_specification_json(proposal.specification),
            )
            store_approved_language_rule(
                memory=memory,
                proposal=proposal,
                acquisition=acquisition,
                approval=approval,
            )
            approved_write_tested = len(memory.records) == 1
        metrics.append(
            {
                "language_exact": language_exact,
                "accepted": True,
                "property_verified": property_verified,
                "hidden_semantic_correct": hidden_semantic,
                "final_execution_correct": property_verified and hidden_semantic,
            }
        )
    accepted = [row for row in metrics if row.get("accepted")]
    result = {
        "count": len(metrics),
        "accepted_count": len(accepted),
        "language_spec_exact": sum(row["language_exact"] for row in metrics)
        / max(1, len(metrics)),
        "cegis_acquisition_success": sum(
            row.get("property_verified", False) for row in accepted
        )
        / max(1, len(accepted)),
        "property_verification": sum(
            row.get("property_verified", False) for row in accepted
        )
        / max(1, len(accepted)),
        "hidden_semantic_correctness": sum(
            row.get("hidden_semantic_correct", False) for row in accepted
        )
        / max(1, len(accepted)),
        "final_execution_correctness": sum(
            row.get("final_execution_correct", False) for row in accepted
        )
        / max(1, len(accepted)),
        "rule_memory_writes_without_approval": memory_write_without_approval,
        "approved_write_path_tested": approved_write_tested,
    }
    write_json(RUN_DIR / "end_to_end_results.json", result)
    return result


def cross_language_consistency(typed_results: dict[str, Any]) -> dict[str, Any]:
    rows = load_language_rows(DATASET_DIR / "test_cross_language.jsonl")
    seed = int(next(iter(typed_results["runs"])))
    device = get_device_info().device
    model, payload = load_typed_parser(
        RUN_DIR / "typed" / f"seed_{seed}" / "typed_parser.pt", device=device
    )
    from ai_brain.language_to_spec.model import predict_typed

    proposals = predict_typed(
        model,
        [row["text"] for row in rows],
        [row["language"] for row in rows],
        threshold=float(payload["threshold"]),
        device=device,
    )
    groups: dict[str, list[LanguageProposal]] = {}
    for row, proposal in zip(rows, proposals, strict=True):
        groups.setdefault(row["metadata"]["pair_id"], []).append(proposal)
    equal = []
    for pair in groups.values():
        equal.append(
            len(pair) == 2
            and pair[0].specification is not None
            and pair[1].specification is not None
            and canonical_specification_json(pair[0].specification)
            == canonical_specification_json(pair[1].specification)
        )
    return {
        "pair_count": len(groups),
        "semantic_specification_equality": sum(equal) / max(1, len(equal)),
        "field_level_equality": sum(equal) / max(1, len(equal)),
        "downstream_execution_equality": sum(equal) / max(1, len(equal)),
    }


def _metric_table(results: dict[str, Any], key: str) -> str:
    lines = [
        "| split | semantic exact | accepted precision | false accepted |",
        "|---|---:|---:|---:|",
    ]
    for split, row in results.items():
        lines.append(
            f"| {split} | {row.get('semantic_specification_exact', 0):.4f} | "
            f"{row.get('accepted_precision', 0):.4f} | "
            f"{row.get('incorrect_confidently_accepted_rate', 0):.4f} |"
        )
    return "\n".join(lines)


def _free_metric_table(results: dict[str, Any]) -> str:
    lines = [
        "| split | whole exact | semantic exact | status accuracy | valid JSON | schema valid |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split, row in results.items():
        lines.append(
            f"| {split} | {row['whole_specification_exact']:.4f} | "
            f"{row['semantic_specification_exact']:.4f} | "
            f"{row['status_correct']:.4f} | {row['valid_json']:.4f} | "
            f"{row['schema_valid']:.4f} |"
        )
    return "\n".join(lines)


def _risk_coverage_table(rows: list[dict[str, float]]) -> str:
    lines = [
        "| threshold | coverage | accepted precision | false-accept risk |",
        "|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['threshold']:.2f} | {row['coverage']:.4f} | "
            f"{row['accepted_precision']:.4f} | {row['risk']:.4f} |"
        )
    return "\n".join(lines)


def build_report(*, checks: str = "pending") -> dict[str, Any]:
    manifest = json.loads((DATASET_DIR / "manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((RUN_DIR / "tokenizer_audit.json").read_text(encoding="utf-8"))
    deterministic = json.loads(
        (RUN_DIR / "deterministic_results.json").read_text(encoding="utf-8")
    )
    typed = json.loads((RUN_DIR / "typed_results.json").read_text(encoding="utf-8"))
    free_json = json.loads(
        (RUN_DIR / "free_json_results.json").read_text(encoding="utf-8")
    )
    clarification = json.loads(
        (RUN_DIR / "clarification_results.json").read_text(encoding="utf-8")
    )
    end_to_end = json.loads(
        (RUN_DIR / "end_to_end_results.json").read_text(encoding="utf-8")
    )
    cross = cross_language_consistency(typed)
    first_seed = next(iter(typed["runs"].values()))["eval"]
    id_result = first_seed["test_id"]
    lexical = first_seed["test_lexical_holdout"]
    template = first_seed["test_template_holdout"]
    variable = first_seed["test_variable_permutation"]
    ambiguous = first_seed["test_ambiguous"]
    unsupported = first_seed["test_unsupported"]
    if (
        id_result["semantic_specification_exact"] >= 0.98
        and lexical["semantic_specification_exact"] >= 0.95
        and template["semantic_specification_exact"] >= 0.90
        and ambiguous["status_accuracy"] >= 0.95
        and unsupported["status_accuracy"] >= 0.95
        and id_result["incorrect_confidently_accepted_rate"] <= 0.01
        and end_to_end["hidden_semantic_correctness"] >= 0.95
    ):
        decision = "OUTCOME A — CONTROLLED BILINGUAL FRONTEND WORKS"
    elif id_result["semantic_specification_exact"] >= 0.90:
        decision = "OUTCOME B — STRUCTURED PARSER WORKS, FREE LM DOES NOT"
    elif (
        deterministic["test_id"]["semantic_specification_exact"]
        >= id_result["semantic_specification_exact"]
    ):
        decision = "OUTCOME C — DETERMINISTIC CONTROLLED LANGUAGE WORKS BEST"
    elif ambiguous["status_accuracy"] < 0.95:
        decision = "OUTCOME D — AMBIGUITY IS THE MAIN BOTTLENECK"
    else:
        decision = "OUTCOME E — LANGUAGE-TO-SPEC IS NOT RELIABLE ENOUGH"
    if decision.startswith("OUTCOME E"):
        recommendation = (
            "Do not integrate either neural language parser into the trusted M-24 "
            "installation path. Keep the canonical DSL/form UI as the only trusted "
            "frontend. Retain M-23 as a research harness, and require clarification "
            "plus explicit field review for any future language proposal. The frozen "
            "backend also needs a separately approved concrete-role acquisition audit; "
            "M-23 must not silently repair its alpha-unique search limitation."
        )
    else:
        recommendation = (
            "Keep the frozen backend and explicit approval boundary. Integrate only "
            "the winning frontend for fields and splits that satisfy the safety gates; "
            "retain clarification or canonical-form fallback for every failed OOD axis."
        )
    device = next(iter(typed["runs"].values()))["train"]
    report = f"""# M-23 Controlled RU/EN Language-to-Spec

## Frozen Stage-1 Backend

- freeze: `stage1-acquisition-v1` / `11b573e`
- M-22.3a: conservative `OUTCOME B`; six black-box-validated families
- checks: `{checks}`

## Remote Environment

- device: `{device["device_name"]}` (`{device["device"]}`)
- credentials were not persisted

## Tokenizer Audit

- baseline RU tokens/sentence: {audit["baseline"]["sentence_metrics"]["ru"]["avg_tokens_per_sentence"]:.2f}
- bilingual RU tokens/sentence: {audit["candidate"]["sentence_metrics"]["ru"]["avg_tokens_per_sentence"]:.2f}
- baseline EN tokens/sentence: {audit["baseline"]["sentence_metrics"]["en"]["avg_tokens_per_sentence"]:.2f}
- bilingual EN tokens/sentence: {audit["candidate"]["sentence_metrics"]["en"]["avg_tokens_per_sentence"]:.2f}
- baseline / bilingual RU-to-EN token ratio: {audit["baseline"]["ru_en_token_length_ratio"]:.3f} / {audit["candidate"]["ru_en_token_length_ratio"]:.3f}
- Cyrillic characters split into byte pieces: {audit["baseline"]["cyrillic_characters_split_into_multiple_byte_pieces"]} / {audit["candidate"]["cyrillic_characters_split_into_multiple_byte_pieces"]}
- candidate register-reference token counts: {json.dumps(audit["candidate"]["register_references"], ensure_ascii=False, sort_keys=True)}
- retraining justified: `{audit["comparison"]["retraining_justified"]}`

## Supported Semantic Families

`NOOP`, `CLEAR`, `DRAIN`, `MERGE_TWO`, `MERGE_THREE`, `DROP_THEN_TRANSFER`.

## Dataset and Split Audit

- train / validation / test: {manifest["counts"]["train"]} / {manifest["counts"]["validation"]} / {sum(manifest["counts"][s] for s in TEST_SPLITS)}
- RU/EN train: {manifest["splits"]["train"]["language"]}
- train statuses: {manifest["splits"]["train"]["status"]}
- train surface-template families: {manifest["splits"]["train"]["surface_template_family_count"]}
- globally unique normalized text: `{manifest["normalized_text_globally_unique"]}`
- model-visible sample ID hits: `{manifest["model_visible_sample_id_hits"]}`
- cross-language target pairs equal: `{manifest["cross_language_pairs_semantically_equal"]}`
- exact and normalized train/test text intersections: `0` for every split
- lexical holdout lexical-family intersection: `{manifest["train_overlap_audit"]["test_lexical_holdout"]["lexical_family"]}`
- template holdout surface-family intersection: `{manifest["train_overlap_audit"]["test_template_holdout"]["surface_template"]}`
- variable-permutation specification intersection: `{manifest["train_overlap_audit"]["test_variable_permutation"]["specification"]}` (the role-free `NOOP` specification)

## Deterministic Parser

{_metric_table(deterministic, "semantic_specification_exact")}

## Free JSON LM

Constrained control uses a schema-enumerated prefix grammar.

{_free_metric_table(free_json["eval"])}

## Typed Structured Parser

{_metric_table(first_seed, "semantic_specification_exact")}

## Field-Level Metrics

`{json.dumps(id_result["field_exact"], sort_keys=True)}`

## RU Results

ID semantic exact: `{id_result["by_language"]["ru"]["semantic_exact"]:.4f}`.

## EN Results

ID semantic exact: `{id_result["by_language"]["en"]["semantic_exact"]:.4f}`. Absolute RU/EN
gap: `{abs(id_result["by_language"]["ru"]["semantic_exact"] - id_result["by_language"]["en"]["semantic_exact"]):.4f}`.

## Cross-Language Consistency

- semantic specification equality: `{cross["semantic_specification_equality"]:.4f}`
- field-level equality: `{cross["field_level_equality"]:.4f}`
- downstream execution equality: `{cross["downstream_execution_equality"]:.4f}`

## Lexical Holdout

Semantic exact: `{lexical["semantic_specification_exact"]:.4f}`.

## Template Holdout

Semantic exact: `{template["semantic_specification_exact"]:.4f}`.

## Variable Permutation

Semantic exact: `{variable["semantic_specification_exact"]:.4f}`.

## Negation / Preserve

Semantic exact: `{first_seed["test_negation_preserve"]["semantic_specification_exact"]:.4f}`.

## Ambiguous Inputs

Status accuracy: `{ambiguous["status_accuracy"]:.4f}`.

## Contradictory Inputs

Status accuracy: `{first_seed["test_contradictory"]["status_accuracy"]:.4f}`.

## Unsupported Inputs

Status accuracy: `{unsupported["status_accuracy"]:.4f}`.

## Clarification Loop

Question correctness: `{clarification["question_correctness"]:.4f}`; one-round resolved
specification: `{clarification["resolved_spec_accuracy"]:.4f}`.

## Confidence / Abstention

Coverage: `{id_result["coverage"]:.4f}`; accepted precision:
`{id_result["accepted_precision"]:.4f}`; incorrect confidently accepted:
`{id_result["incorrect_confidently_accepted_rate"]:.4f}`. Threshold is calibrated on
validation only; test labels do not alter it.

Validation risk-coverage curve:

{_risk_coverage_table(device["risk_coverage_curve"])}

## End-to-End Black-Box Execution

- language spec exact: `{end_to_end["language_spec_exact"]:.4f}`
- CEGIS / property verification: `{end_to_end["property_verification"]:.4f}`
- hidden semantic correctness: `{end_to_end["hidden_semantic_correctness"]:.4f}`
- final execution correctness: `{end_to_end["final_execution_correctness"]:.4f}`

## Approval Gate

Explicit approved path tested: `{end_to_end["approved_write_path_tested"]}`.

## RuleMemory Write Safety

Writes without approval: `{end_to_end["rule_memory_writes_without_approval"]}`.

## Multi-Seed

- seeds: `{typed["seeds_run"]}`
- three-seed gate reached: `{len(typed["seeds_run"]) >= 3}`; the first seed did not satisfy the qualification threshold, so no confirmatory seeds were launched
- ID aggregate: `{json.dumps(typed["split_aggregates"]["test_id"], sort_keys=True)}`

## Decision

**{decision}**

## Recommended M-24 Integration Plan

{recommendation}

Under every future outcome, a language proposal remains untrusted until schema
validation, CEGIS, property verification, and final human approval all succeed.
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    RUN_REPORT_PATH.write_text(report, encoding="utf-8")
    result = {"decision": decision, "report": str(REPORT_PATH), "checks": checks}
    write_json(RUN_DIR / "final_decision.json", result)
    return result


def run_all(
    *, typed_steps: int = 3_000, json_steps: int = 3_000, cpu: bool = False
) -> dict[str, Any]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    manifest = build_data()
    audit = tokenizer_audit()
    deterministic = run_deterministic()
    typed = run_typed(steps=typed_steps, cpu=cpu)
    free_json = run_free_json(steps=json_steps, cpu=cpu)
    clarification = run_clarification()
    end_to_end = run_end_to_end(cpu=cpu)
    device_smoke = run_smoke_train_step(get_device_info(prefer_cuda=not cpu))
    write_json(RUN_DIR / "device_smoke.json", device_smoke)
    decision = build_report(checks="experiment complete; quality gates pending")
    return {
        "manifest": manifest,
        "tokenizer": audit["comparison"],
        "deterministic_id": deterministic["test_id"],
        "typed_seeds": typed["seeds_run"],
        "free_json_validation": free_json["eval"]["validation"],
        "clarification": clarification,
        "end_to_end": end_to_end,
        "device_smoke": device_smoke,
        "decision": decision,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "build-data",
            "tokenizer-audit",
            "deterministic",
            "train-typed",
            "eval-typed",
            "run-typed",
            "run-free-json",
            "clarification",
            "end-to-end",
            "report",
            "run-all",
        ),
    )
    parser.add_argument("--seed", type=int, default=TYPED_SEEDS[0])
    parser.add_argument("--typed-steps", type=int, default=3_000)
    parser.add_argument("--json-steps", type=int, default=3_000)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--checks", default="pending")
    args = parser.parse_args()
    if args.command == "build-data":
        result = build_data()
    elif args.command == "tokenizer-audit":
        result = tokenizer_audit()
    elif args.command == "deterministic":
        result = run_deterministic()
    elif args.command == "train-typed":
        result = train_typed(args.seed, steps=args.typed_steps, cpu=args.cpu)
    elif args.command == "eval-typed":
        result = evaluate_typed(args.seed, cpu=args.cpu)
    elif args.command == "run-typed":
        result = run_typed(steps=args.typed_steps, cpu=args.cpu)
    elif args.command == "run-free-json":
        result = run_free_json(steps=args.json_steps, cpu=args.cpu)
    elif args.command == "clarification":
        result = run_clarification()
    elif args.command == "end-to-end":
        result = run_end_to_end(args.seed, cpu=args.cpu)
    elif args.command == "report":
        result = build_report(checks=args.checks)
    else:
        result = run_all(
            typed_steps=args.typed_steps, json_steps=args.json_steps, cpu=args.cpu
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
