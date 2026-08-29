"""Recursive capability/provider closure and immutable v2 receipts."""

from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.facts.canonical import content_hash, utc_now
from ai_brain.stage3.capabilities.models import (
    AuthorityClass,
    CapabilityDescriptor,
    CapabilityRequirement,
    CapabilityResolution,
    CapabilityResolutionReceipt,
    ResolutionStatus,
)
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.capabilities.semver import matches_version
from ai_brain.stage3.knowledge_ir.version import CAPABILITY_RESOLUTION_SCHEMA_VERSION
from ai_brain.stage3.providers.registry import ProviderRegistry


def resolve_capability(
    registry: CapabilityRegistry,
    requirement: CapabilityRequirement,
    *,
    requesting_domain_id: str,
    requesting_pack_hash: str,
    provider_registry: ProviderRegistry | None = None,
    provider_hashes: dict[str, str] | None = None,
    required_input_schema_hash: str | None = None,
    required_output_schema_hash: str | None = None,
    resolved_at: str | None = None,
) -> CapabilityResolution:
    """Resolve a complete DAG. A descriptor-derived hash map is never authority."""
    del provider_hashes
    if provider_registry is None:
        return CapabilityResolution(ResolutionStatus.NEEDS_NEW_CAPABILITY, None, None)
    try:
        registry.verify(provider_registry)
        descriptor = registry.descriptor(requirement.capability_id)
        if not matches_version(descriptor.version, requirement.version_range):
            return CapabilityResolution(
                ResolutionStatus.NEEDS_NEW_CAPABILITY, None, None
            )
        if (
            required_input_schema_hash is not None
            and descriptor.input_schema_hash != required_input_schema_hash
        ) or (
            required_output_schema_hash is not None
            and descriptor.output_schema_hash != required_output_schema_hash
        ):
            return CapabilityResolution(
                ResolutionStatus.NEEDS_NEW_CAPABILITY, None, None
            )
        closure = _descriptor_closure(registry, descriptor)
        _verify_closure_policy(closure, requirement.execution_context)
    except (KeyError, ValueError):
        return CapabilityResolution(ResolutionStatus.NEEDS_NEW_CAPABILITY, None, None)
    stamp = resolved_at or utc_now()
    dag_hash = content_hash(
        tuple(
            (item.capability_id, item.version, item.descriptor_hash)
            for item in sorted(
                closure, key=lambda value: (value.capability_id, value.version)
            )
        )
    )
    receipts: dict[str, CapabilityResolutionReceipt] = {}

    def issue(
        item: CapabilityDescriptor, requested_range: str
    ) -> CapabilityResolutionReceipt:
        dependency_receipts = tuple(
            issue(registry.descriptor(identity), "*")
            for identity in item.required_capabilities
        )
        provider = provider_registry.current_manifest(
            item.provider_id, item.provider_version
        )
        body = {
            "requesting_domain_id": requesting_domain_id,
            "requesting_pack_hash": requesting_pack_hash,
            "required_capability_id": item.capability_id,
            "required_version_range": requested_range,
            "selected_capability_version": item.version,
            "selected_descriptor_hash": item.descriptor_hash,
            "provider_id": item.provider_id,
            "provider_version": item.provider_version,
            "provider_manifest_hash": provider.manifest_hash,
            "provider_implementation_hash": item.provider_implementation_hash,
            "dependency_capabilities": item.required_capabilities,
            "dependency_receipt_hashes": tuple(
                value.receipt_hash for value in dependency_receipts
            ),
            "dependency_dag_hash": dag_hash,
            "authority_class": item.authority_class,
            "execution_context": requirement.execution_context,
            "input_schema_hash": item.input_schema_hash,
            "output_schema_hash": item.output_schema_hash,
            "registry_hash": registry.registry_hash,
            "provider_registry_hash": provider_registry.registry_hash,
            "resolved_at": stamp,
            "schema_version": CAPABILITY_RESOLUTION_SCHEMA_VERSION,
        }
        receipt = CapabilityResolutionReceipt(**body, receipt_hash=content_hash(body))
        receipts[item.capability_id] = receipt
        return receipt

    root = issue(descriptor, requirement.version_range)
    ordered = tuple(receipts[item.capability_id] for item in closure)
    return CapabilityResolution(ResolutionStatus.RESOLVED, descriptor, root, ordered)


