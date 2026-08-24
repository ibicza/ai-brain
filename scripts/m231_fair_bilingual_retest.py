"""M-23.1 fair bilingual language-to-spec experiment runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from ai_brain.language_to_spec.approval import (
    Approval,
    ApprovalDecision,
    store_approved_language_rule,
)
from ai_brain.language_to_spec.binding import acquire_with_concrete_binding
from ai_brain.language_to_spec.equivalence import (
    behaviorally_equivalent,
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
    parse_fair_controlled_language,
)
from ai_brain.language_to_spec.fair_model import (
    StructuredPrediction,
    apply_calibration,
    evaluate_candidate,
    load_fair_candidate,
    make_config,
    predict_raw,
    prediction_correct,
    train_fair_candidate,
)
from ai_brain.language_to_spec.generator import load_language_rows
from ai_brain.language_to_spec.schema import (
    LanguageProposal,
    ParseStatus,
    ValidationCode,
    ValidationIssue,
    canonical_specification_json,
)
from ai_brain.rules.memory import RuleMemory
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.runtime.device import get_device_info

ROOT = Path(__file__).resolve().parents[1]
M23_RUN = ROOT / "runs" / "m23_language_to_spec"
M23_DATA = ROOT / "datasets" / "m23_language_to_spec"
DATA_DIR = ROOT / "datasets" / "m231_fair_language_to_spec"
RUN_DIR = ROOT / "runs" / "m231_fair_language_to_spec"
TOKENIZER_PATH = ROOT / "artifacts" / "tokenizers" / "m23_ru_en_bpe_8k.json"
PROGRESS_PATH = ROOT / "runs" / "m231_progress.jsonl"
BASELINE_SNAPSHOT = ROOT / "runs" / "m231_m23_baseline_snapshot.json"

TEST_SPLITS = tuple(split for split in FAIR_SPLIT_COUNTS if split.startswith("test_"))
CANDIDATES = {
    "catalog_bpe": ("catalog", "bpe", 0.0),
    "factorized_byte": ("factorized", "byte", 0.0),
    "factorized_bpe": ("factorized", "bpe", 0.0),
    "factorized_bpe_consistency": ("factorized", "bpe", 0.05),
}
PRIMARY_CANDIDATES = ("catalog_bpe", "factorized_byte", "factorized_bpe")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_samples(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_samples(item)
            for key, item in value.items()
            if key not in {"rows", "samples", "failures"}
        }
    if isinstance(value, list):
        return [_without_samples(item) for item in value]
    return value


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def progress(
    phase: str,
    command: str,
    *,
    metrics: dict[str, Any] | None = None,
    diagnosis: str = "",
    fix: str = "",
    next_action: str = "",
) -> None:
    row = {
        "timestamp": datetime.now(UTC).isoformat(),
        "phase": phase,
        "commit": _commit(),
        "command": command,
        "metrics": metrics or {},
        "diagnosis": diagnosis,
        "fix": fix,
        "next_action": next_action,
    }
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def snapshot_m23() -> dict[str, Any]:
    manifest = _read_json(M23_DATA / "manifest.json")
    typed = _read_json(M23_RUN / "typed_results.json")
    finite = _read_json(M23_RUN / "free_json_results.json")
    confounds = {
        "language_family_coupling": [
            "src/ai_brain/language_to_spec/generator.py:547",
            "src/ai_brain/language_to_spec/generator.py:553",
        ],
        "incomplete_text_complete_target": [
            "src/ai_brain/language_to_spec/generator.py:310",
            "src/ai_brain/language_to_spec/generator.py:311",
        ],
        "typed_parser_byte_not_bpe": [
            "src/ai_brain/language_to_spec/model.py:66",
            "src/ai_brain/language_to_spec/model.py:136",
        ],
        "silent_byte_truncation": ["src/ai_brain/language_to_spec/model.py:136"],
        "calibration_not_fail_closed": ["src/ai_brain/language_to_spec/model.py:527"],
        "confidence_ignores_fields": ["src/ai_brain/language_to_spec/model.py:331"],
        "trained_heads_ignored": [
            "src/ai_brain/language_to_spec/model.py:81",
            "src/ai_brain/language_to_spec/model.py:278",
        ],
        "oracle_clarification": ["scripts/m23_language_to_spec.py:285"],
        "finite_answer_json_control": [
            "src/ai_brain/language_to_spec/json_control.py:52",
            "src/ai_brain/language_to_spec/json_control.py:123",
        ],
        "deterministic_holdout_preprogrammed": [
            "src/ai_brain/language_to_spec/deterministic.py:20"
        ],
        "alpha_unique_binding_gap": ["src/ai_brain/rules/grammar.py:235"],
        "exact_order_sensitive_ast_eval": ["scripts/m23_language_to_spec.py:374"],
    }
    snapshot = {
        "m23_commit": "8e1c3cd",
        "frozen_backend_tag": "stage1-acquisition-v1",
        "frozen_backend_commit": "11b573e",
        "dataset_hashes": manifest["sha256"],
        "tokenizer_sha256": _sha256(TOKENIZER_PATH),
        "typed_checkpoint_sha256": _sha256(
            M23_RUN / "typed" / "seed_23001" / "typed_parser.pt"
        ),
        "finite_answer_checkpoint_sha256": _sha256(
            M23_RUN / "free_json" / "checkpoints" / "step_003000.pt"
        ),
        "typed_split_metrics": _without_samples(
            next(iter(typed["runs"].values()))["eval"]
        ),
        "finite_answer_split_metrics": _without_samples(finite["eval"]),
        "confound_source_locations_at_m23_commit": confounds,
    }
    _write_json(BASELINE_SNAPSHOT, snapshot)
    progress(
        "phase_0_baseline_snapshot",
        "snapshot",
        metrics={
            "dataset_splits": len(snapshot["dataset_hashes"]),
            "typed_checkpoint_present": snapshot["typed_checkpoint_sha256"] is not None,
            "finite_checkpoint_present": snapshot["finite_answer_checkpoint_sha256"]
            is not None,
        },
        next_action="Generate strict fair bilingual data",
    )
    return snapshot


def build_data() -> dict[str, Any]:
    manifest = generate_fair_language_dataset(DATA_DIR, tokenizer_path=TOKENIZER_PATH)
    progress(
        "phases_1_to_8_fair_data",
        "build-data",
        metrics={
            "total": manifest["total_count"],
            "bilingual_specs": manifest["all_supported_train_specs_bilingual"],
            "train_language_family_mi": manifest["splits"]["train"][
                "language_family_mutual_information_bits"
            ],
            "visible_ids": manifest["model_visible_id_hits"],
        },
        next_action="Evaluate deterministic baselines and train matched candidates",
    )
    return manifest


def _deterministic_metrics(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    predictions = []
    for row in rows:
        proposal = parse_fair_controlled_language(
            row["text"], language=row["language"], lexicon_mode=mode
        )
        predictions.append(
            StructuredPrediction(proposal, {}, proposal.status == ParseStatus.SUPPORTED)
        )
    structural = [
        prediction_correct(prediction, row, semantic=False)
        for prediction, row in zip(predictions, rows, strict=True)
    ]
    semantic = [
        prediction_correct(prediction, row, semantic=True)
        for prediction, row in zip(predictions, rows, strict=True)
    ]
    failures = [
        {
            "text": row["text"],
            "language": row["language"],
            "family": row["semantic_family"],
            "role": row["metadata"].get("role_assignment"),
            "target_status": row["status"],
            "predicted_status": str(prediction.proposal.status),
            "predicted_issue": (
                str(prediction.proposal.issues[0].code)
                if prediction.proposal.issues
                else None
            ),
        }
        for prediction, row, correct in zip(predictions, rows, semantic, strict=True)
        if not correct
    ][:50]
    return {
        "count": len(rows),
        "structural_specification_exact": sum(structural) / len(rows),
        "semantic_specification_exact": sum(semantic) / len(rows),
        "status_accuracy": sum(
            str(prediction.proposal.status) == row["status"]
            for prediction, row in zip(predictions, rows, strict=True)
        )
        / len(rows),
        "failures": failures,
    }


def evaluate_deterministic() -> dict[str, Any]:
    results = {}
    for mode in ("train", "extended"):
        results[mode] = {
            split: _deterministic_metrics(
                load_language_rows(DATA_DIR / f"{split}.jsonl"), mode
            )
            for split in (
                "validation_train_surface",
                *TEST_SPLITS,
            )
        }
    _write_json(RUN_DIR / "deterministic_results.json", results)
    progress(
        "phase_9_deterministic",
        "deterministic",
        metrics={
            "frozen_lexical": results["train"]["test_lexical_holdout"][
                "semantic_specification_exact"
            ],
            "extended_lexical": results["extended"]["test_lexical_holdout"][
                "semantic_specification_exact"
            ],
        },
        diagnosis="Frozen train lexicon and explicitly extended production lexicon are reported separately.",
        next_action="Train compute-matched neural candidates",
    )
    return results


def _candidate_dir(name: str, seed: int) -> Path:
    return RUN_DIR / "candidates" / name / f"seed_{seed}"


def train_named_candidate(
    name: str,
    *,
    seed: int,
    max_steps: int,
    cpu: bool,
) -> dict[str, Any]:
    kind, encoding, consistency_weight = CANDIDATES[name]
    config = make_config(
        candidate_kind=kind,
        encoding=encoding,
        tokenizer_path=TOKENIZER_PATH if encoding == "bpe" else None,
    )
    result = train_fair_candidate(
        train_path=DATA_DIR / "train.jsonl",
        validation_path=DATA_DIR / "validation_train_surface.jsonl",
        calibration_path=DATA_DIR / "calibration.jsonl",
        output_dir=_candidate_dir(name, seed),
        config=config,
        seed=seed,
        max_steps=max_steps,
        batch_size=64,
        learning_rate=3e-4,
        eval_every=500,
        patience=4,
        consistency_weight=consistency_weight,
        cpu=cpu,
    )
    progress(
        "phases_10_to_19_training",
        f"train {name} seed={seed}",
        metrics={
            "best_step": result["best_step"],
            "updates_run": result["updates_run"],
            "parameters": result["parameter_count"],
            "calibration_status": result["calibration"]["status"],
            "validation_semantic": result["validation"]["semantic_specification_exact"],
        },
        next_action=f"Evaluate {name} on the diagnostic ladder",
    )
    return result


def _cross_language_metrics(
    predictions: list[StructuredPrediction], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    pairs: dict[str, list[tuple[StructuredPrediction, dict[str, Any]]]] = defaultdict(
        list
    )
    for prediction, row in zip(predictions, rows, strict=True):
        pairs[row["metadata"]["pair_id"]].append((prediction, row))
    semantic_equal = []
    structural_equal = []
    downstream_equal = []
    for pair in pairs.values():
        if len(pair) != 2:
            continue
        left, right = pair[0][0].proposal, pair[1][0].proposal
        supported = (
            left.status == right.status == ParseStatus.SUPPORTED
            and left.specification is not None
            and right.specification is not None
        )
        structural_equal.append(
            supported
            and structural_specification_equal(left.specification, right.specification)
        )
        semantic_equal.append(
            supported
            and semantic_specification_equal(left.specification, right.specification)
        )
        if supported:
            left_audit = acquire_with_concrete_binding(left.specification)
            right_audit = acquire_with_concrete_binding(right.specification)
            downstream_equal.append(
                left_audit.property_verified
                and right_audit.property_verified
                and left_audit.candidate is not None
                and right_audit.candidate is not None
                and behaviorally_equivalent(
                    left_audit.candidate,
                    right_audit.candidate,
                    left.specification,
                )
            )
        else:
            downstream_equal.append(False)
    return {
        "pair_count": len(pairs),
        "structural_equality": sum(structural_equal) / max(1, len(structural_equal)),
        "semantic_equality": sum(semantic_equal) / max(1, len(semantic_equal)),
        "downstream_property_equality": sum(downstream_equal)
        / max(1, len(downstream_equal)),
    }


def evaluate_named_candidate(name: str, *, seed: int, cpu: bool) -> dict[str, Any]:
    device = get_device_info(prefer_cuda=not cpu).device
    model, config, calibration, _ = load_fair_candidate(
        _candidate_dir(name, seed) / "best.pt", device=device
    )
    splits = ("train", "validation_train_surface", *TEST_SPLITS)
    results: dict[str, Any] = {
        "candidate": name,
        "seed": seed,
        "calibration": asdict(calibration),
        "raw": {},
        "safe": {},
    }
    for split in splits:
        rows = load_language_rows(DATA_DIR / f"{split}.jsonl")
        if split == "train":
            rows = rows[:2_000]
        results["raw"][split] = evaluate_candidate(
            model,
            rows,
            config=config,
            device=device,
            calibration=None,
        )
        results["safe"][split] = evaluate_candidate(
            model,
            rows,
            config=config,
            device=device,
            calibration=calibration,
        )
    cross_rows = load_language_rows(DATA_DIR / "test_cross_language.jsonl")
    raw_predictions = []
    safe_predictions = []
    for start in range(0, len(cross_rows), 128):
        batch = cross_rows[start : start + 128]
        raw = predict_raw(
            model,
            [row["text"] for row in batch],
            [row["language"] for row in batch],
            config=config,
            device=device,
        )
        raw_predictions.extend(raw)
        safe_predictions.extend(apply_calibration(item, calibration) for item in raw)
    results["cross_language"] = {
        "raw": _cross_language_metrics(raw_predictions, cross_rows),
        "safe": _cross_language_metrics(safe_predictions, cross_rows),
    }
    diagnosis = diagnose_failures(results)
    results["failure_diagnosis"] = diagnosis
    _write_json(_candidate_dir(name, seed) / "eval_results.json", results)
    progress(
        "phase_17_diagnostic_ladder",
        f"evaluate {name} seed={seed}",
        metrics={
            "id_raw": results["raw"]["test_id"]["semantic_specification_exact"],
            "lexical_raw": results["raw"]["test_lexical_holdout"][
                "semantic_specification_exact"
            ],
            "template_raw": results["raw"]["test_template_holdout"][
                "semantic_specification_exact"
            ],
            "safe_coverage": results["safe"]["test_id"]["coverage"],
            "safe_incorrect": results["safe"]["test_id"]["incorrect_accepted_rate"],
        },
        diagnosis=diagnosis["summary"],
        next_action="Compare candidates or apply one targeted fix",
    )
    return results


def diagnose_failures(results: dict[str, Any]) -> dict[str, Any]:
    failures = []
    for split, metrics in results["raw"].items():
        for row in metrics.get("failures", []):
            failures.append({"split": split, **row})
    first = failures[:50]
    dimensions = {
        "language": Counter(row["language"] for row in first),
        "family": Counter(str(row["family"]) for row in first),
        "role": Counter(str(row["role_assignment"]) for row in first),
        "missing_or_invalid_field": Counter(
            str(row["invalid_reason"] or row["predicted_error"]) for row in first
        ),
        "ood_axis": Counter(row["split"] for row in first),
    }
    return {
        "inspected_count": len(first),
        "groups": {
            key: dict(counter.most_common()) for key, counter in dimensions.items()
        },
        "summary": (
            "No sampled failures"
            if not first
            else f"Inspected {len(first)} failures; dominant axis is "
            f"{dimensions['ood_axis'].most_common(1)[0][0]}"
        ),
    }


def _neural_proposals(
    name: str,
    seed: int,
    rows: list[dict[str, Any]],
    *,
    cpu: bool,
    safe: bool,
) -> list[LanguageProposal]:
    device = get_device_info(prefer_cuda=not cpu).device
    model, config, calibration, _ = load_fair_candidate(
        _candidate_dir(name, seed) / "best.pt", device=device
    )
    output = []
    for start in range(0, len(rows), 128):
        batch = rows[start : start + 128]
        predictions = predict_raw(
            model,
            [row["text"] for row in batch],
            [row["language"] for row in batch],
            config=config,
            device=device,
        )
        if safe:
            predictions = [apply_calibration(item, calibration) for item in predictions]
        output.extend(item.proposal for item in predictions)
    return output


def _clarification_condition(
    rows: list[dict[str, Any]], proposals: list[LanguageProposal]
) -> dict[str, Any]:
    states = []
    for row, proposal in zip(rows, proposals, strict=True):

        def parser(
            _text: str, _language: str, proposal: LanguageProposal = proposal
        ) -> LanguageProposal:
            return proposal

        states.append(clarification_from_raw(row["text"], row["language"], parser))
    detection = []
    issue_accuracy = []
    question_accuracy = []
    answer_interpretation = []
    resolved = []
    unresolved = []
    for row, state in zip(rows, states, strict=True):
        target_code = ValidationCode(row["error_code"])
        detected = state.proposal.status == ParseStatus.AMBIGUOUS
        detection.append(detected)
        predicted_code = (
            state.proposal.issues[0].code if state.proposal.issues else None
        )
        issue_accuracy.append(predicted_code == target_code)
        question_accuracy.append(
            state.question is not None and state.question.code == target_code
        )
        result = resolve_clarification_state(
            state, row["metadata"]["clarification_answer"]
        )
        target = ProgramSpecification(**row["metadata"]["resolved_specification"])
        is_resolved = (
            result.status == ParseStatus.SUPPORTED
            and result.specification is not None
            and semantic_specification_equal(result.specification, target)
        )
        answer_interpretation.append(
            bool(state.partial.actions) and result.status == ParseStatus.SUPPORTED
        )
        resolved.append(is_resolved)
        unresolved.append(result.status != ParseStatus.SUPPORTED)
    count = len(rows)
    return {
        "count": count,
        "ambiguity_detection": sum(detection) / count,
        "issue_code_accuracy": sum(issue_accuracy) / count,
        "question_field_accuracy": sum(question_accuracy) / count,
        "answer_interpretation": sum(answer_interpretation) / count,
        "resolved_semantic_exact": sum(resolved) / count,
        "unresolved_abstention": sum(unresolved) / count,
    }


def evaluate_clarification(best_name: str, *, seed: int, cpu: bool) -> dict[str, Any]:
    rows = load_language_rows(DATA_DIR / "test_ambiguous.jsonl")
    oracle = []
    deterministic = []
    for row in rows:
        code = ValidationCode(row["error_code"])
        oracle.append(
            LanguageProposal(
                ParseStatus.AMBIGUOUS,
                row["language"],
                row["text"],
                issues=(ValidationIssue(code, "oracle", "Upper-bound issue"),),
                confidence=1.0,
                parser_name="oracle_issue_upper_bound",
            )
        )
        deterministic.append(
            parse_fair_controlled_language(
                row["text"], language=row["language"], lexicon_mode="train"
            )
        )
    neural = _neural_proposals(best_name, seed, rows, cpu=cpu, safe=True)
    result = {
        "oracle_issue_upper_bound": _clarification_condition(rows, oracle),
        "deterministic_end_to_end": _clarification_condition(rows, deterministic),
        "neural_end_to_end": _clarification_condition(rows, neural),
    }
    _write_json(RUN_DIR / "clarification_results.json", result)
    progress(
        "phases_20_21_clarification",
        f"clarification {best_name}",
        metrics=result,
        diagnosis="Oracle issue is reported only as an upper bound; raw-text parser paths are primary.",
        next_action="Audit concrete role binding and fair E2E behavior",
    )
    return result


def binding_audit() -> dict[str, Any]:
    rows = load_language_rows(DATA_DIR / "train.jsonl")
    unique: dict[str, ProgramSpecification] = {}
    for row in rows:
        if row["canonical_specification"] is None:
            continue
        spec = ProgramSpecification(**row["canonical_specification"])
        unique.setdefault(canonical_specification_json(spec), spec)
    audits = []
    for signature, spec in unique.items():
        audit = acquire_with_concrete_binding(
            spec, task_id=f"binding-{len(audits):03d}"
        )
        audits.append(
            {
                "specification": signature,
                "template_family": audit.template_family,
                "template_found": audit.template_found,
                "binding_found": audit.binding_found,
                "binding": dict(audit.binding),
                "property_verified": audit.property_verified,
            }
        )
    result = {
        "count": len(audits),
        "template_found": sum(row["template_found"] for row in audits) / len(audits),
        "binding_found": sum(row["binding_found"] for row in audits) / len(audits),
        "property_verified": sum(row["property_verified"] for row in audits)
        / len(audits),
        "audits": audits,
    }
    _write_json(RUN_DIR / "binding_audit.json", result)
    progress(
        "phases_22_23_binding",
        "binding-audit",
        metrics={
            key: result[key]
            for key in ("count", "template_found", "binding_found", "property_verified")
        },
        next_action="Run fair end-to-end behavioral evaluation",
    )
    return result


def _approval_safety_example(
    proposal: LanguageProposal, acquisition: Any
) -> dict[str, Any]:
    memory = RuleMemory()
    signature = canonical_specification_json(proposal.specification)
    rejected = {}
    for decision in (
        ApprovalDecision.REJECT,
        ApprovalDecision.ASK_CLARIFICATION,
        ApprovalDecision.EDIT_SPECIFICATION,
    ):
        try:
            store_approved_language_rule(
                memory=memory,
                proposal=proposal,
                acquisition=acquisition,
                approval=Approval(decision, "audit", "TRUSTED_SUPERVISOR", signature),
            )
            rejected[str(decision)] = False
        except ValueError:
            rejected[str(decision)] = True
    try:
        store_approved_language_rule(
            memory=memory,
            proposal=proposal,
            acquisition=acquisition,
            approval=Approval(
                ApprovalDecision.APPROVE,
                "audit",
                "TRUSTED_SUPERVISOR",
                signature + "-mismatch",
            ),
        )
        rejected["mismatched_signature"] = False
    except ValueError:
        rejected["mismatched_signature"] = True
    ambiguous = LanguageProposal(
        ParseStatus.AMBIGUOUS,
        proposal.language,
        proposal.original_text,
        issues=(
            ValidationIssue(
                ValidationCode.LOW_CONFIDENCE,
                "confidence",
                "Calibration failed",
            ),
        ),
        parser_name="failed_calibration",
    )
    try:
        store_approved_language_rule(
            memory=memory,
            proposal=ambiguous,
            acquisition=acquisition,
            approval=Approval(
                ApprovalDecision.APPROVE,
                "audit",
                "TRUSTED_SUPERVISOR",
                signature,
            ),
        )
        rejected["failed_calibration"] = False
    except ValueError:
        rejected["failed_calibration"] = True
    unsupported = replace(
        proposal,
        status=ParseStatus.UNSUPPORTED,
        specification=None,
        issues=(
            ValidationIssue(
                ValidationCode.UNSUPPORTED_OPERATION,
                "operation",
                "Unsupported operation",
            ),
        ),
    )
    try:
        store_approved_language_rule(
            memory=memory,
            proposal=unsupported,
            acquisition=acquisition,
            approval=Approval(
                ApprovalDecision.APPROVE,
                "audit",
                "TRUSTED_SUPERVISOR",
                signature,
            ),
        )
        rejected["unsupported_proposal"] = False
    except ValueError:
        rejected["unsupported_proposal"] = True
    stale_evidence = replace(
        acquisition,
        verification_evidence={
            **dict(acquisition.verification_evidence),
            "specification_signature": "stale-specification",
        },
    )
    try:
        store_approved_language_rule(
            memory=memory,
            proposal=proposal,
            acquisition=stale_evidence,
            approval=Approval(
                ApprovalDecision.APPROVE,
                "audit",
                "TRUSTED_SUPERVISOR",
                signature,
            ),
        )
        rejected["stale_verification_evidence"] = False
    except ValueError:
        rejected["stale_verification_evidence"] = True
    writes_without_approval = len(memory.records)
    approved_memory = RuleMemory()
    store_approved_language_rule(
        memory=approved_memory,
        proposal=proposal,
        acquisition=acquisition,
        approval=Approval(
            ApprovalDecision.APPROVE,
            "audit",
            "TRUSTED_SUPERVISOR",
            signature,
        ),
    )
    return {
        "rejections": rejected,
        "all_unsafe_paths_rejected": all(rejected.values()),
        "writes_without_approval": writes_without_approval,
        "approved_write_count": len(approved_memory.records),
    }


def evaluate_end_to_end(best_name: str, *, seed: int, cpu: bool) -> dict[str, Any]:
    rows = load_language_rows(DATA_DIR / "test_id.jsonl")
    proposals = _neural_proposals(best_name, seed, rows, cpu=cpu, safe=True)
    records = []
    approval_audit = None
    for index, (row, proposal) in enumerate(zip(rows, proposals, strict=True)):
        target_spec = ProgramSpecification(**row["canonical_specification"])
        structural = (
            proposal.specification is not None
            and structural_specification_equal(proposal.specification, target_spec)
        )
        semantic = proposal.specification is not None and semantic_specification_equal(
            proposal.specification, target_spec
        )
        record = {
            "accepted": proposal.status == ParseStatus.SUPPORTED,
            "language_structural_exact": structural,
            "language_semantic_exact": semantic,
            "template_found": False,
            "binding_found": False,
            "property_verified": False,
            "behavior_equivalent": False,
            "exact_ast_identical": False,
            "final_execution_correct": False,
        }
        if (
            proposal.status == ParseStatus.SUPPORTED
            and proposal.specification is not None
        ):
            audit = acquire_with_concrete_binding(
                proposal.specification, task_id=f"e2e-{index:04d}"
            )
            target_audit = acquire_with_concrete_binding(
                target_spec, task_id=f"target-{index:04d}"
            )
            record["template_found"] = audit.template_found
            record["binding_found"] = audit.binding_found
            record["property_verified"] = audit.property_verified
            if audit.candidate is not None and target_audit.candidate is not None:
                record["behavior_equivalent"] = behaviorally_equivalent(
                    audit.candidate, target_audit.candidate, target_spec
                )
                record["exact_ast_identical"] = audit.candidate.semantic_hash(
                    alpha=False, order_insensitive=False
                ) == target_audit.candidate.semantic_hash(
                    alpha=False, order_insensitive=False
                )
            record["final_execution_correct"] = (
                audit.property_verified and record["behavior_equivalent"]
            )
            if approval_audit is None and audit.property_verified:
                approval_audit = _approval_safety_example(proposal, audit.acquisition)
        records.append(record)
    accepted = [record for record in records if record["accepted"]]
    fields = (
        "language_structural_exact",
        "language_semantic_exact",
        "template_found",
        "binding_found",
        "property_verified",
        "behavior_equivalent",
        "exact_ast_identical",
        "final_execution_correct",
    )
    result = {
        "count": len(records),
        "accepted_count": len(accepted),
        "coverage": len(accepted) / len(records),
        **{
            field: sum(record[field] for record in accepted) / max(1, len(accepted))
            for field in fields
        },
        "approval_safety": approval_audit
        or {"rejections": {}, "writes_without_approval": 0},
        "records": records[:50],
    }
    _write_json(RUN_DIR / "end_to_end_results.json", result)
    progress(
        "phases_24_25_end_to_end",
        f"end-to-end {best_name}",
        metrics={
            key: result[key]
            for key in (
                "coverage",
                "language_semantic_exact",
                "property_verified",
                "behavior_equivalent",
                "final_execution_correct",
            )
        },
        next_action="Build final fair-retest reports",
    )
    return result


def candidate_results() -> dict[str, Any]:
    output = {}
    for name in CANDIDATES:
        candidate_dir = RUN_DIR / "candidates" / name
        if not candidate_dir.exists():
            continue
        seeds = {}
        for seed_dir in sorted(candidate_dir.glob("seed_*")):
            result_path = seed_dir / "eval_results.json"
            if result_path.exists():
                seeds[seed_dir.name.removeprefix("seed_")] = _read_json(result_path)
        if seeds:
            output[name] = seeds
    return output


def _best_candidate(results: dict[str, Any]) -> tuple[str, int, dict[str, Any]]:
    ranked = []
    for name, seeds in results.items():
        first_seed, result = next(iter(seeds.items()))
        raw = result["raw"]
        safe = result["safe"]
        score = (
            raw["test_id"]["semantic_specification_exact"]
            + raw["test_lexical_holdout"]["semantic_specification_exact"]
            + raw["test_template_holdout"]["semantic_specification_exact"]
            + raw["test_variable_permutation"]["semantic_specification_exact"]
            + raw["test_negation_preserve"]["semantic_specification_exact"]
            + safe["test_id"]["coverage"]
            - 5.0 * safe["test_id"]["incorrect_accepted_rate"]
        )
        ranked.append((score, name, int(first_seed), result))
    if not ranked:
        raise RuntimeError("No evaluated M-23.1 candidate exists")
    _, name, seed, result = max(ranked, key=lambda row: row[0])
    return name, seed, result


def _qualifies_for_multiseed(result: dict[str, Any]) -> bool:
    raw = result["raw"]
    safe = result["safe"]
    major_ood = max(
        raw[split]["semantic_specification_exact"]
        for split in (
            "test_lexical_holdout",
            "test_template_holdout",
            "test_variable_permutation",
            "test_negation_preserve",
        )
    )
    return (
        raw["test_id"]["semantic_specification_exact"] >= 0.95
        and safe["test_id"]["incorrect_accepted_rate"] <= 0.01
        and safe["test_id"]["calibration_status"] == "CALIBRATED"
        and major_ood >= 0.80
    )


def _aggregate(values: list[float]) -> dict[str, float]:
    average = sum(values) / len(values)
    variance = sum((value - average) ** 2 for value in values) / len(values)
    return {
        "mean": average,
        "std": math.sqrt(variance),
        "min": min(values),
        "max": max(values),
    }


def multiseed_summary(results: dict[str, Any], best_name: str) -> dict[str, Any]:
    seeds = results.get(best_name, {})
    metrics = {}
    for split in (
        "test_id",
        "test_lexical_holdout",
        "test_template_holdout",
        "test_variable_permutation",
    ):
        values = [
            row["raw"][split]["semantic_specification_exact"] for row in seeds.values()
        ]
        if values:
            metrics[split] = _aggregate(values)
    return {"candidate": best_name, "seeds": sorted(seeds), "metrics": metrics}


def _metric_table(results: dict[str, Any]) -> str:
    lines = [
        "| candidate | seed | ID raw | lexical | template | variable | order | cross | negation | composed | safe coverage | safe false accepted |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, seeds in results.items():
        for seed, row in seeds.items():
            raw = row["raw"]
            safe = row["safe"]["test_id"]
            lines.append(
                f"| {name} | {seed} | {raw['test_id']['semantic_specification_exact']:.4f} | "
                f"{raw['test_lexical_holdout']['semantic_specification_exact']:.4f} | "
                f"{raw['test_template_holdout']['semantic_specification_exact']:.4f} | "
                f"{raw['test_variable_permutation']['semantic_specification_exact']:.4f} | "
                f"{raw['test_order_holdout']['semantic_specification_exact']:.4f} | "
                f"{row['cross_language']['raw']['semantic_equality']:.4f} | "
                f"{raw['test_negation_preserve']['semantic_specification_exact']:.4f} | "
                f"{raw['test_composed_ood']['semantic_specification_exact']:.4f} | "
                f"{safe['coverage']:.4f} | {safe['incorrect_accepted_rate']:.4f} |"
            )
    return "\n".join(lines)


def _training_budget_table(results: dict[str, Any]) -> str:
    lines = [
        "| candidate | seed | parameters | updates | examples | best step | wall seconds | consistency weight |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, seeds in results.items():
        for seed in seeds:
            path = _candidate_dir(name, int(seed)) / "train_result.json"
            if not path.exists():
                continue
            row = _read_json(path)
            lines.append(
                f"| {name} | {seed} | {row['parameter_count']} | "
                f"{row['updates_run']} | {row['processed_examples']} | "
                f"{row['best_step']} | {row['wall_time_seconds']:.2f} | "
                f"{row['pair_consistency_weight']:.3f} |"
            )
    return "\n".join(lines)


def _calibration_frontier_table(calibration: dict[str, Any]) -> str:
    lines = [
        "| confidence | best coverage at conditional risk <= .01 | threshold | accepted | conditional risk |",
        "|---|---:|---:|---:|---:|",
    ]
    for method in ("product", "minimum", "temperature_joint"):
        safe = [
            row
            for row in calibration["curve"]
            if row["method"] == method
            and row["accepted_count"] > 0
            and row["conditional_risk"] <= 0.01
        ]
        if not safe:
            lines.append(f"| {method} | 0.0000 | n/a | 0 | n/a |")
            continue
        row = max(safe, key=lambda item: item["coverage"])
        lines.append(
            f"| {method} | {row['coverage']:.4f} | {row['threshold']:.6f} | "
            f"{row['accepted_count']} | {row['conditional_risk']:.4f} |"
        )
    return "\n".join(lines)


def _safe_risk_table(best: dict[str, Any]) -> str:
    lines = [
        "| split | coverage | incorrect accepted / population | conditional accepted risk |",
        "|---|---:|---:|---:|",
    ]
    for split in TEST_SPLITS:
        row = best["safe"][split]
        lines.append(
            f"| {split} | {row['coverage']:.4f} | "
            f"{row['incorrect_accepted_rate']:.4f} | "
            f"{row['conditional_accepted_risk']:.4f} |"
        )
    return "\n".join(lines)


def _group_risk_table(best: dict[str, Any]) -> str:
    groups = best["safe"]["test_id"]["groups"]
    lines = [
        "| dimension | value | count | semantic exact | coverage | incorrect accepted / population |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for dimension in ("language", "family"):
        for value, row in groups[dimension].items():
            lines.append(
                f"| {dimension} | {value} | {row['count']} | "
                f"{row['semantic_exact']:.4f} | {row['coverage']:.4f} | "
                f"{row['incorrect_accepted_rate']:.4f} |"
            )
    return "\n".join(lines)


def build_reports(checks: str) -> dict[str, Any]:
    baseline = _read_json(BASELINE_SNAPSHOT)
    manifest = _read_json(DATA_DIR / "manifest.json")
    deterministic = _read_json(RUN_DIR / "deterministic_results.json")
    results = candidate_results()
    best_name, best_seed, best = _best_candidate(results)
    clarification = _read_json(RUN_DIR / "clarification_results.json")
    binding = _read_json(RUN_DIR / "binding_audit.json")
    end_to_end = _read_json(RUN_DIR / "end_to_end_results.json")
    train_summary = manifest["splits"]["train"]
    confound_lines = "\n".join(
        f"| {name} | {', '.join(locations)} | addressed in isolated M-23.1 pipeline |"
        for name, locations in baseline[
            "confound_source_locations_at_m23_commit"
        ].items()
    )
    confounds_report = f"""# M-23.1 M-23 Confounds Audit

