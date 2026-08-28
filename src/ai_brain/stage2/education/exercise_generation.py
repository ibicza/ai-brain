"""Runtime instantiation of precompiled, semantically distinct exercises."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from ai_brain.stage2.domains.chemistry.education.misconception_catalog import (
    chemistry_counterfactuals,
)
from ai_brain.stage2.education.answers import convert_exact
from ai_brain.stage2.education.exercises import verify_exercise_spec
from ai_brain.stage2.education.models import (
    EducationalCompilationReceipt,
    EducationalDerivationGraph,
    ExerciseFamily,
    ExerciseInstance,
    ExerciseSpec,
    ExerciseSplitAxis,
    PresentedExercise,
    SemanticExerciseKey,
)
from ai_brain.stage2.education.version import (
    EXERCISE_GENERATOR_VERSION,
    EXERCISE_SCHEMA_VERSION,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.trusted_decimal import render_bounded_decimal


def generate_exercise(
    catalog,
    family: ExerciseFamily,
    *,
    seed: int,
    language: str,
    difficulty: int | None = None,
) -> tuple[ExerciseSpec, ExerciseInstance, EducationalDerivationGraph]:
    """Select only from a verified v2 catalog; this function never runs a tool."""
    if not hasattr(catalog, "select"):
        raise ValueError("REBUILD_REQUIRED_FROM_EDUCATIONAL_V2")
    entry = catalog.select(family, seed=seed, difficulty=difficulty)
    instance = instantiate_variant(
        entry.internal_instance,
        entry.exercise_spec,
        entry.graph,
        seed=seed,
        language=language,
    )
    return entry.exercise_spec, instance, entry.graph


def make_internal_instance(
    spec: ExerciseSpec,
    graph: EducationalDerivationGraph,
    receipt: EducationalCompilationReceipt,
    *,
    seed: int,
    language: str,
    question_text: str,
    structured_givens: dict[str, Any],
    expected_answer: dict[str, Any],
    split_axis: ExerciseSplitAxis,
    split_manifest_hash: str,
) -> tuple[SemanticExerciseKey, ExerciseInstance]:
    verify_exercise_spec(spec)
    semantic = make_semantic_key(spec.family, structured_givens, expected_answer, graph)
    body = {
        "instance_id": "",
        "exercise_spec_hash": spec.spec_hash,
        "deterministic_seed": seed,
        "language": language,
        "question_text": question_text,
        "structured_givens": structured_givens,
        "hidden_answer_graph_hash": graph.graph_hash,
        "hidden_expected_answer": expected_answer,
        "accepted_equivalent_forms": _equivalent_forms(expected_answer),
        "provenance_dependencies": tuple(
            sorted(
                {
                    graph.source_result_hash,
                    graph.fact_memory_snapshot_hash,
                    graph.knowledge_snapshot_hash,
                    graph.source_chain_hash,
                    receipt.receipt_hash,
                    *graph.claim_ids,
                    *graph.evidence_hashes,
                    *graph.source_hashes,
                }
            )
        ),
        "difficulty_metadata": _difficulty(graph, question_text),
        "split_axis": split_axis,
        "counterfactuals": chemistry_counterfactuals(graph),
        "generated_at": _deterministic_time(seed),
        "schema_version": EXERCISE_SCHEMA_VERSION,
        "semantic_key_hash": semantic.semantic_key_hash,
        "compilation_receipt_hash": receipt.receipt_hash,
        "split_manifest_hash": split_manifest_hash,
    }
    identity = {**body, "instance_id": None}
    body["instance_id"] = f"education.exercise.{content_hash(identity)[:24]}"
    instance = ExerciseInstance(**body, instance_hash=content_hash(body))
    verify_exercise_instance(instance, spec, graph)
    return semantic, instance


def make_semantic_key(
    family: ExerciseFamily,
    givens: dict[str, Any],
    expected: dict[str, Any],
    graph: EducationalDerivationGraph,
) -> SemanticExerciseKey:
    numeric = tuple(
        sorted(
            (key, str(value))
            for key, value in givens.items()
            if key in {"value", "mass", "amount"}
        )
    )
    body = {
        "exercise_family": family,
        "subject": str(
            givens.get("formula", givens.get("subject", givens.get("symbol", "")))
        ),
        "predicate": givens.get("predicate"),
        "numeric_givens": numeric,
        "source_unit": givens.get("source_unit"),
        "target_unit": givens.get("target_unit"),
        "entity_basis": givens.get("basis"),
        "requested_precision": givens.get("significant_digits"),
        "answer_semantics_hash": content_hash(expected),
        "answer_graph_hash": graph.graph_hash,
    }
    return SemanticExerciseKey(**body, semantic_key_hash=content_hash(body))


def instantiate_variant(
    instance: ExerciseInstance,
    spec: ExerciseSpec,
    graph: EducationalDerivationGraph,
    *,
    seed: int,
    language: str,
) -> ExerciseInstance:
    verify_exercise_instance(instance, spec, graph)
    if language not in {"ru", "en"}:
        raise ValueError("exercise language must be ru or en")
    variant = (seed // 2_000) % 3
    question = render_question(
        spec.family, instance.structured_givens, language=language, variant=variant
    )
    provisional = replace(
        instance,
        instance_id="",
        deterministic_seed=seed,
        language=language,
        question_text=question,
        difficulty_metadata=_difficulty(graph, question),
        generated_at=_deterministic_time(seed),
        instance_hash="",
    )
    identity = asdict(provisional)
    identity["instance_id"] = None
    identity.pop("instance_hash")
    instance_id = f"education.exercise.{content_hash(identity)[:24]}"
    body = asdict(replace(provisional, instance_id=instance_id))
    body.pop("instance_hash")
    result = replace(
        provisional, instance_id=instance_id, instance_hash=content_hash(body)
    )
    verify_exercise_instance(result, spec, graph)
    return result


def derive_exercise_variant(
    instance: ExerciseInstance,
    spec: ExerciseSpec,
    graph: EducationalDerivationGraph,
    *,
    seed: int,
) -> ExerciseInstance:
    """Compatibility wrapper that changes a genuine presentation template."""
    return instantiate_variant(
        instance, spec, graph, seed=seed, language=instance.language
    )


def present_exercise(
    instance: ExerciseInstance, spec: ExerciseSpec, *, session_id: str
) -> PresentedExercise:
    body = {
        "session_id": session_id,
        "exercise_id": instance.instance_id,
        "language": instance.language,
        "question_text": instance.question_text,
        "structured_public_givens": dict(instance.structured_givens),
        "difficulty_metadata": dict(instance.difficulty_metadata),
        "learning_objectives": tuple(spec.learning_objectives),
        "accepted_answer_format": spec.accepted_answer_type.value,
        "schema_version": EXERCISE_SCHEMA_VERSION,
    }
    return PresentedExercise(**body, presentation_hash=content_hash(body))


def verify_presented_exercise(presented: PresentedExercise) -> None:
    body = asdict(presented)
    digest = body.pop("presentation_hash")
    if (
        content_hash(body) != digest
        or presented.schema_version != EXERCISE_SCHEMA_VERSION
    ):
        raise ValueError("invalid presented exercise")
    serialized = str(asdict(presented)).casefold()
    forbidden = ("graph_hash", "counterfactual", "split_axis", "receipt_hash")
    if any(item in serialized for item in forbidden):
        raise ValueError("presented exercise leaks a private field")


def verify_exercise_instance(
    instance: ExerciseInstance,
    spec: ExerciseSpec,
    graph: EducationalDerivationGraph,
) -> None:
    verify_exercise_spec(spec)
    body = asdict(instance)
    digest = body.pop("instance_hash")
    if content_hash(body) != digest:
        raise ValueError("exercise instance hash mismatch")
    if (
        instance.exercise_spec_hash != spec.spec_hash
        or instance.hidden_answer_graph_hash != graph.graph_hash
        or instance.semantic_key_hash
        != make_semantic_key(
            spec.family,
            instance.structured_givens,
            instance.hidden_expected_answer,
            graph,
        ).semantic_key_hash
    ):
        raise ValueError("exercise dependencies do not match")
    if instance.schema_version != EXERCISE_SCHEMA_VERSION:
        raise ValueError("incompatible exercise instance schema")
    if not instance.provenance_dependencies or not instance.compilation_receipt_hash:
        raise ValueError("exercise lacks provenance/compilation dependencies")
    for counterfactual in instance.counterfactuals:
        counterfactual_body = asdict(counterfactual)
        counterfactual_digest = counterfactual_body.pop("counterfactual_hash")
        if content_hash(counterfactual_body) != counterfactual_digest:
            raise ValueError("exercise counterfactual hash mismatch")
    # Split manifests are catalog-level dependencies and deliberately separate.
    if len(instance.split_manifest_hash) != 64:
        raise ValueError("exercise lacks a valid split manifest")
    forbidden = (instance.hidden_answer_graph_hash, instance.split_axis.value)
    if any(value in instance.question_text for value in forbidden):
        raise ValueError("exercise question leaks hidden metadata")


def render_question(
    family: ExerciseFamily,
    givens: dict[str, Any],
    *,
    language: str,
    variant: int = 0,
) -> str:
    formula = str(givens.get("formula", ""))
    prefix = (
        ("Задача", "Упражнение", "Проверка")[variant]
        if language == "ru"
        else (
            "Problem",
            "Exercise",
            "Practice",
        )[variant]
    )
    if family == ExerciseFamily.FORMULA_COMPOSITION:
        body = (
            f"Для формальной химической формулы {formula} укажите число атомов каждого элемента."
            if language == "ru"
            else f"Given the formal chemical formula {formula}, give each element's atom count."
        )
    elif family in {
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        ExerciseFamily.MOLAR_MASS_GROUPED,
    }:
        unit = givens["target_unit"]
        body = (
            f"Вычислите молярную массу формулы {formula} в {unit}."
            if language == "ru"
            else f"Calculate the molar mass of formula {formula} in {unit}."
        )
    elif family == ExerciseFamily.MASS_AMOUNT:
        body = (
            f"Для формулы {formula} преобразуйте {givens['value']} {givens['source_unit']} в {givens['target_unit']}."
            if language == "ru"
            else f"For formula {formula}, convert {givens['value']} {givens['source_unit']} to {givens['target_unit']}."
        )
    elif family == ExerciseFamily.AMOUNT_ENTITIES:
        body = (
            f"Для формулы {formula} преобразуйте {givens['value']} {givens['source_unit']} в число частиц ({givens['basis']})."
            if language == "ru"
            else f"For formula {formula}, convert {givens['value']} {givens['source_unit']} to entities ({givens['basis']})."
        )
    else:
        body = str(
            givens["question_body_ru" if language == "ru" else "question_body_en"]
        )
    return f"{prefix}: {body}"


def _difficulty(graph, question):
    formula_nodes = [node for node in graph.nodes if node.kind.value == "FORMULA_PARSE"]
    formula = str(formula_nodes[0].exact_output) if formula_nodes else ""
    return {
        "distinct_elements": len(formula_nodes[0].metadata.get("composition", {}))
        if formula_nodes
        else 0,
        "parentheses_depth": 1 if "(" in formula else 0,
        "arithmetic_steps": sum(node.operation is not None for node in graph.nodes),
        "requires_unit_conversion": any(
            node.kind.value == "UNIT_NORMALIZATION" for node in graph.nodes
        ),
        "question_length": len(question),
        "generator_version": EXERCISE_GENERATOR_VERSION,
    }


def _equivalent_forms(expected):
    unit = expected.get("unit")
    if unit in {"g", "mol"}:
        target = "kg" if unit == "g" else "mmol"
        return (
            {
                "value": render_bounded_decimal(
                    convert_exact(expected["value"], unit, target)
                ),
                "unit": target,
            },
        )
    return ()


def _deterministic_time(seed: int) -> str:
    value = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=seed % 31_536_000)
    return value.isoformat().replace("+00:00", "Z")