def verify_resolution(
    receipt: CapabilityResolutionReceipt,
    registry: CapabilityRegistry,
    provider_registry: ProviderRegistry,
    closure_receipts: tuple[CapabilityResolutionReceipt, ...] = (),
) -> None:
    registry.verify(provider_registry)
    body = asdict(receipt)
    digest = body.pop("receipt_hash")
    if (
        receipt.schema_version != CAPABILITY_RESOLUTION_SCHEMA_VERSION
        or content_hash(body) != digest
    ):
        raise ValueError("capability resolution receipt hash or schema mismatch")
    if (
        receipt.registry_hash != registry.registry_hash
        or receipt.provider_registry_hash != provider_registry.registry_hash
    ):
        raise ValueError("capability resolution registry is stale")
    descriptor = registry.descriptor(
        receipt.required_capability_id, receipt.selected_capability_version
    )
    provider = provider_registry.current_manifest(
        receipt.provider_id, receipt.provider_version
    )
    if not matches_version(
        receipt.selected_capability_version, receipt.required_version_range
    ):
        raise ValueError("selected capability no longer matches requested range")
    if (
        descriptor.descriptor_hash != receipt.selected_descriptor_hash
        or descriptor.provider_id != receipt.provider_id
        or provider.manifest_hash != receipt.provider_manifest_hash
        or descriptor.provider_manifest_hash != provider.manifest_hash
        or descriptor.provider_implementation_hash
        != receipt.provider_implementation_hash
        or descriptor.input_schema_hash != receipt.input_schema_hash
        or descriptor.output_schema_hash != receipt.output_schema_hash
        or descriptor.required_capabilities != receipt.dependency_capabilities
        or receipt.execution_context not in descriptor.allowed_execution_contexts
    ):
        raise ValueError("capability resolution authority changed")
    if closure_receipts:
        by_hash = {item.receipt_hash: item for item in closure_receipts}
        if not set(receipt.dependency_receipt_hashes) <= set(by_hash):
            raise ValueError("capability dependency receipt closure is incomplete")
        for dependency_hash in receipt.dependency_receipt_hashes:
            verify_resolution(
                by_hash[dependency_hash], registry, provider_registry, closure_receipts
            )
        selected = tuple(
            sorted(
                {
                    (
                        item.required_capability_id,
                        item.selected_capability_version,
                        item.selected_descriptor_hash,
                    )
                    for item in closure_receipts
                    if item.dependency_dag_hash == receipt.dependency_dag_hash
                }
            )
        )
        if receipt.dependency_dag_hash != content_hash(selected):
            raise ValueError("capability dependency DAG hash mismatch")


def _descriptor_closure(
    registry: CapabilityRegistry, root: CapabilityDescriptor
) -> tuple[CapabilityDescriptor, ...]:
    result: list[CapabilityDescriptor] = []
    seen: set[str] = set()

    def visit(item: CapabilityDescriptor) -> None:
        if item.capability_id in seen:
            return
        seen.add(item.capability_id)
        for dependency in item.required_capabilities:
            visit(registry.descriptor(dependency))
        result.append(item)

    visit(root)
    return tuple(result)


def _verify_closure_policy(
    closure: tuple[CapabilityDescriptor, ...], context: str
) -> None:
    by_id = {item.capability_id: item for item in closure}
    for item in closure:
        if context not in item.allowed_execution_contexts:
            raise ValueError("capability execution context closure is incomplete")
        for dependency_id in item.required_capabilities:
            dependency = by_id[dependency_id]
            if not set(item.allowed_execution_contexts) <= set(
                dependency.allowed_execution_contexts
            ):
                raise ValueError("dependent capability weakens execution contexts")
            if not _authority_at_least(
                item.authority_class, dependency.authority_class
            ):
                raise ValueError("dependent capability weakens authority restrictions")


def _authority_at_least(parent: AuthorityClass, dependency: AuthorityClass) -> bool:
    if dependency is AuthorityClass.OFFLINE_COMPILATION_ONLY:
        return parent is AuthorityClass.OFFLINE_COMPILATION_ONLY
    if dependency is AuthorityClass.CONFIRMATION_REQUIRED:
        return parent in {
            AuthorityClass.CONFIRMATION_REQUIRED,
            AuthorityClass.OFFLINE_COMPILATION_ONLY,
        }
    if dependency is AuthorityClass.ASSISTIVE_ONLY:
        return parent is AuthorityClass.ASSISTIVE_ONLY
    if dependency is AuthorityClass.READ_ONLY_EXACT:
        return parent is not AuthorityClass.DESCRIPTIVE_ONLY
    return True
