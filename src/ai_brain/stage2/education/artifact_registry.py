"""Closed reconstruction and semantic-validation registry for v2 artifacts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from typing import Any

from ai_brain.stage2.education.exercises import verify_exercise_spec
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.models import (
    GradingResult,
    HintArtifact,
    HintPlan,
    StudentAnswer,
)
from ai_brain.stage2.education.serialization import (
    compilation_receipt_from_dict,
    event_from_dict,
    explanation_from_dict,
    explanation_plan_from_dict,
    grading_from_dict,
    graph_from_dict,
    hint_from_dict,
    hint_plan_from_dict,
    instance_from_dict,
    presented_from_dict,
    session_from_dict,
    spec_from_dict,
    student_answer_from_dict,
)
from ai_brain.stage2.education.sessions import verify_event_hash, verify_session_hash
from ai_brain.stage2.facts.canonical import content_hash

Deserializer = Callable[[dict[str, Any]], Any]

ARTIFACT_KINDS: dict[str, tuple[Deserializer, str]] = {
    "exercise_spec": (spec_from_dict, "spec_hash"),
    "exercise_instance_internal": (instance_from_dict, "instance_hash"),
    "presented_exercise": (presented_from_dict, "presentation_hash"),
    "source_result": (lambda row: row, "result_hash"),
    "compilation_receipt": (compilation_receipt_from_dict, "receipt_hash"),
    "derivation_graph": (graph_from_dict, "graph_hash"),
    "explanation_plan": (explanation_plan_from_dict, "plan_hash"),
    "explanation": (explanation_from_dict, "explanation_hash"),
    "student_answer": (student_answer_from_dict, "answer_hash"),
    "grading_result": (grading_from_dict, "result_hash"),
    "hint_plan": (hint_plan_from_dict, "plan_hash"),
    "hint": (hint_from_dict, "hint_hash"),
    "session": (session_from_dict, "session_hash"),
    "event": (event_from_dict, "event_hash"),
}


def reconstruct_and_validate(kind: str, artifact_hash: str, value: Any) -> Any:
    if kind not in ARTIFACT_KINDS:
        raise ValueError("unknown educational artifact kind")
    row = asdict(value) if is_dataclass(value) else value
    if not isinstance(row, dict):
        raise TypeError("educational artifact payload is not an object")
    deserializer, hash_field = ARTIFACT_KINDS[kind]
    typed = deserializer(row)
    if kind == "source_result":
        _verify_source_result_key(artifact_hash, typed)
        return typed
    internal_hash = _internal_hash(typed, hash_field)
    if internal_hash != artifact_hash:
        raise ValueError("educational artifact key/internal hash mismatch")
    _semantic_validate(kind, typed)
    return typed


def _internal_hash(value: Any, hash_field: str) -> str:
    if isinstance(value, dict):
        digest = value.get(hash_field) or value.get("answer_hash")
        body = dict(value)
    else:
        digest = getattr(value, hash_field)
        body = asdict(value)
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("educational artifact lacks its internal hash")
    body.pop(hash_field, None)
    if (
        hash_field == "result_hash"
        and isinstance(value, dict)
        and "result_hash" not in value
    ):
        body.pop("answer_hash", None)
    if content_hash(body) != digest:
        raise ValueError("educational artifact internal hash mismatch")
    return digest


def _semantic_validate(kind: str, value: Any) -> None:
    if kind == "exercise_spec":
        verify_exercise_spec(value)
    elif kind == "derivation_graph":
        verify_derivation_graph(value)
    elif kind == "student_answer":
        _verify_generic(value, "answer_hash")
        if not isinstance(value, StudentAnswer):
            raise TypeError("wrong student-answer artifact type")
    elif kind == "grading_result":
        _verify_generic(value, "result_hash")
        if not isinstance(value, GradingResult):
            raise TypeError("wrong grading-result artifact type")
    elif kind == "hint_plan":
        _verify_generic(value, "plan_hash")
        if not isinstance(value, HintPlan) or not value.node_order:
            raise ValueError("invalid hint plan")
    elif kind == "hint":
        _verify_generic(value, "hint_hash")
        if not isinstance(value, HintArtifact) or not value.text:
            raise ValueError("invalid hint artifact")
    elif kind == "session":
        verify_session_hash(value)
    elif kind == "event":
        verify_event_hash(value)
    elif kind not in {"source_result", "compilation_receipt"}:
        _, hash_field = ARTIFACT_KINDS[kind]
        _verify_generic(value, hash_field)


def _verify_generic(value: Any, hash_field: str) -> None:
    body = asdict(value)
    digest = body.pop(hash_field)
    if content_hash(body) != digest:
        raise ValueError("educational artifact hash mismatch")


def _verify_source_result_key(artifact_hash: str, value: dict[str, Any]) -> None:
    if "result_hash" in value:
        digest = value["result_hash"]
        body = {key: item for key, item in value.items() if key != "result_hash"}
    elif "answer_hash" in value:
        digest = value["answer_hash"]
        body = {key: item for key, item in value.items() if key != "answer_hash"}
    elif {"given_result_hash", "answer_result_hash"} <= set(value):
        body = {
            "given_result_hash": value["given_result_hash"],
            "answer_result_hash": value["answer_result_hash"],
        }
        digest = content_hash(body)
    else:
        raise ValueError("unknown educational source-result schema")
    if digest != artifact_hash or content_hash(body) != digest:
        raise ValueError("source-result key/internal hash mismatch")
