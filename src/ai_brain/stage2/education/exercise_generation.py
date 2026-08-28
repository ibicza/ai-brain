"""Deterministic chemistry exercise generation through exact trusted tools."""

from __future__ import annotations

import random
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import localcontext

from ai_brain.stage2.domains.chemistry.education.exercise_catalog import (
    GROUPED_FORMULAS,
    INTERVAL_ELEMENTS,
    SIMPLE_FORMULAS,
    chemistry_exercise_specs,
)
from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.domains.chemistry.education.misconception_catalog import (
    chemistry_counterfactuals,
)
from ai_brain.stage2.education.answers import convert_exact
from ai_brain.stage2.education.exercises import verify_exercise_spec
from ai_brain.stage2.education.models import (
    EducationalDerivationGraph,
    ExerciseFamily,
    ExerciseInstance,
    ExerciseSpec,
    ExerciseSplitAxis,
    StudentAnswerKind,
)
from ai_brain.stage2.education.version import (
    EXERCISE_GENERATOR_VERSION,
    EXERCISE_SCHEMA_VERSION,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.trusted_decimal import (
    parse_bounded_decimal,
    render_bounded_decimal,
)


def generate_exercise(
    adapter: ChemistryEducationAdapter,
    family: ExerciseFamily,
    *,
    seed: int,
    language: str,
    difficulty: int | None = None,
) -> tuple[ExerciseSpec, ExerciseInstance, EducationalDerivationGraph]:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("exercise seed must be a nonnegative integer")
    if language not in {"ru", "en"}:
        raise ValueError("exercise language must be ru or en")
    specs = tuple(
        spec
        for spec in chemistry_exercise_specs(adapter.service.manifest["domain_version"])
        if spec.family == family
        and (difficulty is None or spec.difficulty_tier == difficulty)
    )
    if not specs:
        raise ValueError("no exercise spec matches the requested family/difficulty")
    rng = random.Random(seed)
    spec = specs[seed % len(specs)]
    verify_exercise_spec(spec)
    question, givens, expected, graph = _materialize(adapter, spec, rng, language, seed)
    split_axes = tuple(ExerciseSplitAxis)
    body = {
        "instance_id": "",
        "exercise_spec_hash": spec.spec_hash,
        "deterministic_seed": seed,
        "language": language,
        "question_text": question,
        "structured_givens": givens,
        "hidden_answer_graph_hash": graph.graph_hash,
        "hidden_expected_answer": expected,
        "accepted_equivalent_forms": _equivalent_forms(expected),
        "provenance_dependencies": tuple(
            sorted(
                {
                    graph.source_result_hash,
                    graph.fact_memory_snapshot_hash,
                    graph.knowledge_snapshot_hash,
                    graph.source_chain_hash,
                    *graph.claim_ids,
                    *graph.evidence_hashes,
                    *graph.source_hashes,
                }
            )
        ),
        "difficulty_metadata": _difficulty(graph, question),
        "split_axis": split_axes[seed % len(split_axes)],
        "counterfactuals": chemistry_counterfactuals(graph),
        "generated_at": _deterministic_time(seed),
        "schema_version": EXERCISE_SCHEMA_VERSION,
    }
    identity_body = {**body, "instance_id": None}
    body["instance_id"] = f"education.exercise.{content_hash(identity_body)[:24]}"
    instance = ExerciseInstance(**body, instance_hash=content_hash(body))
    verify_exercise_instance(instance, spec, graph)
    return spec, instance, graph


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
    ):
        raise ValueError("exercise dependencies do not match")
    if instance.schema_version != EXERCISE_SCHEMA_VERSION:
        raise ValueError("incompatible exercise instance schema")
    forbidden = (
        instance.hidden_answer_graph_hash,
        instance.split_axis.value,
        "expected misconception",
    )
    if any(value in instance.question_text for value in forbidden):
        raise ValueError("exercise question leaks hidden metadata")
    if not instance.provenance_dependencies:
        raise ValueError("exercise lacks provenance dependencies")