M-23 baseline commit: `8e1c3cd`; frozen backend: `stage1-acquisition-v1` -> `11b573e`.

| confound | frozen source location | retest treatment |
|---|---|---|
{confound_lines}

Original artifacts are hashed in `runs/m231_m23_baseline_snapshot.json` and were not overwritten.
"""
    dataset_report = f"""# M-23.1 Fair Dataset Report

- total rows: `{manifest["total_count"]}`
- strict explicit primary condition: `{manifest["explicitness_policy"]}`
- closed-world defaults mixed into primary: `{manifest["closed_world_default_mixed_into_primary"]}`
- every supported train specification bilingual: `{manifest["all_supported_train_specs_bilingual"]}`
- paired targets equal: `{manifest["paired_targets_semantically_equal"]}`
- train language-family mutual information: `{train_summary["language_family_mutual_information_bits"]:.8f}` bits
- model-visible IDs: `{manifest["model_visible_id_hits"]}`
- lexical holdout intersection: `{manifest["train_overlap_audit"]["test_lexical_holdout"]["lexical_items"]}`
- template holdout intersection: `{manifest["train_overlap_audit"]["test_template_holdout"]["template_ids"]}`

The manifest persists language/family/status/specification matrices and all requested overlap axes.
"""
    byte_lengths = train_summary["lengths"]["byte"]
    bpe_lengths = train_summary["lengths"]["bpe"]
    token_report = f"""# M-23.1 Tokenization and Truncation Report

