from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash, utc_now
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityRequirement,
    CapabilityResolution,
    CapabilityResolutionReceipt,
    ProviderType,
    ResolutionStatus,
)
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.knowledge_ir.version import CAPABILITY_RESOLUTION_SCHEMA_VERSION


def resolve_capability(
    registry: CapabilityRegistry,
    requirement: CapabilityRequirement,
    *,
    requesting_domain_id: str,
    requesting_pack_hash: str,
    provider_hashes: dict[str, str],
    resolved_at: str | None = None,
) -> CapabilityResolution:
    registry.verify(provider_hashes)
    try:
        descriptor = registry.descriptor(requirement.capability_id)
    except KeyError:
        return CapabilityResolution(ResolutionStatus.NEEDS_NEW_CAPABILITY, None, None)
    if not _matches(descriptor.version, requirement.version_range):
        return CapabilityResolution(ResolutionStatus.NEEDS_NEW_CAPABILITY, None, None)
    if requirement.execution_context not in descriptor.allowed_execution_contexts:
        return CapabilityResolution(ResolutionStatus.NEEDS_NEW_CAPABILITY, None, None)
    if (
        descriptor.authority_class is AuthorityClass.OFFLINE_COMPILATION_ONLY
        and requirement.execution_context != "OFFLINE_COMPILATION"
    ):
        return CapabilityResolution(ResolutionStatus.NEEDS_NEW_CAPABILITY, None, None)
    # TOOL and SKILL remain the existing execution authorities. Other providers
    # are exact parser/verifier/adapter contracts bound by their implementation hash.
    if (
        descriptor.provider_type in {ProviderType.TOOL, ProviderType.SKILL}
        and descriptor.provider_id not in provider_hashes
    ):
        return CapabilityResolution(ResolutionStatus.NEEDS_NEW_CAPABILITY, None, None)
    body = {
        "requesting_domain_id": requesting_domain_id,
        "requesting_pack_hash": requesting_pack_hash,
        "required_capability_id": requirement.capability_id,
        "required_version_range": requirement.version_range,
        "selected_descriptor_hash": descriptor.descriptor_hash,
        "provider_id": descriptor.provider_id,
        "provider_implementation_hash": descriptor.provider_implementation_hash,
        "dependency_capabilities": descriptor.required_capabilities,
        "authority_class": descriptor.authority_class,
        "execution_context": requirement.execution_context,
        "registry_hash": registry.registry_hash,
        "resolved_at": resolved_at or utc_now(),
        "schema_version": CAPABILITY_RESOLUTION_SCHEMA_VERSION,
    }
    receipt = CapabilityResolutionReceipt(**body, receipt_hash=content_hash(body))
    return CapabilityResolution(ResolutionStatus.RESOLVED, descriptor, receipt)


def verify_resolution(
    receipt: CapabilityResolutionReceipt,
    registry: CapabilityRegistry,
    provider_hashes: dict[str, str],
) -> None:
    body = asdict(receipt)
    digest = body.pop("receipt_hash")
    if (
        receipt.schema_version != CAPABILITY_RESOLUTION_SCHEMA_VERSION
        or content_hash(body) != digest
    ):
        raise ValueError("capability resolution receipt hash or schema mismatch")
    if receipt.registry_hash != registry.registry_hash:
        raise ValueError("capability resolution registry is stale")
    descriptor = registry.descriptor(receipt.required_capability_id)
    if (
        descriptor.descriptor_hash != receipt.selected_descriptor_hash
        or provider_hashes.get(receipt.provider_id)
        != receipt.provider_implementation_hash
    ):
        raise ValueError("capability resolution authority changed")


def _matches(version: str, expression: str) -> bool:
    if expression in {"*", version}:
        return True
    if expression.endswith(".*"):
        return version.startswith(expression[:-1])
    if expression.startswith("^"):
        return version.split(".", 1)[0] == expression[1:].split(".", 1)[0]
    return False