def derive_exercise_variant(
    instance: ExerciseInstance,
    spec: ExerciseSpec,
    graph: EducationalDerivationGraph,
    *,
    seed: int,
) -> ExerciseInstance:
    """Create a new deterministic envelope over an already verified exact key."""
    verify_exercise_instance(instance, spec, graph)
    axes = tuple(ExerciseSplitAxis)
    provisional = replace(
        instance,
        instance_id="",
        deterministic_seed=seed,
        split_axis=axes[seed % len(axes)],
        generated_at=_deterministic_time(seed),
        instance_hash="",
    )
    identity = asdict(provisional)
    identity["instance_id"] = None
    instance_id = f"education.exercise.{content_hash(identity)[:24]}"
    body = asdict(replace(provisional, instance_id=instance_id))
    body.pop("instance_hash")
    variant = replace(
        provisional,
        instance_id=instance_id,
        instance_hash=content_hash(body),
    )
    verify_exercise_instance(variant, spec, graph)
    return variant


def _materialize(adapter, spec, rng, language, seed):
    family = spec.family
    created_at = _deterministic_time(seed)
    if family == ExerciseFamily.FACT_RETRIEVAL:
        symbols = (
            INTERVAL_ELEMENTS
            if spec.accepted_answer_type == StudentAnswerKind.ATOMIC_WEIGHT_INTERVAL
            else tuple(adapter.service.manifest["supported_elements"])
        )
        symbol = symbols[rng.randrange(len(symbols))]
        predicates = tuple(spec.parameter_constraints["predicates"])
        predicate = predicates[seed % len(predicates)]
        given_predicate = (
            "element_name_ru"
            if predicate == "element_symbol" and language == "ru"
            else "element_name_en"
            if predicate == "element_symbol"
            else "element_symbol"
        )
        _, _, graph = adapter.paired_fact_graph(
            symbol,
            given_predicate,
            predicate,
            language=language,
            created_at=created_at,
        )
        root = next(
            node for node in graph.nodes if node.node_id == graph.root_result_node_id
        )
        if spec.accepted_answer_type == StudentAnswerKind.NUMERIC_WITH_UNIT:
            expected = {"value": str(root.exact_output), "unit": "u"}
        elif spec.accepted_answer_type == StudentAnswerKind.ATOMIC_WEIGHT_INTERVAL:
            expected = dict(root.exact_output)
        else:
            expected = {"text": str(root.exact_output)}
        given = next(
            node
            for node in graph.nodes
            if node.metadata.get("role") == "question_given"
        )
        question = _fact_question(language, given.exact_output, predicate)
        return (
            question,
            {"given_value": given.exact_output, "given_predicate": given_predicate},
            expected,
            graph,
        )
    if family in {
        ExerciseFamily.FORMULA_COMPOSITION,
        ExerciseFamily.MOLAR_MASS_SIMPLE,
    }:
        formulas = SIMPLE_FORMULAS
    elif family == ExerciseFamily.MOLAR_MASS_GROUPED:
        formulas = GROUPED_FORMULAS
    else:
        formulas = SIMPLE_FORMULAS + GROUPED_FORMULAS
    formula = formulas[rng.randrange(len(formulas))]
    if family == ExerciseFamily.FORMULA_COMPOSITION:
        result, graph = adapter.tool_graph(
            "chemistry_formula_composition",
            {"formula": formula},
            created_at=created_at,
        )
        expected = {
            "element_counts": dict(sorted(result["result"]["element_counts"].items()))
        }
        question = (
            f"Укажите число атомов каждого элемента в формуле {formula}."
            if language == "ru"
            else f"Give the atom count of each element in {formula}."
        )
        return question, {"formula": formula}, expected, graph
    if family in {
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        ExerciseFamily.MOLAR_MASS_GROUPED,
    }:
        unit = ("g/mol", "kg/mol")[seed % 2]
        result, graph = adapter.tool_graph(
            "chemistry_molar_mass",
            {
                "formula": formula,
                "mode": "conventional",
                "unit": unit,
                "significant_digits": 8,
            },
            created_at=created_at,
        )
        expected = _numeric_expected(result)
        question = (
            f"Вычислите молярную массу {formula} в {unit}."
            if language == "ru"
            else f"Calculate the molar mass of {formula} in {unit}."
        )
        return question, {"formula": formula, "target_unit": unit}, expected, graph
    if family == ExerciseFamily.MASS_AMOUNT:
        value = str(2 + rng.randrange(97))
        source_unit, target_unit = (
            ("g", "mol"),
            ("kg", "mmol"),
            ("mol", "g"),
            ("mmol", "kg"),
        )[seed % 4]
        result, graph = adapter.tool_graph(
            "chemistry_mass_amount",
            {
                "formula": formula,
                "value": value,
                "source_unit": source_unit,
                "target_unit": target_unit,
                "significant_digits": 8,
            },
            created_at=created_at,
        )
        expected = _numeric_expected(result)
        question = (
            f"Для {formula} преобразуйте {value} {source_unit} в {target_unit}."
            if language == "ru"
            else f"For {formula}, convert {value} {source_unit} to {target_unit}."
        )
        givens = {
            "formula": formula,
            "value": value,
            "source_unit": source_unit,
            "target_unit": target_unit,
        }
        return question, givens, expected, graph
    value = str(1 + rng.randrange(20))
    source_unit, target_unit = (("mol", "entities"), ("mmol", "entities"))[seed % 2]
    basis = ("FORMULA_ENTITIES", "TOTAL_ATOMS_IN_FORMULA")[seed % 2]
    result, graph = adapter.tool_graph(
        "chemistry_entity_amount",
        {
            "formula": formula,
            "value": value,
            "source_unit": source_unit,
            "target_unit": target_unit,
            "basis": basis,
            "target_element": None,
            "requested_display_label": None,
            "significant_digits": 8,
        },
        created_at=created_at,
    )
    expected = _numeric_expected(result)
    subject = (
        "всех атомов"
        if language == "ru" and basis == "TOTAL_ATOMS_IN_FORMULA"
        else "формульных единиц"
        if language == "ru"
        else "all atoms"
        if basis == "TOTAL_ATOMS_IN_FORMULA"
        else "formula entities"
    )
    question = (
        f"Сколько {subject} содержится в {value} {source_unit} {formula}?"
        if language == "ru"
        else f"How many {subject} are in {value} {source_unit} of {formula}?"
    )
    givens = {
        "formula": formula,
        "value": value,
        "source_unit": source_unit,
        "target_unit": target_unit,
        "basis": basis,
    }
    return question, givens, expected, graph