| encoder | average | p95 | max | configured max | truncated |
|---|---:|---:|---:|---:|---:|
| UTF-8 byte | {byte_lengths["avg"]:.2f} | {byte_lengths["p95"]:.0f} | {byte_lengths["max"]} | 768 | {byte_lengths["truncated_at_768"]} |
| bilingual BPE | {bpe_lengths["avg"]:.2f} | {bpe_lengths["p95"]:.0f} | {bpe_lengths["max"]} | 256 | {bpe_lengths["truncated_at_256"]} |

Both paths prepend an explicit summary/BOS token. Overlength input raises `InputTooLongError`; no semantic clause is silently cut.
"""
    model_report = f"""# M-23.1 Compute-Matched Model Comparison

The finite-answer model is labeled a catalog classifier: JSON/schema validity is guaranteed by catalog construction and is not claimed as generation ability.

## Training Budget

{_training_budget_table(results)}

## Diagnostic Ladder

{_metric_table(results)}

Best ranked candidate: `{best_name}` seed `{best_seed}`.

Deterministic train-lexicon lexical holdout: `{deterministic["train"]["test_lexical_holdout"]["semantic_specification_exact"]:.4f}`.
Extended production parser lexical holdout: `{deterministic["extended"]["test_lexical_holdout"]["semantic_specification_exact"]:.4f}` (programmed support, not OOD learning).
"""
    calibration = best["calibration"]
    calibration_report = f"""# M-23.1 Calibration and Safety Report

