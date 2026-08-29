"""Data-only educational flow shared by every installed domain pack."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.domains.runtime import GenericDomainRuntime
from ai_brain.stage3.knowledge_ir.records import KnowledgeKind, RuleContent


@dataclass(frozen=True)
class GenericPresentedExercise:
    exercise_id: str
    domain_id: str
    family_id: str
    question: str
    concept_ids: tuple[str, ...]
    presentation_hash: str


@dataclass(frozen=True)
class GenericGrade:
    exercise_id: str
    correct: bool
    grading_hash: str


class GenericEducationalDomainProvider:
    """Runs bounded catalog/answer/grade/explain/replay flows from pack data."""

    def __init__(self, runtime: GenericDomainRuntime) -> None:
        self._runtime = runtime
        self._sessions: dict[str, dict] = {}

    @classmethod
    def from_installed(cls, registry, domain_id: str, pack_version: str | None = None):
        pack = registry.load_installed_pack(domain_id, pack_version)
        return cls(GenericDomainRuntime(pack, installed_registry=registry))

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
        self, family_id: str | None = None, *, seed: int = 0, language: str = "en"
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
        elif pack.concept_graph.edges:
            edge = pack.concept_graph.edges[seed % len(pack.concept_graph.edges)]
            question = f"Is {edge.source_concept_id} {edge.kind.value} {edge.target_concept_id}?"
            expected, answer_type = "yes", "TEXT"
        else:
            concept = family.concept_ids[seed % len(family.concept_ids)]
            question = f"Identify the reviewed concept: {concept}"
            expected, answer_type = self.strict_answer_parser(concept), "TEXT"
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
            **body, presentation_hash=content_hash(body)
        )
        self._sessions[presented.exercise_id] = {
            "presented": presented,
            "expected": expected,
            "answer_type": answer_type,
            "events": (("PRESENTED", presented.presentation_hash),),
        }
        return presented

    def grade(self, exercise_id: str, raw_answer) -> GenericGrade:
        session = self._sessions[exercise_id]
        parsed = self.strict_answer_parser(raw_answer, session["answer_type"])
        correct = parsed == session["expected"]
        body = {
            "exercise_id": exercise_id,
            "correct": correct,
            "answer_hash": content_hash(parsed),
        }
        grade = GenericGrade(exercise_id, correct, content_hash(body))
        session["events"] = (*session["events"], ("ANSWER_GRADED", grade.grading_hash))
        return grade

    def explain(self, exercise_id: str) -> dict[str, object]:
        session = self._sessions[exercise_id]
        explanation = {
            "exercise_id": exercise_id,
            "source_backed": True,
            "steps": (
                "read the installed typed record",
                "apply only its explicit relation or equation",
                "compare the exact answer",
            ),
            "pack_hash": self._runtime.pack_hash(),
        }
        digest = content_hash(explanation)
        session["events"] = (*session["events"], ("SOLUTION_REVEALED", digest))
        return {**explanation, "explanation_hash": digest}

    def hint(self, exercise_id: str) -> dict[str, object]:
        session = self._sessions[exercise_id]
        value = {
            "exercise_id": exercise_id,
            "level": 1,
            "text": "Use the exact installed relation or typed equation.",
        }
        digest = content_hash(value)
        session["events"] = (*session["events"], ("HINT_USED", digest))
        return {**value, "hint_hash": digest}

    def replay(self, exercise_id: str) -> dict[str, object]:
        session = self._sessions[exercise_id]
        return {
            "status": "REPLAYED",
            "exercise_id": exercise_id,
            "event_count": len(session["events"]),
            "event_chain_hash": content_hash(session["events"]),
        }

    def progress(self) -> dict[str, int]:
        events = tuple(
            event for session in self._sessions.values() for event in session["events"]
        )
        return {
            "presented": sum(item[0] == "PRESENTED" for item in events),
            "attempts": sum(item[0] == "ANSWER_GRADED" for item in events),
            "hints": sum(item[0] == "HINT_USED" for item in events),
            "solutions": sum(item[0] == "SOLUTION_REVEALED" for item in events),
        }

    def converse(self, text: str, *, exercise_id: str | None = None):
        command = " ".join(text.casefold().split())
        if command in {"exercise", "give me an exercise", "дай задачу"}:
            return self.present()
        if command in {"hint", "give me a hint", "дай подсказку"} and exercise_id:
            return self.hint(exercise_id)
        if command in {"solution", "show solution", "покажи решение"} and exercise_id:
            return self.explain(exercise_id)
        if command in {"progress", "show progress", "покажи прогресс"}:
            return self.progress()
        if command.startswith("answer:") and exercise_id:
            return self.grade(exercise_id, text.split(":", 1)[1])
        return {
            "status": "CLARIFICATION_REQUIRED",
            "message": "Use one bounded tutoring command.",
        }


def _equation_question(record):
    content = record.content
    assert isinstance(content, RuleContent)
    variables = content.variables
    if len(variables) == 1:
        expected = "1"
        return (
            f"Solve the installed equation for {variables[0].variable_id}.",
            expected,
            "DECIMAL",
        )
    return "Apply the installed typed equation.", "review-required", "TEXT"
