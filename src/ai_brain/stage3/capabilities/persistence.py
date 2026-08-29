from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.capabilities.models import *
from ai_brain.stage3.capabilities.registry import CapabilityRegistry


def save_registry(registry: CapabilityRegistry, path: Path) -> None:
    registry.verify()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        canonical_json(asdict(registry)) + "\n", encoding="utf-8", newline="\n"
    )
    temporary.replace(path)


def load_registry(path: Path) -> CapabilityRegistry:
    row = json.loads(path.read_text(encoding="utf-8"))
    descriptors = tuple(
        CapabilityDescriptor(
            **{
                **x,
                "capability_kind": CapabilityKind(x["capability_kind"]),
                "authority_class": AuthorityClass(x["authority_class"]),
                "provider_type": ProviderType(x["provider_type"]),
                "status": CapabilityStatus(x["status"]),
                "required_capabilities": tuple(x["required_capabilities"]),
                "allowed_execution_contexts": tuple(x["allowed_execution_contexts"]),
            }
        )
        for x in row["descriptors"]
    )
    value = CapabilityRegistry(descriptors, row["schema_version"], row["registry_hash"])
    value.verify()
    return value