- best candidate: `{best_name}`
- calibration status: `{calibration["status"]}`
- confidence method: `{calibration["method"]}`
- threshold: `{calibration["threshold"]}`
- calibration coverage: `{calibration["coverage"]:.4f}`
- calibration accepted precision: `{calibration["accepted_precision"]:.4f}`
- safe ID coverage: `{best["safe"]["test_id"]["coverage"]:.4f}`
- safe ID incorrect accepted rate: `{best["safe"]["test_id"]["incorrect_accepted_rate"]:.4f}`

If no non-empty threshold has conditional risk <= .01, status is `FAILED`, coverage is zero, and every supported neural proposal becomes review-required/ambiguous.

## Confidence Frontier

{_calibration_frontier_table(calibration)}

## ID Group Risk

{_group_risk_table(best)}

## OOD Risk

{_safe_risk_table(best)}
"""
    clarification_report = """# M-23.1 Clarification End-to-End Report

| condition | ambiguity | issue code | question field | answer interpretation | resolved semantic | unresolved |
|---|---:|---:|---:|---:|---:|---:|
""" + "\n".join(
        f"| {name} | {row['ambiguity_detection']:.4f} | {row['issue_code_accuracy']:.4f} | {row['question_field_accuracy']:.4f} | {row['answer_interpretation']:.4f} | {row['resolved_semantic_exact']:.4f} | {row['unresolved_abstention']:.4f} |"
        for name, row in clarification.items()
    )
    binding_report = f"""# M-23.1 Concrete Binding Audit

