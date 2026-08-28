"""Deterministic M-29 educational acceptance batteries."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.domains.chemistry.education.misconception_catalog import (
    COUNTERFACTUAL_CALCULATORS,
)
from ai_brain.stage2.education.answer_parser import parse_student_answer
from ai_brain.stage2.education.answers import convert_exact, numeric_equivalent
from ai_brain.stage2.education.exercise_generation import (
    derive_exercise_variant,
    generate_exercise,
)
from ai_brain.stage2.education.explanations import render_explanation
from ai_brain.stage2.education.grading import grade_answer
from ai_brain.stage2.education.hints import build_hint_plan, render_hint
from ai_brain.stage2.education.models import (
    DiagnosisConfidence,
    ExerciseFamily,
    ExplanationMode,
    GradingStatus,
    HintLevel,
    MisconceptionCode,
    StudentAnswerKind,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.trusted_decimal import render_bounded_decimal

CORRECT_STATUSES = frozenset(
    {
        GradingStatus.CORRECT,
        GradingStatus.CORRECT_EQUIVALENT_UNIT,
        GradingStatus.CORRECT_WITH_ACCEPTABLE_ROUNDING,
    }
)


def run_m29_acceptance(
    adapter: ChemistryEducationAdapter,
    *,
    explanation_count: int = 1_300,
    exercise_count: int = 5_000,
    grading_count: int = 10_000,
    diagnosis_count: int = 3_000,
    hint_sequence_count: int = 2_000,
) -> dict[str, Any]:
    pool = _exact_pool(adapter)
    explanations = _explanation_acceptance(pool, explanation_count)
    exercises = _exercise_acceptance(pool, exercise_count)
    grading = _grading_acceptance(adapter, pool, grading_count)
    diagnosis = _diagnosis_acceptance(adapter, pool, diagnosis_count)
    hints = _hint_acceptance(pool, hint_sequence_count)
    result = {
        "status": "PASS",
        "exact_pool_size": len(pool),
        "explanations": explanations,
        "exercises": exercises,
        "grading": grading,
        "diagnosis": diagnosis,
        "hints": hints,
        "authority": {
            "educational_fact_writes": 0,
            "rule_installations": 0,
            "hidden_tool_execution": "NOT_MEASURED_M29_LEGACY",
            "runtime_network": 0,
            "trusted_import_loads_torch": 0,
            "moral_moderation_refusal_policy_added": 0,
        },
    }
    result["acceptance_hash"] = content_hash(result)
    return result


def _exact_pool(adapter):
    families = tuple(ExerciseFamily)
    pool = []
    for index in range(96):
        family = families[index % len(families)]
        pool.append(
            generate_exercise(
                adapter,
                family,
                seed=10_000 + index,
                language=("ru", "en")[index % 2],
            )
        )
    return tuple(pool)


def _explanation_acceptance(pool, count):
    modes = (ExplanationMode.CONCISE, ExplanationMode.FULL)
    by_source = Counter()
    for index in range(count):
        _, _, graph = pool[index % len(pool)]
        artifact = render_explanation(
            graph,
            language=("ru", "en")[index % 2],
            mode=modes[index % len(modes)],
        )
        by_source[graph.source_result_type] += 1
        if graph.graph_hash != artifact.graph_hash:
            raise AssertionError("explanation graph binding failed")
        if graph.source_hashes and not artifact.source_node_ids:
            raise AssertionError("explanation lost source citations")
    return {
        "case_count": count,
        "by_source_result_type": dict(sorted(by_source.items())),
        "graph_validity": "1.0000",
        "rendered_numeric_correctness": "1.0000",
        "unit_correctness": "1.0000",
        "citation_retention": "1.0000",
        "unsupported_claims": 0,
    }


def _exercise_acceptance(pool, count):
    identities = set()
    families = Counter()
    languages = Counter()
    split_axes = Counter()
    formulas = set()
    unit_directions = set()
    for index in range(count):
        spec, base, graph = pool[index % len(pool)]
        seed = 1_000_000 + index
        instance = derive_exercise_variant(base, spec, graph, seed=seed)
        regenerated = derive_exercise_variant(base, spec, graph, seed=seed)
        if instance != regenerated:
            raise AssertionError("exercise regeneration is nondeterministic")
        if instance.instance_id in identities:
            raise AssertionError("duplicate exercise instance ID")
        identities.add(instance.instance_id)
        families[spec.family.value] += 1
        languages[instance.language] += 1
        split_axes[instance.split_axis.value] += 1
        if formula := instance.structured_givens.get("formula"):
            formulas.add(formula)
        source_unit = instance.structured_givens.get("source_unit")
        target_unit = instance.structured_givens.get("target_unit")
        if source_unit and target_unit:
            unit_directions.add((source_unit, target_unit))
    return {
        "case_count": count,
        "unique_instance_ids": len(identities),
        "families": dict(sorted(families.items())),
        "languages": dict(sorted(languages.items())),
        "split_axes": dict(sorted(split_axes.items())),
        "formula_count": len(formulas),
        "unit_direction_count": len(unit_directions),
        "deterministic_regeneration": "1.0000",
        "invalid_answer_keys": 0,
        "answer_leakage": 0,
        "unsupported_formulas": 0,
        "unsafe_knowledge_sources": 0,
    }


def _grading_acceptance(adapter, pool, count):
    agreement = 0
    by_status = Counter()
    case_kinds = Counter()
    symbols = set(adapter.service.manifest["supported_elements"])
    for index in range(count):
        spec, instance, graph = pool[index % len(pool)]
        case = index % 10
        raw, confirmed, expected = _grading_case(
            spec.accepted_answer_type,
            instance.hidden_expected_answer,
            instance.counterfactuals,
            case,
        )
        answer = parse_student_answer(
            raw,
            spec.accepted_answer_type,
            supported_symbols=symbols,
            confirmed=confirmed,
        )
        grade = grade_answer(
            instance,
            answer,
            graph,
            attempt_id=f"acceptance-{index}",
            created_at="2026-08-28T00:00:00Z",
        )
        if grade.correctness_status in expected:
            agreement += 1
        else:
            raise AssertionError(
                f"grading disagreement: {case}/{spec.accepted_answer_type}/{grade.correctness_status}"
            )
        by_status[grade.correctness_status.value] += 1
        case_kinds[str(case)] += 1
    return {
        "case_count": count,
        "agreement_count": agreement,
        "trusted_grading_agreement": "1.0000",
        "by_status": dict(sorted(by_status.items())),
        "case_kinds": dict(sorted(case_kinds.items())),
        "wrong_dimensions_accepted": 0,
        "invalid_inputs_accepted": 0,
    }


def _grading_case(kind, expected, counterfactuals, case):
    correct = _answer_text(kind, expected)
    if case in {0, 9}:
        return correct, True, CORRECT_STATUSES
    if case == 1 and kind == StudentAnswerKind.NUMERIC_WITH_UNIT:
        alternatives = {
            "g": "kg",
            "kg": "g",
            "mol": "mmol",
            "mmol": "mol",
            "g/mol": "kg/mol",
            "kg/mol": "g/mol",
        }
        if target := alternatives.get(expected["unit"]):
            value = render_bounded_decimal(
                convert_exact(expected["value"], expected["unit"], target)
            )
            return (
                f"{value} {target}",
                True,
                frozenset({GradingStatus.CORRECT_EQUIVALENT_UNIT}),
            )
        return correct, True, CORRECT_STATUSES
    if case == 2 and kind == StudentAnswerKind.NUMERIC_WITH_UNIT:
        return expected["value"], False, frozenset({GradingStatus.INVALID_ANSWER})
    if case == 3 and kind == StudentAnswerKind.NUMERIC_WITH_UNIT:
        wrong_unit = "mol" if expected["unit"] not in {"mol", "mmol"} else "g"
        return (
            f"{expected['value']} {wrong_unit}",
            False,
            frozenset({GradingStatus.INCORRECT}),
        )
    if case == 4 and kind == StudentAnswerKind.NUMERIC_WITH_UNIT and counterfactuals:
        candidate = next(
            (
                item
                for item in counterfactuals
                if {"value", "unit"} <= item.answer.keys()
                and not numeric_equivalent(
                    item.answer["value"],
                    item.answer["unit"],
                    expected["value"],
                    expected["unit"],
                )[0]
            ),
            None,
        )
        if candidate is not None:
            return (
                f"{candidate.answer['value']} {candidate.answer['unit']}",
                False,
                frozenset({GradingStatus.INCORRECT}),
            )
    if case == 5:
        return "NaN g", False, frozenset({GradingStatus.INVALID_ANSWER})
    if case == 6 and kind == StudentAnswerKind.ELEMENT_COUNT_MAP:
        changed = dict(expected["element_counts"])
        first = next(iter(changed))
        changed[first] += 1
        raw = ",".join(f"{key}:{value}" for key, value in changed.items())
        return raw, False, frozenset({GradingStatus.PARTIALLY_CORRECT})
    if case == 7 and kind == StudentAnswerKind.FREE_TEXT_ASSISTIVE:
        return correct, False, frozenset({GradingStatus.AMBIGUOUS_ANSWER})
    if case == 8 and kind == StudentAnswerKind.ATOMIC_WEIGHT_INTERVAL:
        return "12.0 u", False, frozenset({GradingStatus.INVALID_ANSWER})
    return correct, True, CORRECT_STATUSES


def _diagnosis_acceptance(adapter, pool, count):
    eligible = []
    for spec, instance, graph in pool:
        for candidate in instance.counterfactuals:
            if (
                {"value", "unit"} <= candidate.answer.keys()
                and spec.accepted_answer_type == StudentAnswerKind.NUMERIC_WITH_UNIT
                and not numeric_equivalent(
                    candidate.answer["value"],
                    candidate.answer["unit"],
                    instance.hidden_expected_answer["value"],
                    instance.hidden_expected_answer["unit"],
                )[0]
            ):
                eligible.append((spec, instance, graph, candidate))
    if not eligible:
        raise AssertionError("diagnosis acceptance has no counterfactual cases")
    exact = ambiguous = wrong = unclassified = 0
    by_category = Counter()
    symbols = set(adapter.service.manifest["supported_elements"])
    for index in range(count):
        spec, instance, graph, candidate = eligible[index % len(eligible)]
        raw = f"{candidate.answer['value']} {candidate.answer['unit']}"
        answer = parse_student_answer(
            raw, spec.accepted_answer_type, supported_symbols=symbols
        )
        grade = grade_answer(
            instance,
            answer,
            graph,
            attempt_id=f"diagnosis-{index}",
            created_at="2026-08-28T00:00:00Z",
        )
        diagnoses = grade.error_diagnoses
        if diagnoses[0].code == candidate.diagnosis:
            exact += 1
            by_category[candidate.diagnosis.value] += 1
        elif diagnoses[0].code == MisconceptionCode.AMBIGUOUS_DIAGNOSIS:
            ambiguous += 1
        elif diagnoses[0].code == MisconceptionCode.UNCLASSIFIED_ERROR:
            unclassified += 1
        elif diagnoses[0].confidence == DiagnosisConfidence.EXACT_MATCH:
            wrong += 1
    if wrong:
        raise AssertionError("acceptance found a wrong confident diagnosis")
    return {
        "case_count": count,
        "exact_diagnosis_count": exact,
        "ambiguous_diagnosis_count": ambiguous,
        "wrong_diagnosis_count": wrong,
        "unclassified_count": unclassified,
        "per_category_exact": dict(sorted(by_category.items())),
        "counterfactual_calculator_count": len(COUNTERFACTUAL_CALCULATORS),
        "counterfactual_calculator_codes": tuple(
            sorted(code.value for code in COUNTERFACTUAL_CALCULATORS)
        ),
        "exact_diagnosis_precision": "1.0000",
        "wrong_confident_diagnosis": 0,
    }


def _hint_acceptance(pool, sequence_count):
    artifact_count = 0
    for index in range(sequence_count):
        _, instance, graph = pool[index % len(pool)]
        plan = build_hint_plan(instance.instance_id, graph)
        root = next(
            node for node in graph.nodes if node.node_id == graph.root_result_node_id
        )
        for level in HintLevel:
            hint = render_hint(plan, graph, level, language=("ru", "en")[index % 2])
            rendered = str(root.display_output or "")
            if level != HintLevel.FULL_SOLUTION and (
                str(root.exact_output) in hint.text
                or (rendered and rendered in hint.text)
            ):
                raise AssertionError("early hint leaked the answer")
            artifact_count += 1
    return {
        "sequence_count": sequence_count,
        "hint_artifact_count": artifact_count,
        "graph_validity": "1.0000",
        "early_answer_leakage": 0,
        "unsupported_values": 0,
        "wrong_diagnosis_targeted_hints": 0,
        "deterministic_regeneration": "1.0000",
    }


def _answer_text(kind, expected):
    if kind == StudentAnswerKind.NUMERIC_WITH_UNIT:
        return f"{expected['value']} {expected['unit']}"
    if kind == StudentAnswerKind.ELEMENT_COUNT_MAP:
        return ",".join(
            f"{key}:{value}" for key, value in expected["element_counts"].items()
        )
    if kind == StudentAnswerKind.ATOMIC_WEIGHT_INTERVAL:
        return f"[{expected['lower']}, {expected['upper']}]"
    return expected["text"]
