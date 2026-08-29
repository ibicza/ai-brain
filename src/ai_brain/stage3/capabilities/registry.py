from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.capabilities.models import CapabilityDescriptor, CapabilityStatus
from ai_brain.stage3.capabilities.validation import validate_descriptor
from ai_brain.stage3.knowledge_ir.version import CAPABILITY_REGISTRY_SCHEMA_VERSION


@dataclass(frozen=True)
class CapabilityRegistry:
    descriptors: tuple[CapabilityDescriptor, ...]
    schema_version: int
    registry_hash: str

    @classmethod
    def build(cls, descriptors: tuple[CapabilityDescriptor, ...]) -> CapabilityRegistry:
        ordered = tuple(sorted(descriptors, key=lambda x: (x.capability_id, x.version)))
        body = {
            "descriptors": ordered,
            "schema_version": CAPABILITY_REGISTRY_SCHEMA_VERSION,
        }
        value = cls(ordered, CAPABILITY_REGISTRY_SCHEMA_VERSION, content_hash(body))
        value.verify()
        return value

    def verify(self, provider_hashes: dict[str, str] | None = None) -> None:
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
            if (
                provider_hashes is not None
                and provider_hashes.get(item.provider_id)
                != item.provider_implementation_hash
            ):
                raise ValueError("capability provider implementation changed")
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