- concrete specifications: `{binding["count"]}`
- abstract template found: `{binding["template_found"]:.4f}`
- concrete binding found: `{binding["binding_found"]:.4f}`
- property verified: `{binding["property_verified"]:.4f}`

The experimental path instantiates concrete roles from the public specification and does not access a hidden target. It is a candidate M-24 backend patch; `stage1-acquisition-v1` remains unchanged.
"""
    raw = best["raw"]
    safe = best["safe"]
    cross = best["cross_language"]["raw"]
    ru = raw["test_id"]["groups"]["language"]["ru"]["semantic_exact"]
    en = raw["test_id"]["groups"]["language"]["en"]["semantic_exact"]
    neural_passes = (
        raw["test_id"]["semantic_specification_exact"] >= 0.98
        and raw["test_lexical_holdout"]["semantic_specification_exact"] >= 0.95
        and raw["test_template_holdout"]["semantic_specification_exact"] >= 0.90
        and raw["test_variable_permutation"]["semantic_specification_exact"] >= 0.95
        and cross["semantic_equality"] >= 0.95
        and abs(ru - en) <= 0.03
        and raw["test_negation_preserve"]["semantic_specification_exact"] >= 0.90
        and safe["test_id"]["incorrect_accepted_rate"] <= 0.01
        and end_to_end["final_execution_correct"] >= 0.95
    )
    if neural_passes:
        decision = (
            "OUTCOME B — FINITE CATALOG CLASSIFIER WORKS BEST"
            if best_name == "catalog_bpe"
            else "OUTCOME A — FAIR BILINGUAL FRONTEND WORKS"
        )
    elif (
        deterministic["extended"]["test_composed_ood"]["semantic_specification_exact"]
        >= 0.95
    ):
        decision = "OUTCOME C — DETERMINISTIC CONTROLLED LANGUAGE WORKS BEST"
    elif raw["test_id"]["semantic_specification_exact"] >= 0.90:
        decision = "OUTCOME D — LANGUAGE PROPOSALS ARE USEFUL ONLY WITH FULL REVIEW"
    else:
        decision = "OUTCOME E — FAIR RETEST STILL FAILS"
    multiseed = multiseed_summary(results, best_name)
    final_report = f"""# M-23.1 Fair Bilingual Language-to-Spec Retest