def _numeric_expected(result):
    value = result["result"]["exact_internal_value"]
    rendered = result["result"]["rendered_value"]
    with localcontext() as context:
        context.prec = 256
        tolerance = abs(parse_bounded_decimal(value) - parse_bounded_decimal(rendered))
    return {
        "value": value,
        "unit": result["result"]["unit"],
        "absolute_tolerance": render_bounded_decimal(tolerance),
    }


def _fact_question(language, given_value, predicate):
    if predicate == "element_symbol":
        return (
            f"Запишите символ элемента {given_value}."
            if language == "ru"
            else f"Give the symbol of {given_value}."
        )
    labels = {
        "ru": {
            "atomic_number": "атомный номер",
            "element_name_en": "английское название",
            "element_name_ru": "русское название",
            "conventional_atomic_weight": "условную атомную массу",
            "standard_atomic_weight": "интервал стандартной атомной массы",
        },
        "en": {
            "atomic_number": "atomic number",
            "element_name_en": "English name",
            "element_name_ru": "Russian name",
            "conventional_atomic_weight": "conventional atomic weight",
            "standard_atomic_weight": "standard atomic-weight interval",
        },
    }
    return (
        f"Укажите {labels['ru'][predicate]} элемента {given_value}."
        if language == "ru"
        else f"Give the {labels['en'][predicate]} of element {given_value}."
    )


def _difficulty(graph, question):
    formula_nodes = [node for node in graph.nodes if node.kind.value == "FORMULA_PARSE"]
    formula = str(formula_nodes[0].exact_output) if formula_nodes else ""
    return {
        "distinct_elements": (
            len(formula_nodes[0].metadata.get("composition", {}))
            if formula_nodes
            else 0
        ),
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
    if unit == "g":
        return (
            {
                "value": render_bounded_decimal(
                    convert_exact(expected["value"], "g", "kg")
                ),
                "unit": "kg",
            },
        )
    if unit == "mol":
        return (
            {
                "value": render_bounded_decimal(
                    convert_exact(expected["value"], "mol", "mmol")
                ),
                "unit": "mmol",
            },
        )
    return ()


def _deterministic_time(seed: int) -> str:
    value = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=seed % 31_536_000)
    return value.isoformat().replace("+00:00", "Z")
