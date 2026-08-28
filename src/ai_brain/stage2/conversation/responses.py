"""Public response construction and hidden-data leak checks."""

from __future__ import annotations

import re
from dataclasses import asdict

from ai_brain.stage2.conversation.models import PublicConversationResponse
from ai_brain.stage2.facts.canonical import canonical_json, content_hash

FORBIDDEN_KEYS = frozenset(
    {
        "graph",
        "hidden_answer",
        "compilation_receipt",
        "source_result",
        "event_hash",
        "pending_hash",
        "grading_result_hash",
        "catalog_entry_hash",
    }
)
INTERNAL_TEXT = re.compile(
    r"\b(?:education\.(?:node|session|event)|[0-9a-f]{40,64})\b", re.IGNORECASE
)


def response_hash(response: PublicConversationResponse) -> str:
    verify_public_response(response)
    return content_hash(asdict(response))


def verify_public_response(response: PublicConversationResponse) -> None:
    payload = asdict(response)
    if (
        sum(
            payload[name] is not None
            for name in ("exercise", "submission", "hint", "solution")
        )
        > 1
    ):
        raise ValueError(
            "public conversation response contains multiple authority payloads"
        )
    serialized = canonical_json(payload)
    if any(f'"{key}":' in serialized for key in FORBIDDEN_KEYS):
        raise ValueError(
            "public conversation response leaks an internal authority field"
        )
    for value in (response.text, response.clarification_prompt or ""):
        if INTERNAL_TEXT.search(value):
            raise ValueError("public conversation text leaks an internal identifier")