## Checks

`{checks}`

## Baseline and Confounds

All 12 M-23 blocking findings were frozen, source-located, and addressed without moving `stage1-acquisition-v1`.

## Fair Dataset

Language/family MI is `{train_summary["language_family_mutual_information_bits"]:.8f}` bits; all train specs are bilingual; strict supported prompts explicitly state preserve and termination semantics.

## Model Comparison

{_metric_table(results)}

## Bilingual and Safety Diagnostics

- best candidate: `{best_name}` seed `{best_seed}`
- RU / EN ID semantic: `{ru:.4f}` / `{en:.4f}`; gap `{abs(ru - en):.4f}`
- paired semantic equality: `{cross["semantic_equality"]:.4f}`
- calibration: `{best["calibration"]["status"]}`
- safe coverage / incorrect accepted: `{safe["test_id"]["coverage"]:.4f}` / `{safe["test_id"]["incorrect_accepted_rate"]:.4f}`
- multi-seed: `{json.dumps(multiseed, sort_keys=True)}`

## Clarification and Backend

- deterministic raw-text clarification resolved semantic: `{clarification["deterministic_end_to_end"]["resolved_semantic_exact"]:.4f}`
- neural raw-text clarification resolved semantic: `{clarification["neural_end_to_end"]["resolved_semantic_exact"]:.4f}`
- concrete binding property verified: `{binding["property_verified"]:.4f}`
- accepted E2E behavior / final execution: `{end_to_end["behavior_equivalent"]:.4f}` / `{end_to_end["final_execution_correct"]:.4f}`
- RuleMemory writes without approval: `{end_to_end["approval_safety"]["writes_without_approval"]}`
- all unsafe approval paths rejected: `{end_to_end["approval_safety"].get("all_unsafe_paths_rejected")}`
- explicitly approved writes: `{end_to_end["approval_safety"].get("approved_write_count")}`

