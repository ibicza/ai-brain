from __future__ import annotations

from typing import Protocol

from ai_brain.stage3.domains.pack import ConceptGraph, DomainPack
from ai_brain.stage3.domains.validation import validate_pack


class DomainRuntime(Protocol):
    def domain_id(self) -> str: ...
    def pack_hash(self) -> str: ...
    def concept_graph(self) -> ConceptGraph: ...
    def exercise_families(self): ...
    def concepts_for_exercise_family(self, family_id: str) -> tuple[str, ...]: ...
    def capabilities_for_operation(self, operation: str) -> tuple[str, ...]: ...
    def resolve_catalog_candidates(self, entries, concept_id: str): ...
    def resolve_fact_schema(self, knowledge_id: str): ...
    def resolve_adapter(self, capability_id: str): ...
    def verify_currentness(self) -> dict: ...
    def public_domain_summary(self) -> dict: ...


class GenericDomainRuntime:
    def __init__(
        self,
        pack: DomainPack,
        adapters: dict[str, object] | None = None,
        installed_registry=None,
    ) -> None:
        validate_pack(pack)
        self._pack = pack
        self._adapters = adapters or {}
        self._installed_registry = installed_registry

    def domain_id(self):
        return self._pack.manifest.domain_id

    def pack_hash(self):
        return self._pack.manifest.pack_content_hash

    def concept_graph(self):
        return self._pack.concept_graph

    def exercise_families(self):
        return self._pack.exercise_families

    def concepts_for_exercise_family(self, family_id):
        item = next(
            (x for x in self._pack.exercise_families if x.family_id == str(family_id)),
            None,
        )
        if item is None:
            raise KeyError(family_id)
        return item.concept_ids

    def capabilities_for_operation(self, operation):
        item = next(
            (x for x in self._pack.exercise_families if x.family_id == str(operation)),
            None,
        )
        return item.required_capabilities if item else ()

    def resolve_catalog_candidates(self, entries, concept_id):
        families = {
            x.family_id
            for x in self._pack.exercise_families
            if concept_id in x.concept_ids
        }
        return tuple(
            x
            for x in entries
            if str(x.exercise_spec.family) in families
            or x.exercise_spec.family.value in families
        )

    def resolve_fact_schema(self, knowledge_id):
        return next(
            x for x in self._pack.knowledge_records if x.knowledge_id == knowledge_id
        )

    def resolve_adapter(self, capability_id):
        binding = next(
            (
                x
                for x in self._pack.adapter_bindings
                if capability_id in x.capability_ids
            ),
            None,
        )
        if binding is None or binding.adapter_id not in self._adapters:
            raise KeyError(capability_id)
        return self._adapters[binding.adapter_id]

    def verify_currentness(self):
        if self._installed_registry is None:
            return {
                **validate_pack(self._pack),
                "current": False,
                "reason": "INSTALLED_AUTHORITY_REQUIRED",
            }
        result = self._installed_registry.verify_currentness(
            self.domain_id(), self._pack.manifest.pack_version
        )
        if result["pack_hash"] != self.pack_hash():
            raise ValueError("runtime pack differs from installed authority")
        return result

    def public_domain_summary(self):
        m = self._pack.manifest
        return {
            "domain_id": m.domain_id,
            "pack_version": m.pack_version,
            "pack_hash": m.pack_content_hash,
            "names": {"ru": m.canonical_name_ru, "en": m.canonical_name_en},
            "languages": m.supported_languages,
            "concept_count": len(self._pack.concept_graph.nodes),
        }
