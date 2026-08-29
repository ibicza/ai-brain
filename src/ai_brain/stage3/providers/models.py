from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_brain.stage3.capabilities.models import ProviderType


class ProviderStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


@dataclass(frozen=True)
class ProviderSource:
    relative_path: str
    role: str
    bytes_hash: str


@dataclass(frozen=True)
class ProviderManifest:
    provider_id: str
    version: str
    provider_type: ProviderType
    implementation_sources: tuple[ProviderSource, ...]
    transitive_helpers: tuple[ProviderSource, ...]
    resource_policy_path: str
    resource_policy_hash: str
    input_schema_path: str
    input_schema_hash: str
    output_schema_path: str
    output_schema_hash: str
    allowed_execution_contexts: tuple[str, ...]
    underlying_authority_ids: tuple[str, ...]
    status: ProviderStatus
    schema_version: int
    manifest_hash: str
