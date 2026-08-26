"""Canonical RequestEnvelope construction and validation."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from ai_brain.stage2.facts.canonical import content_hash, utc_now
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
    semantic = {
        "source_kind": kind,
        "original_input": original_input.strip(),
        "language": language,
        "structured_payload": normalized_payload,
        "requested_valid_at": requested_valid_at,
        "requested_known_at": requested_known_at,
        "requested_equivalence_scope": requested_equivalence_scope,
    }
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
    return RequestEnvelope(**payload, request_hash=content_hash(payload))


def validate_request(request: RequestEnvelope) -> None:
    payload = asdict(request)
    digest = payload.pop("request_hash")
    if content_hash(payload) != digest:
        raise ValueError("request envelope hash mismatch")
    if content_hash(request.original_input) != request.original_input_hash:
        raise ValueError("request original input hash mismatch")
    if request.schema_version != UNIFIED_ROUTER_SCHEMA_VERSION:
        raise ValueError("incompatible unified-router request schema")
