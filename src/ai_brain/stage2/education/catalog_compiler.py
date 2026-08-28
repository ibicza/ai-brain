"""Administrative offline compiler for the educational catalog v2."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, localcontext
from pathlib import Path
from time import perf_counter
from typing import Any

from ai_brain.stage2.domains.chemistry.education.exercise_catalog import (
    ALL_EXERCISE_FORMULAS,
    GROUPED_FORMULAS,
    INTERVAL_ELEMENTS,
    SIMPLE_FORMULAS,
    SPLIT_BUCKETS,
    chemistry_exercise_specs,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.compiler import (
    COMPILER_IDENTITY,
    compile_answer_key,
    compile_fact_answer_key,
)
from ai_brain.stage2.education.exercise_generation import (
    make_internal_instance,
    make_semantic_key,
    render_question,
)
from ai_brain.stage2.education.models import (
    ActorIdentityType,
    EducationalCatalogEntryV2,
    EducationalCatalogManifestV2,
    ExerciseFamily,
    ExerciseSplitAxis,
    StudentAnswerKind,
)
from ai_brain.stage2.education.version import (
    EDUCATIONAL_SCHEMA_VERSION,
    EXERCISE_GENERATOR_VERSION,
)
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage2.trusted_decimal import (
    parse_bounded_decimal,
    render_bounded_decimal,
)


def compile_catalog_v2(
    service: ChemistryDomainService,
    output: Path,
    *,
    entry_count: int = 2_000,
    audit_path: Path | None = None,
) -> dict[str, Any]:
    if entry_count < 2_000:
        raise ValueError("M-29.1 catalog requires at least 2,000 semantic entries")
    started = perf_counter()
    records = _compile_records(service, entry_count, audit_path)
    semantic_keys = tuple(
        make_semantic_key(
            row["spec"].family, row["givens"], row["expected"], row["graph"]
        )
        for row in records
    )
    if len({item.semantic_key_hash for item in semantic_keys}) != entry_count:
        raise ValueError("catalog compiler produced duplicate semantic keys")
    split_manifests = _split_manifests(records, semantic_keys)
    split_by_axis = {
        ExerciseSplitAxis(item["axis"]): item["manifest_hash"]
        for item in split_manifests
    }
    entries = []
    for index, (row, semantic) in enumerate(zip(records, semantic_keys, strict=True)):
        axis = _primary_axis(row)
        _, instance = make_internal_instance(
            row["spec"],
            row["graph"],
            row["receipt"],
            seed=index,
            language="en",
            question_text=render_question(
                row["spec"].family, row["givens"], language="en", variant=0
            ),
            structured_givens=row["givens"],
            expected_answer=row["expected"],
            split_axis=axis,
            split_manifest_hash=split_by_axis[axis],
        )
        body = {
            "semantic_key": semantic,
            "exercise_spec": row["spec"],
            "internal_instance": instance,
            "graph": row["graph"],
            "compilation_receipt": row["receipt"],
        }
        entries.append(EducationalCatalogEntryV2(**body, entry_hash=content_hash(body)))
    manifest_body = {
        "chemistry_domain_manifest_hash": service.manifest["domain_manifest_hash"],
        "fact_memory_snapshot_hash": service.manifest["fact_memory_snapshot_hash"],
        "source_chain_hash": service.manifest["source_chain_hash"],
        "tool_manifest_hashes": tuple(service.registry.current_manifest_hashes()),
        "generator_version": EXERCISE_GENERATOR_VERSION,
        "entry_hashes": tuple(entry.entry_hash for entry in entries),
        "split_manifest_hashes": tuple(
            item["manifest_hash"] for item in split_manifests
        ),
        "schema_version": EDUCATIONAL_SCHEMA_VERSION,
    }
    manifest = EducationalCatalogManifestV2(
        **manifest_body, catalog_hash=content_hash(manifest_body)
    )
    payload = {
        "catalog_manifest": asdict(manifest),
        "entries": [asdict(entry) for entry in entries],
        "split_manifests": split_manifests,
    }
    resolved = output.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(payload) + "\n")
    return {
        "status": "COMPILED",
        "catalog_hash": manifest.catalog_hash,
        "entry_count": len(entries),
        "distinct_semantic_keys": len(semantic_keys),
        "distinct_graphs": len({entry.graph.graph_hash for entry in entries}),
        "compilation_receipt_count": len(entries),
        "receipt_bound_tool_execution_count": sum(
            entry.compilation_receipt.tool_id != "chemistry_fact_lookup"
            for entry in entries
        ),
        "elapsed_seconds": f"{perf_counter() - started:.6f}",
        "split_manifest_hashes": manifest.split_manifest_hashes,
    }


def _compile_records(service, count: int, audit_path: Path | None):
    specs = chemistry_exercise_specs(service.manifest["domain_version"])
    by_family = {family: [] for family in ExerciseFamily}
    for spec in specs:
        by_family[spec.family].append(spec)
    allocations = (
        (ExerciseFamily.FACT_RETRIEVAL, 100),
        (ExerciseFamily.FORMULA_COMPOSITION, 24),
        (ExerciseFamily.MOLAR_MASS_SIMPLE, 192),
        (ExerciseFamily.MOLAR_MASS_GROUPED, 192),
        (ExerciseFamily.MASS_AMOUNT, 900),
        (ExerciseFamily.AMOUNT_ENTITIES, count - 1_408),
    )
    records = []
    global_index = 0
    for family, family_count in allocations:
        for local_index in range(family_count):
            timestamp = _time(global_index)
            if family == ExerciseFamily.FACT_RETRIEVAL:
                record = _compile_fact(
                    service,
                    by_family[family],
                    local_index,
                    timestamp,
                    audit_path,
                )
            else:
                spec = by_family[family][0]
                arguments, givens = _tool_case(family, local_index)
                result, graph, receipt = compile_answer_key(
                    service,
                    _tool_id(family),
                    arguments,
                    actor_identity_type=ActorIdentityType.TRUSTED_PROCESS,
                    compiler_identity=COMPILER_IDENTITY,
                    exercise_spec_hash=spec.spec_hash,
                    created_at=timestamp,
                    audit_path=audit_path,
                )
                record = {
                    "spec": spec,
                    "graph": graph,
                    "receipt": receipt,
                    "givens": givens,
                    "expected": _expected(result),
                }
            records.append(record)
            global_index += 1
    return records


def _compile_fact(service, specs, index, timestamp, audit_path):
    regular_predicates = (
        "element_symbol",
        "atomic_number",
        "element_name_en",
        "element_name_ru",
        "conventional_atomic_weight",
    )
    if index < len(INTERVAL_ELEMENTS):
        predicate = "standard_atomic_weight"
        symbol = INTERVAL_ELEMENTS[index]
    else:
        regular_index = index - len(INTERVAL_ELEMENTS)
        predicate = regular_predicates[regular_index % len(regular_predicates)]
        symbols = tuple(service.manifest["supported_elements"])
        symbol = symbols[(regular_index // len(regular_predicates)) % len(symbols)]
    given_predicate = (
        "element_name_en" if predicate == "element_symbol" else "element_symbol"
    )
    spec = next(
        item for item in specs if predicate in item.parameter_constraints["predicates"]
    )
    given, answer, graph, receipt = compile_fact_answer_key(
        service,
        symbol,
        given_predicate,
        predicate,
        language="en",
        actor_identity_type=ActorIdentityType.TRUSTED_PROCESS,
        compiler_identity=COMPILER_IDENTITY,
        exercise_spec_hash=spec.spec_hash,
        created_at=timestamp,
        audit_path=audit_path,
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
    given_node = next(
        node for node in graph.nodes if node.metadata.get("role") == "question_given"
    )
    label = {
        "element_symbol": "Give the symbol of the stated element.",
        "atomic_number": "Give the atomic number of the stated element.",
        "element_name_en": "Give the English element name.",
        "element_name_ru": "Give the Russian element name.",
        "conventional_atomic_weight": "Give the conventional atomic weight in u.",
        "standard_atomic_weight": "Give the standard atomic-weight interval.",
    }[predicate]
    givens = {
        "subject": symbol,
        "predicate": predicate,
        "given_value": given_node.exact_output,
        "question_body_en": f"{label} Given: {given_node.exact_output}.",
        "question_body_ru": f"Укажите запрошенное свойство элемента. Дано: {given_node.exact_output}.",
    }
    return {
        "spec": spec,
        "graph": graph,
        "receipt": receipt,
        "givens": givens,
        "expected": expected,
        "given_result": given,
        "answer_result": answer,
    }


def _tool_case(family: ExerciseFamily, index: int):
    if family == ExerciseFamily.FORMULA_COMPOSITION:
        formula = ALL_EXERCISE_FORMULAS[index % len(ALL_EXERCISE_FORMULAS)]
        return {"formula": formula}, {"formula": formula}
    if family in {ExerciseFamily.MOLAR_MASS_SIMPLE, ExerciseFamily.MOLAR_MASS_GROUPED}:
        formulas = (
            SIMPLE_FORMULAS
            if family == ExerciseFamily.MOLAR_MASS_SIMPLE
            else GROUPED_FORMULAS
        )
        formula = formulas[index % len(formulas)]
        unit = ("g/mol", "kg/mol")[(index // len(formulas)) % 2]
        digits = 3 + (index // (len(formulas) * 2)) % 8
        arguments = {
            "formula": formula,
            "mode": "conventional",
            "unit": unit,
            "significant_digits": digits,
        }
        return arguments, {
            "formula": formula,
            "target_unit": unit,
            "significant_digits": digits,
        }
    formula = ALL_EXERCISE_FORMULAS[index % len(ALL_EXERCISE_FORMULAS)]
    value = render_bounded_decimal(Decimal(index + 10) / Decimal(10))
    digits = 4 + index % 7
    if family == ExerciseFamily.MASS_AMOUNT:
        source, target = (
            ("g", "mol"),
            ("kg", "mmol"),
            ("mol", "g"),
            ("mmol", "kg"),
        )[index % 4]
        arguments = {
            "formula": formula,
            "value": value,
            "source_unit": source,
            "target_unit": target,
            "significant_digits": digits,
        }
        return arguments, dict(arguments)
    source, target = (
        ("mol", "entities"),
        ("mmol", "entities"),
        ("entities", "mol"),
        ("entities", "mmol"),
    )[index % 4]
    if source == "entities":
        value = str(index + 1000)
    basis = (
        "FORMULA_ENTITIES",
        "TOTAL_ATOMS_IN_FORMULA",
        "ATOMS_OF_ELEMENT_IN_FORMULA",
    )[index % 3]
    target_element = (
        _symbols(formula)[0] if basis == "ATOMS_OF_ELEMENT_IN_FORMULA" else None
    )
    arguments = {
        "formula": formula,
        "value": value,
        "source_unit": source,
        "target_unit": target,
        "basis": basis,
        "target_element": target_element,
        "requested_display_label": None,
        "significant_digits": digits,
    }
    return arguments, dict(arguments)


def _tool_id(family: ExerciseFamily) -> str:
    return {
        ExerciseFamily.FORMULA_COMPOSITION: "chemistry_formula_composition",
        ExerciseFamily.MOLAR_MASS_SIMPLE: "chemistry_molar_mass",
        ExerciseFamily.MOLAR_MASS_GROUPED: "chemistry_molar_mass",
        ExerciseFamily.MASS_AMOUNT: "chemistry_mass_amount",
        ExerciseFamily.AMOUNT_ENTITIES: "chemistry_entity_amount",
    }[family]


def _expected(result):
    value = result["result"]
    if "element_counts" in value:
        return {"element_counts": dict(sorted(value["element_counts"].items()))}
    if "exact_internal_lower" in value:
        return {
            "lower": value["exact_internal_lower"],
            "upper": value["exact_internal_upper"],
            "unit": value["unit"],
        }
    exact = value["exact_internal_value"]
    rendered = value["rendered_value"]
    with localcontext() as context:
        context.prec = 256
        tolerance = abs(parse_bounded_decimal(exact) - parse_bounded_decimal(rendered))
    return {
        "value": exact,
        "unit": value["unit"],
        "absolute_tolerance": render_bounded_decimal(tolerance),
    }


def _primary_axis(row) -> ExerciseSplitAxis:
    givens = row["givens"]
    formula = givens.get("formula")
    if formula in SPLIT_BUCKETS["final"]:
        return ExerciseSplitAxis.FORMULA_STRUCTURE_HOLDOUT
    if givens.get("source_unit") in {"kg", "entities"}:
        return ExerciseSplitAxis.UNIT_DIRECTION_HOLDOUT
    if "value" in givens and Decimal(str(givens["value"])) >= 70:
        return ExerciseSplitAxis.NUMERIC_RANGE_HOLDOUT
    if formula and "(" in formula:
        return ExerciseSplitAxis.MULTI_STEP_COMPOSITION
    if row["spec"].family == ExerciseFamily.FACT_RETRIEVAL:
        return ExerciseSplitAxis.ELEMENT_COMBINATION_HOLDOUT
    return ExerciseSplitAxis.TEMPLATE_HOLDOUT


def _split_manifests(records, semantic_keys):
    implemented = tuple(ExerciseSplitAxis)
    manifests = []
    for axis in implemented:
        development = []
        final = []
        for row, semantic in zip(records, semantic_keys, strict=True):
            target = final if _is_final(axis, row) else development
            target.append(semantic.semantic_key_hash)
        body = {
            "axis": axis.value,
            "status": "TESTED",
            "development": tuple(development),
            "final_validation": tuple(final),
            "intersection_count": 0,
        }
        manifests.append({**body, "manifest_hash": content_hash(body)})
    return tuple(manifests)


def _is_final(axis: ExerciseSplitAxis, row) -> bool:
    givens = row["givens"]
    formula = givens.get("formula", "")
    if axis == ExerciseSplitAxis.FORMULA_STRUCTURE_HOLDOUT:
        return formula in SPLIT_BUCKETS["final"]
    if axis == ExerciseSplitAxis.ELEMENT_COMBINATION_HOLDOUT:
        return bool(formula) and set(_symbols(formula)) >= {"N", "O"}
    if axis == ExerciseSplitAxis.NUMERIC_RANGE_HOLDOUT:
        return "value" in givens and Decimal(str(givens["value"])) >= 70
    if axis == ExerciseSplitAxis.UNIT_DIRECTION_HOLDOUT:
        return (givens.get("source_unit"), givens.get("target_unit")) in {
            ("kg", "mmol"),
            ("entities", "mmol"),
        }
    if axis == ExerciseSplitAxis.TEMPLATE_HOLDOUT:
        return semantic_bucket(row) == 2
    if axis == ExerciseSplitAxis.RU_EN_CROSS_LANGUAGE:
        return semantic_bucket(row) % 2 == 1
    if axis == ExerciseSplitAxis.MULTI_STEP_COMPOSITION:
        return "(" in formula or row["spec"].family in {
            ExerciseFamily.MASS_AMOUNT,
            ExerciseFamily.AMOUNT_ENTITIES,
        }
    return row["spec"].family == ExerciseFamily.FACT_RETRIEVAL


def semantic_bucket(row) -> int:
    return (
        int(
            content_hash({"givens": row["givens"], "family": row["spec"].family})[:8],
            16,
        )
        % 3
    )


def _symbols(formula: str) -> tuple[str, ...]:
    import re

    return tuple(re.findall(r"[A-Z][a-z]?", formula))


def _time(index: int) -> str:
    return f"2026-01-{1 + (index // 86400):02d}T00:{(index // 60) % 60:02d}:{index % 60:02d}Z"
