from __future__ import annotations

import re
from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityDescriptor,
    CapabilityStatus,
    ProviderType,
)

_ID = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")


def descriptor_hash(value: CapabilityDescriptor) -> str:
    body = asdict(value)
    body.pop("descriptor_hash")
    return content_hash(body)


def validate_descriptor(value: CapabilityDescriptor) -> None:
    if not _ID.fullmatch(value.capability_id) or not value.version:
        raise ValueError("invalid capability identity")
    if not value.canonical_name_ru or not value.canonical_name_en:
        raise ValueError("capability requires canonical RU/EN names")
    for digest in (
        value.input_schema_hash,
        value.output_schema_hash,
        value.provider_implementation_hash,
        value.resource_policy_hash,
    ):
        if not _HEX.fullmatch(digest):
            raise ValueError("capability hashes must be exact SHA-256")
    if not value.provider_id or not value.allowed_execution_contexts:
        raise ValueError("capability provider and contexts are required")
    if (
        value.authority_class is AuthorityClass.ASSISTIVE_ONLY
        and value.capability_kind.value
        in {"GRADING", "PROCEDURE_EXECUTION", "TEST_EXECUTION"}
    ):
        raise ValueError("assistive capability cannot grade or execute")
    if (
        value.provider_type in {ProviderType.TOOL, ProviderType.SKILL}
        and not value.provider_id
    ):
        raise ValueError("existing execution authority must be explicit")
    if value.descriptor_hash != descriptor_hash(value):
        raise ValueError("capability descriptor hash mismatch")
    if len(set(value.required_capabilities)) != len(value.required_capabilities):
        raise ValueError("duplicate capability dependency")
    if value.capability_id in value.required_capabilities:
        raise ValueError("self capability dependency")
    if value.status not in CapabilityStatus:
        raise ValueError("invalid capability status")
