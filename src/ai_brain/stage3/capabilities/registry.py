from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.capabilities.models import CapabilityDescriptor, CapabilityStatus
from ai_brain.stage3.capabilities.validation import validate_descriptor
from ai_brain.stage3.knowledge_ir.version import CAPABILITY_REGISTRY_SCHEMA_VERSION

if TYPE_CHECKING:
    from ai_brain.stage3.providers.registry import ProviderRegistry


@dataclass(frozen=True)
class CapabilityRegistry:
    descriptors: tuple[CapabilityDescriptor, ...]
    schema_version: int
    registry_hash: str

    @classmethod
    def build(
        cls,
        descriptors: tuple[CapabilityDescriptor, ...],
        provider_registry: ProviderRegistry | None = None,
    ) -> CapabilityRegistry:
        ordered = tuple(sorted(descriptors, key=lambda x: (x.capability_id, x.version)))
        body = {
            "descriptors": ordered,
            "schema_version": CAPABILITY_REGISTRY_SCHEMA_VERSION,
        }
        value = cls(ordered, CAPABILITY_REGISTRY_SCHEMA_VERSION, content_hash(body))
        value.verify(provider_registry)
        return value

    def verify(self, provider_registry: ProviderRegistry | None = None) -> None:
        if self.schema_version != CAPABILITY_REGISTRY_SCHEMA_VERSION:
            raise ValueError("unsupported capability registry schema")
        keys: set[tuple[str, str]] = set()
        known = {item.capability_id for item in self.descriptors}
        for item in self.descriptors:
            validate_descriptor(item)
            key = (item.capability_id, item.version)
            if key in keys:
                raise ValueError("duplicate capability descriptor")
            keys.add(key)
            if not set(item.required_capabilities) <= known:
                raise ValueError("missing capability dependency")
            if provider_registry is None:
                raise ValueError("provider registry v2 is required")
            try:
                provider = provider_registry.current_manifest(
                    item.provider_id, item.provider_version
                )
            except KeyError as error:
                raise ValueError(
                    "capability provider is unavailable or deprecated"
                ) from error
            implementation_hash = content_hash(
                tuple(
                    source.bytes_hash
                    for source in (
                        *provider.implementation_sources,
                        *provider.transitive_helpers,
                    )
                )
            )
            if (
                provider.provider_type is not item.provider_type
                or provider.manifest_hash != item.provider_manifest_hash
                or provider.input_schema_hash != item.input_schema_hash
                or provider.output_schema_hash != item.output_schema_hash
                or provider.resource_policy_hash != item.resource_policy_hash
                or provider.allowed_execution_contexts
                != item.allowed_execution_contexts
                or implementation_hash != item.provider_implementation_hash
            ):
                raise ValueError("capability provider manifest binding changed")
        body = {"descriptors": self.descriptors, "schema_version": self.schema_version}
        if self.registry_hash != content_hash(body):
            raise ValueError("capability registry hash mismatch")
        self._verify_acyclic()

    def descriptor(
        self, capability_id: str, version: str | None = None
    ) -> CapabilityDescriptor:
        matches = [
            x
            for x in self.descriptors
            if x.capability_id == capability_id
            and x.status is CapabilityStatus.ACTIVE
            and (version is None or x.version == version)
        ]
        if not matches:
            raise KeyError(capability_id)
        return max(matches, key=lambda x: tuple(int(p) for p in x.version.split(".")))

    def _verify_acyclic(self) -> None:
        edges = {x.capability_id: x.required_capabilities for x in self.descriptors}
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("capability dependency cycle")
            if node in done:
                return
            visiting.add(node)
            for child in edges.get(node, ()):
                visit(child)
            visiting.remove(node)
            done.add(node)

        for node in edges:
            visit(node)
