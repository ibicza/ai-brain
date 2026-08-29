"""Build the frozen M-33 provider/capability authority from exact local bytes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityStatus,
    ProviderType,
)
from ai_brain.stage3.capabilities.persistence import save_registry
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.capabilities.validation import descriptor_hash
from ai_brain.stage3.providers.models import ProviderSource, ProviderStatus
from ai_brain.stage3.providers.persistence import save_provider_registry
from ai_brain.stage3.providers.registry import ProviderRegistry, make_provider_manifest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/stage3/m33"
RESOURCE = "schemas/stage3/provider_resource_policy_v2.json"

SPECS = (
    (
        "generic.record_query",
        "generic.record_query.v1",
        ProviderType.TOOL,
        CapabilityKind.FACT_RETRIEVAL,
        "src/ai_brain/stage3/domains/education.py",
        "m33_record_query",
        (),
    ),
    (
        "generic.taxonomy_query",
        "generic.taxonomy_query.v1",
        ProviderType.TOOL,
        CapabilityKind.TAXONOMY_REASONING,
        "src/ai_brain/stage3/domains/education.py",
        "m33_taxonomy_query",
        (),
    ),
    (
        "generic.temporal_query",
        "generic.temporal_query.v1",
        ProviderType.TOOL,
        CapabilityKind.TEMPORAL_REASONING,
        "src/ai_brain/stage3/domains/education.py",
        "m33_temporal_query",
        (),
    ),
    (
        "generic.api_contract_query",
        "generic.api_contract_query.v1",
        ProviderType.TOOL,
        CapabilityKind.FACT_RETRIEVAL,
        "src/ai_brain/stage3/domains/education.py",
        "m33_api_contract_query",
        (),
    ),
    (
        "generic.typed_scalar_equation_solver",
        "generic.typed_scalar_equation_solver.v1",
        ProviderType.SOLVER,
        CapabilityKind.EQUATION_EVALUATION,
        "src/ai_brain/stage3/capabilities/typed_scalar_equation_solver.py",
        "m33_equation_solver",
        ("generic.unit_conversion.v1",),
    ),
    (
        "generic.unit_conversion",
        "generic.unit_conversion.v1",
        ProviderType.SOLVER,
        CapabilityKind.UNIT_CONVERSION,
        "src/ai_brain/stage3/capabilities/typed_scalar_equation_solver.py",
        "m33_unit_conversion",
        (),
    ),
    (
        "generic.source_backed_explanation",
        "generic.source_backed_explanation.v1",
        ProviderType.TOOL,
        CapabilityKind.SOURCE_VERIFICATION,
        "src/ai_brain/stage3/domains/education.py",
        "m33_explanation",
        (),
    ),
    (
        "generic.exact_grading",
        "generic.exact_grading.v1",
        ProviderType.TOOL,
        CapabilityKind.GRADING,
        "src/ai_brain/stage3/domains/education.py",
        "m33_grading",
        (),
    ),
)


def main() -> None:
    resource_hash = bytes_hash((ROOT / RESOURCE).read_bytes())
    manifests = []
    for provider_id, _, provider_type, _, source, schema, _ in SPECS:
        input_path = f"schemas/stage3/{schema}_input.schema.json"
        output_path = f"schemas/stage3/{schema}_output.schema.json"
        manifests.append(
            make_provider_manifest(
                provider_id=provider_id,
                version="1.0.0",
                provider_type=provider_type,
                implementation_sources=(
                    ProviderSource(
                        source,
                        "IMPLEMENTATION",
                        bytes_hash((ROOT / source).read_bytes()),
                    ),
                ),
                transitive_helpers=(),
                resource_policy_path=RESOURCE,
                resource_policy_hash=resource_hash,
                input_schema_path=input_path,
                input_schema_hash=bytes_hash((ROOT / input_path).read_bytes()),
                output_schema_path=output_path,
                output_schema_hash=bytes_hash((ROOT / output_path).read_bytes()),
                allowed_execution_contexts=(
                    "USER_RUNTIME",
                    "OFFLINE_COMPILATION",
                ),
                underlying_authority_ids=(),
                status=ProviderStatus.ACTIVE,
            )
        )
    providers = ProviderRegistry.build(ROOT, tuple(manifests))
    descriptors = []
    for provider_id, capability_id, _, kind, _, _, dependencies in SPECS:
        provider = providers.manifest(provider_id, "1.0.0")
        implementation_hash = content_hash(
            tuple(
                item.bytes_hash
                for item in (
                    *provider.implementation_sources,
                    *provider.transitive_helpers,
                )
            )
        )
        value = CapabilityDescriptor(
            capability_id,
            "1.0.0",
            kind,
            capability_id,
            capability_id,
            provider.input_schema_hash,
            provider.output_schema_hash,
            True,
            AuthorityClass.READ_ONLY_EXACT,
            provider.provider_type,
            provider.provider_id,
            provider.version,
            provider.manifest_hash,
            implementation_hash,
            dependencies,
            provider.allowed_execution_contexts,
            provider.resource_policy_hash,
            CapabilityStatus.ACTIVE,
            "",
        )
        descriptors.append(replace(value, descriptor_hash=descriptor_hash(value)))
    capabilities = CapabilityRegistry.build(tuple(descriptors), providers)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    save_provider_registry(providers, OUTPUT / "provider_registry.json")
    save_registry(capabilities, OUTPUT / "capability_registry.json", providers)
    print(providers.registry_hash)
    print(capabilities.registry_hash)


if __name__ == "__main__":
    main()
