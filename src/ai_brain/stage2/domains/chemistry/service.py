"""Production assembly and explicit-confirmation chemistry workflows."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.importer import (
    ChemistryImportSummary,
    build_chemistry_fact_memory,
)
from ai_brain.stage2.domains.chemistry.manifest import (
    build_domain_manifest,
    load_domain_manifest,
    verify_domain_manifest,
    write_domain_manifest,
)
from ai_brain.stage2.domains.chemistry.persistence import ChemistryResultStore
from ai_brain.stage2.domains.chemistry.router import ChemistryUnifiedRouter
from ai_brain.stage2.domains.chemistry.sources import SOURCE_FILES, default_source_dir
from ai_brain.stage2.domains.chemistry.tool_registry import (
    ChemistryToolRegistry,
    chemistry_tool_manifests,
)
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.router.models import (
    ConfirmationDecision,
    RequestSourceKind,
    RouteDecision,
    ToolCallProposal,
    ToolResultBundle,
    UnifiedResponseEnvelope,
)
from ai_brain.stage2.router.request import create_request
from ai_brain.stage2.router.service import UnifiedRouterService


@dataclass
class ChemistryDomainService:
    root: Path
    memory: FactMemory
    manifest: dict[str, Any]
    registry: ChemistryToolRegistry
    router: ChemistryUnifiedRouter
    unified: UnifiedRouterService
    results: ChemistryResultStore

    @classmethod
    def open(
        cls, root: Path, *, source_dir: Path | None = None
    ) -> ChemistryDomainService:
        resolved = root.resolve()
        memory = FactMemory.open(resolved / "fact_memory")
        manifest = load_domain_manifest(resolved / "domain_manifest.json")
        verify_domain_manifest(manifest, memory, source_dir)
        current = tuple(
            (key, value.manifest_hash)
            for key, value in sorted(chemistry_tool_manifests().items())
        )
        if tuple(tuple(row) for row in manifest["tool_manifest_hashes"]) != current:
            raise ValueError("chemistry tool manifests are stale")
        registry = ChemistryToolRegistry(memory, manifest["domain_manifest_hash"])
        router = ChemistryUnifiedRouter(tool_registry=registry, fact_memory=memory)
        return cls(
            resolved,
            memory,
            manifest,
            registry,
            router,
            UnifiedRouterService(router),
            ChemistryResultStore(resolved / "results"),
        )

    def route_text(
        self, text: str, language: str
    ) -> tuple[RouteDecision, UnifiedResponseEnvelope]:
        request = create_request(
            RequestSourceKind.CONTROLLED_LANGUAGE,
            original_input=text,
            language=language,
        )
        return self.unified.handle(request)

    def prepare_tool(
        self, tool_id: str, arguments: dict[str, Any]
    ) -> tuple[RouteDecision, UnifiedResponseEnvelope, ToolCallProposal]:
        request = create_request(
            RequestSourceKind.STRUCTURED_TOOL,
            structured_payload={"tool_id": tool_id, "arguments": arguments},
        )
        decision, response = self.unified.handle(request)
        if response.tool_proposal_hash is None:
            raise ValueError("chemistry tool request did not produce a proposal")
        return (
            decision,
            response,
            self.unified._tool_proposals[response.tool_proposal_hash],
        )

    def confirm_and_execute(
        self,
        prepared: UnifiedResponseEnvelope,
        proposal: ToolCallProposal,
        *,
        identity: str,
    ) -> tuple[ToolResultBundle | None, UnifiedResponseEnvelope]:
        confirmation = self.unified.confirm_tool(
            proposal, identity=identity, decision=ConfirmationDecision.CONFIRMED
        )
        result, response = self.unified.execute_tool_and_respond(
            prepared, proposal, confirmation
        )
        if result is not None and result.status.value == "EXECUTED":
            self.results.save(result.output)
        return result, response

    def verify(self) -> dict[str, Any]:
        verify_domain_manifest(self.manifest, self.memory)
        self.registry.verify()
        return {
            "fact_memory": self.memory.verify(),
            "domain_manifest_hash": self.manifest["domain_manifest_hash"],
            "reproducible_content_hash": self.manifest["reproducible_content_hash"],
            "tool_registry_hash": self.registry.registry_hash,
        }


def build_domain(
    root: Path, *, source_dir: Path | None = None
) -> tuple[ChemistryDomainService, ChemistryImportSummary]:
    resolved = root.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    input_sources = (source_dir or default_source_dir()).resolve()
    pack_sources = (resolved / "sources").resolve()
    if input_sources != pack_sources:
        pack_sources.mkdir(parents=True, exist_ok=True)
        for name in SOURCE_FILES:
            source = (input_sources / name).resolve()
            if input_sources not in source.parents or not source.is_file():
                raise ValueError(f"missing or unsafe chemistry source extract: {name}")
            shutil.copy2(source, pack_sources / name)
    memory, summary = build_chemistry_fact_memory(
        resolved / "fact_memory", pack_sources
    )
    tool_hashes = tuple(
        (key, value.manifest_hash)
        for key, value in sorted(chemistry_tool_manifests().items())
    )
    manifest = build_domain_manifest(memory, pack_sources, tool_hashes)
    write_domain_manifest(manifest, resolved / "domain_manifest.json")
    return ChemistryDomainService.open(resolved, source_dir=pack_sources), summary
