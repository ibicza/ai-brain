"""Canonical RequestEnvelope construction and validation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from ai_brain.stage2.facts.canonical import content_hash, normalize_temporal, utc_now
from ai_brain.stage2.models import EquivalenceScope
from ai_brain.stage2.router.models import RequestEnvelope, RequestSourceKind
from ai_brain.stage2.router.version import UNIFIED_ROUTER_SCHEMA_VERSION


def create_request(
    source_kind: RequestSourceKind | str,
    *,
    original_input: str = "",
    language: str | None = None,
    structured_payload: dict[str, Any] | None = None,
    requested_valid_at: str | None = None,
    requested_known_at: str | None = None,
    requested_equivalence_scope: str | None = None,
    request_id_factory=None,
    clock=utc_now,
) -> RequestEnvelope:
    if not isinstance(original_input, str):
        raise TypeError("original_input must be a string")
    kind = RequestSourceKind(source_kind)
    if (
        kind
        in {
            RequestSourceKind.STRUCTURED_FACT,
            RequestSourceKind.STRUCTURED_SKILL,
            RequestSourceKind.STRUCTURED_TOOL,
        }
        and structured_payload is None
    ):
        raise ValueError("structured request requires structured_payload")
    if (
        kind
        in {
            RequestSourceKind.CONTROLLED_LANGUAGE,
            RequestSourceKind.ASSISTIVE_TEXT,
        }
        and not original_input.strip()
    ):
        raise ValueError("text request cannot be empty")
    if language is not None and language not in {"ru", "en"}:
        raise ValueError("language must be ru or en")
    normalized_payload = (
        json.loads(json.dumps(structured_payload, ensure_ascii=False, sort_keys=True))
        if structured_payload is not None
        else None
    )
    original_hash = content_hash(original_input)
    semantic = _semantic_payload(
        kind,
        original_input,
        language,
        normalized_payload,
        requested_valid_at,
        requested_known_at,
        requested_equivalence_scope,
    )
    payload = {
        "request_id": (request_id_factory or (lambda: f"request_{uuid4().hex}"))(),
        "source_kind": kind,
        "original_input": original_input,
        "original_input_hash": original_hash,
        "semantic_input_hash": content_hash(semantic),
        "language": language,
        "structured_payload": normalized_payload,
        "requested_valid_at": requested_valid_at,
        "requested_known_at": requested_known_at,
        "requested_equivalence_scope": requested_equivalence_scope,
        "created_at": clock(),
        "schema_version": UNIFIED_ROUTER_SCHEMA_VERSION,
    }
    request = RequestEnvelope(**payload, request_hash=content_hash(payload))
    validate_request(request)
    return request


def _semantic_payload(
    kind: RequestSourceKind,
    original_input: str,
    language: str | None,
    structured_payload: dict[str, Any] | None,
    requested_valid_at: str | None,
    requested_known_at: str | None,
    requested_equivalence_scope: str | None,
) -> dict[str, Any]:
    return {
        "source_kind": kind,
        "original_input": original_input.strip(),
        "language": language,
        "structured_payload": structured_payload,
        "requested_valid_at": requested_valid_at,
        "requested_known_at": requested_known_at,
        "requested_equivalence_scope": requested_equivalence_scope,
    }


def validate_request(request: RequestEnvelope) -> None:
    if type(request) is not RequestEnvelope:
        raise TypeError("request must be an exact RequestEnvelope")
    if not isinstance(request.source_kind, RequestSourceKind):
        raise TypeError("request source_kind must be typed")
    if not isinstance(request.original_input, str):
        raise TypeError("request original_input must be a string")
    if re.fullmatch(r"request_[0-9a-f]{32}", request.request_id) is None:
        raise ValueError("invalid request ID")
    for name in ("original_input_hash", "semantic_input_hash", "request_hash"):
        if re.fullmatch(r"[0-9a-f]{64}", getattr(request, name)) is None:
            raise ValueError(f"invalid {name}")
    payload = asdict(request)
    digest = payload.pop("request_hash")
    if content_hash(payload) != digest:
        raise ValueError("request envelope hash mismatch")
    if content_hash(request.original_input) != request.original_input_hash:
        raise ValueError("request original input hash mismatch")
    semantic = _semantic_payload(
        request.source_kind,
        request.original_input,
        request.language,
        request.structured_payload,
        request.requested_valid_at,
        request.requested_known_at,
        request.requested_equivalence_scope,
    )
    if content_hash(semantic) != request.semantic_input_hash:
        raise ValueError("request semantic input hash mismatch")
    if request.schema_version != UNIFIED_ROUTER_SCHEMA_VERSION:
        raise ValueError("incompatible unified-router request schema")
    structured = request.source_kind in {
        RequestSourceKind.STRUCTURED_FACT,
        RequestSourceKind.STRUCTURED_SKILL,
        RequestSourceKind.STRUCTURED_TOOL,
    }
    if structured != (request.structured_payload is not None):
        raise ValueError("request source kind and structured payload disagree")
    if structured and request.original_input != "":
        raise ValueError("structured requests cannot carry textual input")
    if request.structured_payload is not None and not isinstance(
        request.structured_payload, dict
    ):
        raise TypeError("structured payload must be a JSON object")
    if request.language is not None and request.language not in {"ru", "en"}:
        raise ValueError("request language is invalid")
    if request.source_kind in {
        RequestSourceKind.CONTROLLED_LANGUAGE,
        RequestSourceKind.ASSISTIVE_TEXT,
    } and (not request.original_input.strip() or request.language not in {"ru", "en"}):
        raise ValueError("text requests require non-empty text and language")
    for name in ("requested_valid_at", "requested_known_at", "created_at"):
        value = getattr(request, name)
        if value is not None:
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a temporal string")
            normalize_temporal(value)
    if request.requested_equivalence_scope is not None:
        EquivalenceScope(request.requested_equivalence_scope)