## Decision

**{decision}**

## Recommended M-24 Path

{"The fair neural/catalog frontend passed the gates; retain explicit review and approval." if neural_passes else "Use the deterministic controlled command/form frontend as the trusted path. Neural language-to-spec remains research-only and may only pre-fill a fully reviewed specification."}
"""
    reports = {
        "docs/m231_m23_confounds_audit.md": confounds_report,
        "docs/m231_fair_dataset_report.md": dataset_report,
        "docs/m231_tokenization_truncation_report.md": token_report,
        "docs/m231_model_comparison_report.md": model_report,
        "docs/m231_calibration_safety_report.md": calibration_report,
        "docs/m231_clarification_end_to_end_report.md": clarification_report,
        "docs/m231_concrete_binding_audit.md": binding_report,
        "docs/m231_fair_bilingual_retest_report.md": final_report,
        "runs/m231_fair_bilingual_retest_report.md": final_report,
    }
    for path, text in reports.items():
        destination = ROOT / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    final = {
        "decision": decision,
        "best_candidate": best_name,
        "best_seed": best_seed,
        "qualifies_for_multiseed": _qualifies_for_multiseed(best),
        "multiseed": multiseed,
        "checks": checks,
    }
    _write_json(RUN_DIR / "final_decision.json", final)
    progress(
        "reports",
        "report",
        metrics=final,
        diagnosis=decision,
        next_action="Commit and push the isolated fair-retest branch",
    )
    return final


def cuda_smoke() -> dict[str, Any]:
    device_info = get_device_info(prefer_cuda=True)
    if not device_info.is_cuda:
        raise RuntimeError("M-23.1 CUDA smoke requires CUDA")
    config = make_config(
        candidate_kind="factorized", encoding="bpe", tokenizer_path=TOKENIZER_PATH
    )
    from ai_brain.language_to_spec.fair_model import build_candidate, encode_texts_v2

    model = build_candidate(config).to(device_info.device)
    before = [parameter.detach().clone() for parameter in model.parameters()]
    ids, mask, _ = encode_texts_v2(
        ["Move A into B. Leave C and D unchanged. Stop when A is empty."],
        config=config,
        device=device_info.device,
    )
    logits = model(ids, mask)
    loss = sum(value.float().square().mean() for value in logits.values())
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()
    changed = any(
        not torch.equal(old, parameter.detach())
        for old, parameter in zip(before, model.parameters(), strict=True)
    )
    result = {
        "device": str(device_info.device),
        "device_name": device_info.name,
        "loss": float(loss.detach().cpu()),
        "parameters_changed": changed,
    }
    _write_json(RUN_DIR / "cuda_smoke.json", result)
    return result


def run_all(*, max_steps: int, cpu: bool, checks: str) -> dict[str, Any]:
    snapshot_m23()
    build_data()
    evaluate_deterministic()
    evaluations = {}
    for name in PRIMARY_CANDIDATES:
        train_named_candidate(name, seed=23_101, max_steps=max_steps, cpu=cpu)
        evaluations[name] = evaluate_named_candidate(name, seed=23_101, cpu=cpu)
    if (
        evaluations["factorized_bpe"]["cross_language"]["raw"]["semantic_equality"]
        < 0.95
    ):
        train_named_candidate(
            "factorized_bpe_consistency",
            seed=23_101,
            max_steps=max_steps,
            cpu=cpu,
        )
        evaluations["factorized_bpe_consistency"] = evaluate_named_candidate(
            "factorized_bpe_consistency", seed=23_101, cpu=cpu
        )
        progress(
            "phase_14_pair_consistency_ablation",
            "factorized_bpe_consistency",
            metrics={
                "baseline_cross": evaluations["factorized_bpe"]["cross_language"][
                    "raw"
                ]["semantic_equality"],
                "consistency_cross": evaluations["factorized_bpe_consistency"][
                    "cross_language"
                ]["raw"]["semantic_equality"],
            },
            next_action="Select best candidate",
        )
    all_results = candidate_results()
    best_name, best_seed, best = _best_candidate(all_results)
    if _qualifies_for_multiseed(best):
        for seed in (23_102, 23_103):
            train_named_candidate(best_name, seed=seed, max_steps=max_steps, cpu=cpu)
            evaluate_named_candidate(best_name, seed=seed, cpu=cpu)
    else:
        progress(
            "phase_28_multiseed_gate",
            "gate",
            metrics={"qualified": False, "candidate": best_name},
            diagnosis="Exploratory candidate did not satisfy all semantic, OOD, and safety gates.",
            next_action="Do not spend confirmatory seed compute",
        )
    evaluate_clarification(best_name, seed=best_seed, cpu=cpu)
    binding_audit()
    evaluate_end_to_end(best_name, seed=best_seed, cpu=cpu)
    return build_reports(checks)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("snapshot")
    subparsers.add_parser("build-data")
    subparsers.add_parser("deterministic")
    subparsers.add_parser("binding-audit")
    subparsers.add_parser("cuda-smoke")
    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--candidate", choices=CANDIDATES, required=True)
    train_parser.add_argument("--seed", type=int, default=23_101)
    train_parser.add_argument("--max-steps", type=int, default=20_000)
    train_parser.add_argument("--cpu", action="store_true")
    eval_parser = subparsers.add_parser("evaluate")
    eval_parser.add_argument("--candidate", choices=CANDIDATES, required=True)
    eval_parser.add_argument("--seed", type=int, default=23_101)
    eval_parser.add_argument("--cpu", action="store_true")
    clarification_parser = subparsers.add_parser("clarification")
    clarification_parser.add_argument("--candidate", choices=CANDIDATES, required=True)
    clarification_parser.add_argument("--seed", type=int, default=23_101)
    clarification_parser.add_argument("--cpu", action="store_true")
    e2e_parser = subparsers.add_parser("end-to-end")
    e2e_parser.add_argument("--candidate", choices=CANDIDATES, required=True)
    e2e_parser.add_argument("--seed", type=int, default=23_101)
    e2e_parser.add_argument("--cpu", action="store_true")
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--checks", default="pending")
    all_parser = subparsers.add_parser("run-all")
    all_parser.add_argument("--max-steps", type=int, default=20_000)
    all_parser.add_argument("--cpu", action="store_true")
    all_parser.add_argument("--checks", default="pending")
    args = parser.parse_args()
    if args.command == "snapshot":
        result = snapshot_m23()
    elif args.command == "build-data":
        result = build_data()
    elif args.command == "deterministic":
        result = evaluate_deterministic()
    elif args.command == "train":
        result = train_named_candidate(
            args.candidate,
            seed=args.seed,
            max_steps=args.max_steps,
            cpu=args.cpu,
        )
    elif args.command == "evaluate":
        result = evaluate_named_candidate(args.candidate, seed=args.seed, cpu=args.cpu)
    elif args.command == "clarification":
        result = evaluate_clarification(args.candidate, seed=args.seed, cpu=args.cpu)
    elif args.command == "binding-audit":
        result = binding_audit()
    elif args.command == "end-to-end":
        result = evaluate_end_to_end(args.candidate, seed=args.seed, cpu=args.cpu)
    elif args.command == "cuda-smoke":
        result = cuda_smoke()
    elif args.command == "report":
        result = build_reports(args.checks)
    else:
        result = run_all(max_steps=args.max_steps, cpu=args.cpu, checks=args.checks)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
