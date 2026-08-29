"""Data-only educational flow shared by every installed domain pack."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

from ai_brain.stage2.education.persistence import EducationalSessionStore
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.generic_ledger import GenericPersistentLedger
from ai_brain.stage3.acquisition.evaluation import verify_pack_evaluation
from ai_brain.stage3.capabilities.models import CapabilityRequirement, ResolutionStatus
from ai_brain.stage3.capabilities.resolution import resolve_capability
from ai_brain.stage3.capabilities.typed_scalar_equation_solver import (
    TypedQuantity,
    solve_typed_scalar_equation,
)
from ai_brain.stage3.domains.runtime import GenericDomainRuntime
from ai_brain.stage3.knowledge_ir.records import (
    ClaimSchemaContent,
    DefinitionContent,
    InterpretationContent,
    KnowledgeKind,
    RelationContent,
    RuleContent,
    TemporalRelationContent,
    UnitDefinitionContent,
)


@dataclass(frozen=True)
class GenericPresentedExercise:
    exercise_id: str
    domain_id: str
    family_id: str
    question: str
    concept_ids: tuple[str, ...]
    presentation_hash: str
    record_id: str = ""
    record_hash: str = ""
    source_binding_hashes: tuple[str, ...] = ()
    capability_receipt_hashes: tuple[str, ...] = ()
    pack_hash: str = ""


@dataclass(frozen=True)
class GenericGrade:
    exercise_id: str
    correct: bool
    grading_hash: str


class GenericEducationalDomainProvider:
    """Runs bounded catalog/answer/grade/explain/replay flows from pack data."""

    def __init__(self, runtime: GenericDomainRuntime, state_root: Path) -> None:
        self._runtime = runtime
        self._store = EducationalSessionStore.open_or_initialize(state_root)
        self._ledger = GenericPersistentLedger(
            self._store, "generic_educational_records"
        )

    @classmethod
    def from_installed(
        cls,
        registry,
        domain_id: str,
        pack_version: str | None = None,
        *,
        state_root: Path | None = None,
    ):
        pack = registry.load_installed_pack(domain_id, pack_version)
        root = state_root or (
            Path(tempfile.gettempdir())
            / "ai-brain-generic-runtime"
            / str(os.getpid())
            / pack.manifest.pack_content_hash
            / "education"
        )
        return cls(
            GenericDomainRuntime(pack, installed_registry=registry), root.resolve()
        )

    def domain_runtime(self):
        return self._runtime

    def strict_answer_parser(self, raw, answer_type="TEXT"):
        if isinstance(raw, bool) or not isinstance(raw, (str, int, Decimal)):
            raise TypeError("generic answer has an unsupported type")
        text = str(raw).strip()
        if not text or len(text.encode("utf-8")) > 4096:
            raise ValueError("generic answer is empty or oversized")
        if answer_type == "DECIMAL":
            try:
                value = Decimal(text)
            except InvalidOperation as error:
                raise ValueError("generic answer is not an exact decimal") from error
            if not value.is_finite():
                raise ValueError("generic answer is not finite")
            return format(value.normalize(), "f")
        if answer_type == "RATIONAL":
            try:
                value = Fraction(text)
            except (ValueError, ZeroDivisionError) as error:
                raise ValueError("generic answer is not an exact rational") from error
            return (
                str(value.numerator)
                if value.denominator == 1
                else f"{value.numerator}/{value.denominator}"
            )
        return " ".join(text.casefold().split())

    def fact_resolver(self, knowledge_id: str):
        return self._runtime.resolve_fact_schema(knowledge_id)

    def catalog_provider(self):
        return self._runtime.exercise_families()

    def graph_compiler_provider(self):
        return self._runtime.concept_graph()

    def explanation_provider(self):
        return self.explain

    def currentness_verifier(self):
        return self._runtime.verify_currentness()

    def controlled_language_provider(self):
        return self.converse

    def public_domain_metadata(self):
        return self._runtime.public_domain_summary()

    def present(
        self,
        family_id: str | None = None,
        *,
        seed: int = 0,
        language: str = "en",
        operation_id: str | None = None,
    ) -> GenericPresentedExercise:
        families = self._runtime.exercise_families()
        if not families:
            raise ValueError("installed pack has no exercise families")
        family = next(
            (item for item in families if item.family_id == family_id),
            families[seed % len(families)],
        )
        pack = self._runtime._pack
        rule = next(
            (
                item
                for item in pack.knowledge_records
                if item.kind is KnowledgeKind.EQUATION_RULE
            ),
            None,
        )
        if rule is not None:
            question, expected, answer_type = _equation_question(rule)
            authority_record = rule
        elif pack.concept_graph.edges:
            edge = pack.concept_graph.edges[seed % len(pack.concept_graph.edges)]
            question = f"Is {edge.source_concept_id} {edge.kind.value} {edge.target_concept_id}?"
            expected, answer_type = "yes", "TEXT"
            authority_record = next(
                (
                    item
                    for item in pack.knowledge_records
                    if item.knowledge_id
                    in {edge.source_concept_id, edge.target_concept_id}
                ),
                pack.knowledge_records[0],
            )
        else:
            concept = family.concept_ids[seed % len(family.concept_ids)]
            question = f"Identify the reviewed concept: {concept}"
            expected, answer_type = self.strict_answer_parser(concept), "TEXT"
            authority_record = next(
                item for item in pack.knowledge_records if item.knowledge_id == concept
            )
        source_bindings = tuple(
            item
            for item in pack.source_bindings
            if item.binding_id in authority_record.provenance_refs
        )
        installed = self._runtime._installed_registry.show(
            self._runtime.domain_id(), pack.manifest.pack_version
        )
        body = {
            "exercise_id": "",
            "domain_id": self._runtime.domain_id(),
            "family_id": family.family_id,
            "question": question,
            "concept_ids": family.concept_ids,
        }
        body["exercise_id"] = (
            f"generic.exercise.{content_hash((body, seed, language))[:24]}"
        )
        presented = GenericPresentedExercise(
            **body,
            presentation_hash=content_hash(body),
            record_id=authority_record.knowledge_id,
            record_hash=authority_record.content_hash,
            source_binding_hashes=tuple(item.binding_hash for item in source_bindings),
            capability_receipt_hashes=installed.capability_resolution_receipt_hashes,
            pack_hash=pack.manifest.pack_content_hash,
        )
        operation = operation_id or f"direct.{presented.presentation_hash[:32]}"
        self._ledger.put(
            presented.exercise_id,
            operation,
            "PRESENTATION",
            {
                "presented": presented,
                "expected": expected,
                "answer_type": answer_type,
                "evaluation_result_hash": installed.evaluation_result_hash,
            },
        )
        return presented

    def grade(
        self, exercise_id: str, raw_answer, *, operation_id: str | None = None
    ) -> GenericGrade:
        session = self._presentation(exercise_id)
        parsed = self.strict_answer_parser(raw_answer, session["answer_type"])
        correct = parsed == session["expected"]
        body = {
            "exercise_id": exercise_id,
            "correct": correct,
            "answer_hash": content_hash(parsed),
        }
        grade = GenericGrade(exercise_id, correct, content_hash(body))
        operation = operation_id or f"direct.{grade.grading_hash[:32]}"
        self._ledger.put(
            f"{exercise_id}.grade.{grade.grading_hash[:24]}",
            operation,
            "ANSWER_GRADED",
            grade,
        )
        return grade

    def explain(
        self, exercise_id: str, *, operation_id: str | None = None
    ) -> dict[str, object]:
        session = self._presentation(exercise_id)
        presented = session["presented"]
        explanation = {
            "exercise_id": exercise_id,
            "source_backed": True,
            "steps": (
                "read the installed typed record",
                "apply only its explicit relation or equation",
                "compare the exact answer",
            ),
            "pack_hash": self._runtime.pack_hash(),
            "record_id": presented["record_id"],
            "record_hash": presented["record_hash"],
            "source_binding_hashes": tuple(presented["source_binding_hashes"]),
            "capability_receipt_hashes": tuple(presented["capability_receipt_hashes"]),
            "evaluation_result_hash": session["evaluation_result_hash"],
        }
        digest = content_hash(explanation)
        operation = operation_id or f"direct.{digest[:32]}"
        self._ledger.put(
            f"{exercise_id}.explanation.{digest[:24]}",
            operation,
            "SOLUTION_REVEALED",
            explanation,
        )
        return {**explanation, "explanation_hash": digest}

    def hint(
        self, exercise_id: str, *, operation_id: str | None = None
    ) -> dict[str, object]:
        self._presentation(exercise_id)
        value = {
            "exercise_id": exercise_id,
            "level": 1,
            "text": "Use the exact installed relation or typed equation.",
        }
        digest = content_hash(value)
        operation = operation_id or f"direct.{digest[:32]}"
        self._ledger.put(
            f"{exercise_id}.hint.{digest[:24]}", operation, "HINT_USED", value
        )
        return {**value, "hint_hash": digest}

    def replay(self, exercise_id: str) -> dict[str, object]:
        records = tuple(
            item
            for item in self._ledger.records()
            if item[0] == exercise_id or item[0].startswith(f"{exercise_id}.")
        )
        return {
            "status": "REPLAYED",
            "exercise_id": exercise_id,
            "event_count": len(records),
            "event_chain_hash": content_hash(tuple(item[3] for item in records)),
        }

    def progress(self) -> dict[str, int]:
        events = self._ledger.records()
        return {
            "presented": sum(item[1] == "PRESENTATION" for item in events),
            "attempts": sum(item[1] == "ANSWER_GRADED" for item in events),
            "hints": sum(item[1] == "HINT_USED" for item in events),
            "solutions": sum(item[1] == "SOLUTION_REVEALED" for item in events),
        }

    def converse(
        self,
        text: str,
        *,
        exercise_id: str | None = None,
        operation_id: str | None = None,
    ):
        command = " ".join(text.casefold().split())
        if command.startswith("query:"):
            request = json.loads(
                text.split(":", 1)[1], object_pairs_hook=_strict_json_object
            )
            result = self.query(request)
        elif command in {"exercise", "give me an exercise", "дай задачу"}:
            result = self.present(operation_id=operation_id)
        elif command in {"hint", "give me a hint", "дай подсказку"} and exercise_id:
            result = self.hint(exercise_id, operation_id=operation_id)
        elif command in {"solution", "show solution", "покажи решение"} and exercise_id:
            result = self.explain(exercise_id, operation_id=operation_id)
        elif command in {"progress", "show progress", "покажи прогресс"}:
            result = self.progress()
        elif command.startswith("answer:") and exercise_id:
            result = self.grade(
                exercise_id, text.split(":", 1)[1], operation_id=operation_id
            )
        else:
            result = {
                "status": "CLARIFICATION_REQUIRED",
                "message": "Use one bounded tutoring command.",
            }
        if operation_id:
            self._ledger.put(
                f"response.{operation_id}",
                operation_id,
                "COMMAND_RESPONSE",
                _result_payload(result),
            )
        return result

    def query(self, request: dict) -> dict[str, object]:
        """Execute one schema-bound query over the installed pack only."""

        if not isinstance(request, dict) or not isinstance(
            request.get("operation"), str
        ):
            raise TypeError("generic query requires an exact operation")
        operation = request["operation"]
        if operation in {"COMPILE", "RUN"}:
            return {
                "status": "NEEDS_NEW_CAPABILITY",
                "required_capability": "generic.code_execution.v1",
                "pack_hash": self._runtime.pack_hash(),
                "capability_receipt_hashes": (),
            }
        capability_id = _query_capability(operation)
        receipt_hashes = self._resolve_query_capability(capability_id)
        if operation == "EQUATION_SOLVE":
            answer = self._query_equation(request)
        elif operation in {"TAXONOMY", "PART_WHOLE"}:
            answer = self._query_taxonomy(request, operation)
        elif operation in {"CHRONOLOGY", "DATE", "PRECEDES"}:
            answer = self._query_temporal(request)
        elif operation in {
            "SIGNATURE",
            "OVERLOADS",
            "PARAMETERS",
            "RETURN_TYPE",
            "GENERICS",
            "EXCEPTIONS",
            "DEPRECATION",
            "SINCE",
            "WORDING",
        }:
            answer = self._query_api(request)
        else:
            answer = self._query_records(request)
        return {
            **answer,
            "pack_hash": self._runtime.pack_hash(),
            "capability_id": capability_id,
            "capability_receipt_hashes": receipt_hashes,
        }

    def _resolve_query_capability(self, capability_id):
        registry = self._runtime._installed_registry
        required = {
            item.capability_id
            for item in self._runtime._pack.manifest.required_capabilities
        }
        if registry is None or capability_id not in required:
            raise ValueError(
                "NEEDS_NEW_CAPABILITY: pack did not declare query authority"
            )
        descriptor = registry.capability_registry.descriptor(capability_id)
        resolution = resolve_capability(
            registry.capability_registry,
            CapabilityRequirement(capability_id, "^1.0.0", "USER_RUNTIME"),
            requesting_domain_id=self._runtime.domain_id(),
            requesting_pack_hash=self._runtime.pack_hash(),
            provider_registry=registry.provider_registry,
            required_input_schema_hash=descriptor.input_schema_hash,
            required_output_schema_hash=descriptor.output_schema_hash,
        )
        if (
            resolution.status is not ResolutionStatus.RESOLVED
            or resolution.receipt is None
        ):
            raise ValueError("NEEDS_NEW_CAPABILITY: query capability is not current")
        return tuple(item.receipt_hash for item in resolution.closure_receipts)

    def _query_equation(self, request):
        record = next(
            (
                item
                for item in self._runtime._pack.knowledge_records
                if item.knowledge_id == request.get("rule_id")
                and isinstance(item.content, RuleContent)
            ),
            None,
        )
        if record is None:
            return {"status": "INSUFFICIENT_EVIDENCE", "exact_value": None}
        units = {
            item.content.unit.unit_id: item.content.unit
            for item in self._runtime._pack.knowledge_records
            if isinstance(item.content, UnitDefinitionContent)
        }
        for binding in record.content.variables:
            quantity = binding.value_type.quantity_type
            if quantity and quantity.canonical_unit:
                units[quantity.canonical_unit.unit_id] = quantity.canonical_unit
        known = {}
        try:
            for variable_id, value in request.get("givens", {}).items():
                known[variable_id] = TypedQuantity(
                    value["value"], units[value["unit_id"]]
                )
            output_unit = (
                units[request["output_unit_id"]]
                if request.get("output_unit_id")
                else None
            )
            solved = solve_typed_scalar_equation(
                record.content,
                known,
                request.get("unknown", ""),
                output_unit=output_unit,
                satisfied_conditions=tuple(request.get("conditions", ())),
            )
        except (KeyError, ValueError):
            return {"status": "NEEDS_NEW_CAPABILITY", "exact_value": None}
        return {
            "status": "SOLVED_EXACT",
            "exact_value": solved.solution.exact_value,
            "output_unit_id": solved.output_unit_id,
            "conversion_receipt_hashes": tuple(
                item.receipt_hash for item in solved.conversion_receipts
            ),
            "record_id": record.knowledge_id,
            "source_binding_hashes": self._source_hashes((record,)),
        }

    def _query_taxonomy(self, request, operation):
        predicate = "is_a" if operation == "TAXONOMY" else "part_of"
        matches = tuple(
            item
            for item in self._runtime._pack.knowledge_records
            if isinstance(item.content, RelationContent)
            and item.content.subject_id == request.get("subject_id")
            and item.content.predicate_id == predicate
        )
        return {
            "status": "ANSWERED" if matches else "INSUFFICIENT_EVIDENCE",
            "record_ids": tuple(item.knowledge_id for item in matches),
            "target_ids": tuple(item.content.object_id for item in matches),
            "source_binding_hashes": self._source_hashes(matches),
        }

    def _query_temporal(self, request):
        requested = set(request.get("record_ids", ()))
        matches = tuple(
            item
            for item in self._runtime._pack.knowledge_records
            if isinstance(item.content, TemporalRelationContent)
            and (not requested or item.knowledge_id in requested)
        )
        ordered = tuple(
            item.knowledge_id
            for item in sorted(
                matches,
                key=lambda value: (
                    value.content.start or "",
                    value.content.end or "",
                    value.knowledge_id,
                ),
            )
        )
        return {
            "status": "ANSWERED" if matches else "INSUFFICIENT_EVIDENCE",
            "ordered_record_ids": ordered,
            "records": tuple(asdict(item) for item in matches),
            "source_binding_hashes": self._source_hashes(matches),
        }

    def _query_api(self, request):
        if request.get("version") != self._runtime._pack.manifest.pack_version:
            return {"status": "VERSION_MISMATCH", "record_ids": (), "claims": ()}
        matches = tuple(
            item
            for item in self._runtime._pack.knowledge_records
            if isinstance(item.content, ClaimSchemaContent)
            and item.content.receiver_type == request.get("receiver_type")
            and item.content.predicate_id == request.get("symbol")
        )
        return {
            "status": "ANSWERED" if matches else "INSUFFICIENT_EVIDENCE",
            "record_ids": tuple(item.knowledge_id for item in matches),
            "claims": tuple(asdict(item.content) for item in matches),
            "source_binding_hashes": self._source_hashes(matches),
        }

    def _query_records(self, request):
        operation = request["operation"]
        matches = []
        for item in self._runtime._pack.knowledge_records:
            content = item.content
            if operation == "RECORD_BY_ID" and item.knowledge_id == request.get(
                "record_id"
            ):
                matches.append(item)
            elif operation == "DEFINITION" and isinstance(content, DefinitionContent):
                if request.get("term") in {content.term_id, content.definition_en}:
                    matches.append(item)
            elif (
                operation == "INTERPRETATIONS"
                and isinstance(content, InterpretationContent)
            ) or (
                operation == "SOURCE_ATTRIBUTION"
                and (
                    not request.get("record_id")
                    or item.knowledge_id == request["record_id"]
                )
            ):
                matches.append(item)
        values = tuple(matches)
        return {
            "status": "ANSWERED" if values else "INSUFFICIENT_EVIDENCE",
            "records": tuple(asdict(item) for item in values),
            "source_binding_hashes": self._source_hashes(values),
        }

    def _source_hashes(self, records):
        identities = {identity for item in records for identity in item.provenance_refs}
        return tuple(
            item.binding_hash
            for item in self._runtime._pack.source_bindings
            if item.binding_id in identities
        )

    def inspect_operation(self, operation_id: str) -> tuple[str, ...]:
        return self._ledger.inspect_operation(operation_id)

    def result_for_operation(self, operation_id: str):
        _, _, payload, _ = self._ledger.get(f"response.{operation_id}")
        return _restore_result(payload)

    def verify_persistence(self):
        return {
            **self._ledger.verify(),
            "currentness": self._runtime.verify_currentness(),
            "pack_evaluation": verify_pack_evaluation(self._runtime._pack),
        }

    def _presentation(self, exercise_id: str):
        _, kind, payload, _ = self._ledger.get(exercise_id)
        if kind != "PRESENTATION":
            raise ValueError("generic exercise presentation type mismatch")
        return payload


def _equation_question(record):
    content = record.content
    assert isinstance(content, RuleContent)
    variables = content.variables
    unknown = variables[0].variable_id
    known = {}
    displayed = []
    for binding in variables[1:]:
        quantity = binding.value_type.quantity_type
        if quantity is not None and quantity.canonical_unit is not None:
            known[binding.variable_id] = TypedQuantity("1", quantity.canonical_unit)
            displayed.append(
                f"{binding.variable_id}=1 {quantity.canonical_unit.unit_id}"
            )
        else:
            known[binding.variable_id] = "1"
            displayed.append(f"{binding.variable_id}=1")
    solved = solve_typed_scalar_equation(
        content,
        known,
        unknown,
        satisfied_conditions=content.applicability.preconditions,
        require_typed_quantities=True,
    )
    conditions = ", ".join(content.applicability.preconditions) or "none"
    givens = ", ".join(displayed) or "none"
    return (
        f"Solve the installed equation for {unknown}; givens: {givens}; conditions: {conditions}.",
        solved.solution.exact_value,
        "RATIONAL",
    )


def _result_payload(result):
    if isinstance(result, GenericPresentedExercise):
        return {"kind": "PRESENTATION", "value": result}
    if isinstance(result, GenericGrade):
        return {"kind": "GRADE", "value": result}
    return {"kind": "DICT", "value": result}


def _restore_result(payload):
    if payload["kind"] == "PRESENTATION":
        value = dict(payload["value"])
        for key in (
            "concept_ids",
            "source_binding_hashes",
            "capability_receipt_hashes",
        ):
            value[key] = tuple(value[key])
        return GenericPresentedExercise(**value)
    if payload["kind"] == "GRADE":
        return GenericGrade(**payload["value"])
    value = payload["value"]
    for key in ("steps", "source_binding_hashes", "capability_receipt_hashes"):
        if key in value:
            value[key] = tuple(value[key])
    return value


def _query_capability(operation: str) -> str:
    if operation == "EQUATION_SOLVE":
        return "generic.typed_scalar_equation_solver.v1"
    if operation in {"TAXONOMY", "PART_WHOLE"}:
        return "generic.taxonomy_query.v1"
    if operation in {"CHRONOLOGY", "DATE", "PRECEDES"}:
        return "generic.temporal_query.v1"
    if operation in {
        "SIGNATURE",
        "OVERLOADS",
        "PARAMETERS",
        "RETURN_TYPE",
        "GENERICS",
        "EXCEPTIONS",
        "DEPRECATION",
        "SINCE",
        "WORDING",
    }:
        return "generic.api_contract_query.v1"
    if operation in {
        "RECORD_BY_ID",
        "DEFINITION",
        "SOURCE_ATTRIBUTION",
        "INTERPRETATIONS",
        "EXCEPTIONS",
    }:
        return "generic.record_query.v1"
    raise ValueError("NEEDS_NEW_CAPABILITY: unsupported generic query operation")


def _strict_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate generic query field")
        value[key] = item
    return value
