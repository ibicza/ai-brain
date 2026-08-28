"""Exact immutable catalog anchoring for educational runtime closures."""

from __future__ import annotations

from dataclasses import asdict, replace

from ai_brain.stage2.education.models import (
    EducationalCatalogEntryV2,
    EducationalCompilationReceipt,
    EducationalDerivationGraph,
    ExerciseInstance,
    ExerciseSpec,
    SemanticExerciseKey,
)
from ai_brain.stage2.facts.canonical import content_hash


def canonical_base_identity(instance: ExerciseInstance) -> dict[str, object]:
    """Return the authority-bearing fields shared by all presentation variants."""
    row = asdict(instance)
    for key in (
        "instance_id",
        "deterministic_seed",
        "language",
        "question_text",
        "difficulty_metadata",
        "generated_at",
        "instance_hash",
        "catalog_entry_hash",
    ):
        row.pop(key)
    return row


def catalog_entry_anchor_hash(
    semantic: SemanticExerciseKey,
    spec: ExerciseSpec,
    instance: ExerciseInstance,
    graph: EducationalDerivationGraph,
    receipt: EducationalCompilationReceipt,
) -> str:
    return content_hash(
        {
            "semantic_key_hash": semantic.semantic_key_hash,
            "exercise_spec_hash": spec.spec_hash,
            "canonical_base_identity_hash": content_hash(
                canonical_base_identity(instance)
            ),
            "graph_hash": graph.graph_hash,
            "compilation_receipt_hash": receipt.receipt_hash,
            "source_result_hash": graph.source_result_hash,
            "answer_semantics_hash": semantic.answer_semantics_hash,
        }
    )


def bind_instance_to_catalog(
    semantic: SemanticExerciseKey,
    spec: ExerciseSpec,
    instance: ExerciseInstance,
    graph: EducationalDerivationGraph,
    receipt: EducationalCompilationReceipt,
) -> ExerciseInstance:
    anchor = catalog_entry_anchor_hash(semantic, spec, instance, graph, receipt)
    provisional = replace(instance, catalog_entry_hash=anchor, instance_hash="")
    body = asdict(provisional)
    body.pop("instance_hash")
    return replace(provisional, instance_hash=content_hash(body))


def verify_catalog_entry_anchor(entry: EducationalCatalogEntryV2) -> None:
    expected = catalog_entry_anchor_hash(
        entry.semantic_key,
        entry.exercise_spec,
        entry.internal_instance,
        entry.graph,
        entry.compilation_receipt,
    )
    if entry.entry_hash != expected:
        raise ValueError("educational catalog entry anchor mismatch")
    if entry.internal_instance.catalog_entry_hash != expected:
        raise ValueError("catalog instance lacks its exact entry anchor")


def verify_instance_catalog_anchor(
    instance: ExerciseInstance, entry: EducationalCatalogEntryV2
) -> None:
    verify_catalog_entry_anchor(entry)
    if instance.catalog_entry_hash != entry.entry_hash:
        raise ValueError("exercise is anchored to another catalog entry")
    if canonical_base_identity(instance) != canonical_base_identity(
        entry.internal_instance
    ):
        raise ValueError("exercise variant changes catalog authority fields")
