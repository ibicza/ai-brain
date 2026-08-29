from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.capabilities.models import ProviderType
from ai_brain.stage3.providers.models import (
    ProviderManifest,
    ProviderSource,
    ProviderStatus,
)
from ai_brain.stage3.providers.registry import ProviderRegistry


def save_provider_registry(registry: ProviderRegistry, path: Path) -> None:
    registry.verify()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        canonical_json(asdict(registry)) + "\n", encoding="utf-8", newline="\n"
    )


def load_provider_registry(path: Path) -> ProviderRegistry:
    row = json.loads(path.read_text(encoding="utf-8"))
    manifests = tuple(
        ProviderManifest(
            **{
                **item,
                "provider_type": ProviderType(item["provider_type"]),
                "implementation_sources": tuple(
                    ProviderSource(**x) for x in item["implementation_sources"]
                ),
                "transitive_helpers": tuple(
                    ProviderSource(**x) for x in item["transitive_helpers"]
                ),
                "allowed_execution_contexts": tuple(item["allowed_execution_contexts"]),
                "underlying_authority_ids": tuple(item["underlying_authority_ids"]),
                "status": ProviderStatus(item["status"]),
            }
        )
        for item in row["manifests"]
    )
    result = ProviderRegistry(
        row["root"], manifests, row["schema_version"], row["registry_hash"]
    )
    result.verify()
    return result
