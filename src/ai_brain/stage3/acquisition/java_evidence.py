"""Policy-denominated, independently reproducible Java field evidence."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_evidence_policy import (
    JavaEvidenceClass,
    JavaEvidencePolicyManifest,
    JavaEvidenceRequirement,
    enumerate_java_evidence_requirements,
    load_java_evidence_policy,
    match_java_evidence_policy,
    verify_java_evidence_policy,
)
from ai_brain.stage3.acquisition.java_evidence_transforms import (
    load_java_evidence_transformation_manifest,
    normalized_transformation_output,
)
from ai_brain.stage3.acquisition.java_proposals import JavaProposalBatch
from ai_brain.stage3.acquisition.java_source_index import (
    JavaSourceIndex,
    declaration_by_node_id,
)
from ai_brain.stage3.acquisition.models import SourceBundle, SourceLocation

JAVA_EVIDENCE_EXTRACTOR_VERSION = "m342.java-field-evidence.v2"


@dataclass(frozen=True)
class JavaFieldEvidence:
    proposal_id: str
    proposal_hash: str
    field_path: str
    evidence_class: JavaEvidenceClass
    document_id: str
    document_bytes_hash: str
    source_location: SourceLocation
    source_span_hash: str
    parser_node_id: str
    semantic_identity_hash: str
    requirement_hash: str
    transformation_id: str
    transformation_version: str
    transformation_hash: str
    normalized_output: str
    derivation_receipt_hash: str
    transformation_registry_hash: str | None
    output_hash: str
    evidence_hash: str


@dataclass(frozen=True)
class JavaFieldEvidenceManifest:
    bundle_hash: str
    source_index_hash: str
    proposal_manifest_hash: str
    evidence_policy_hash: str
    requirement_manifest_hash: str
    required_field_count: int
    evidence_count: int
    exact_count: int
    missing_count: int
    extra_count: int
    duplicate_count: int
    wrong_count: int
    completeness_ratio: str
    exactness_ratio: str
    missing_requirements: tuple[tuple[str, str], ...]
    evidence: tuple[JavaFieldEvidence, ...]
    transformation_registry_hash: str | None
    policy_coverage_hash: str | None
    manifest_hash: str


def build_java_field_evidence_manifest(
    proposal_batch: JavaProposalBatch,
    source_index: JavaSourceIndex,
    bundle: SourceBundle,
    store,
    *,
    policy: JavaEvidencePolicyManifest | None = None,
    omit_fields: tuple[str, ...] = (),
) -> JavaFieldEvidenceManifest:
    policy = policy or load_java_evidence_policy()
    requirements = enumerate_java_evidence_requirements(
        proposal_batch, source_index, policy
    )
    evidence = _generate_evidence(
        requirements,
        proposal_batch,
        source_index,
        bundle,
        store,
        policy,
        omit_fields=frozenset(omit_fields),
    )
    return _manifest(
        proposal_batch, source_index, bundle, policy, requirements, evidence
    )


def verify_java_field_evidence_manifest(
    manifest: JavaFieldEvidenceManifest,
    proposal_batch: JavaProposalBatch,
    source_index: JavaSourceIndex,
    bundle: SourceBundle,
    store,
    *,
    policy: JavaEvidencePolicyManifest | None = None,
) -> None:
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    if content_hash(body) != claimed:
        raise ValueError("Java field evidence manifest hash mismatch")
    policy = policy or load_java_evidence_policy()
    verify_java_evidence_policy(policy)
    requirements = enumerate_java_evidence_requirements(
        proposal_batch, source_index, policy
    )
    expected_evidence = _generate_evidence(
        requirements,
        proposal_batch,
        source_index,
        bundle,
        store,
        policy,
        omit_fields=frozenset(),
    )
    rebuilt = _manifest(
        proposal_batch,
        source_index,
        bundle,
        policy,
        requirements,
        manifest.evidence,
    )
    if rebuilt != manifest:
        raise ValueError("Java field evidence metrics are not reproducible")
    expected_by_key = {
        (item.proposal_id, item.field_path): item for item in expected_evidence
    }
    for item in manifest.evidence:
        if expected_by_key.get((item.proposal_id, item.field_path)) != item:
            raise ValueError("Java field evidence transformation mismatch")


def evidence_by_proposal(
    manifest: JavaFieldEvidenceManifest,
) -> dict[str, tuple[JavaFieldEvidence, ...]]:
    result: dict[str, list[JavaFieldEvidence]] = {}
    for item in manifest.evidence:
        result.setdefault(item.proposal_id, []).append(item)
    return {
        key: tuple(sorted(values, key=lambda item: item.field_path))
        for key, values in result.items()
    }


def incomplete_evidence_proposal_ids(
    manifest: JavaFieldEvidenceManifest,
) -> frozenset[str]:
    return frozenset(item[0] for item in manifest.missing_requirements)


def nonexact_evidence_proposal_ids(
    manifest: JavaFieldEvidenceManifest,
    proposal_batch: JavaProposalBatch,
    source_index: JavaSourceIndex,
    policy: JavaEvidencePolicyManifest,
) -> frozenset[str]:
    """Return every proposal without a one-to-one exact requirement receipt."""

    requirements = enumerate_java_evidence_requirements(
        proposal_batch, source_index, policy
    )
    expected = {
        (item.proposal_id, item.field_path): item for item in requirements
    }
    counts = Counter((item.proposal_id, item.field_path) for item in manifest.evidence)
    invalid = {item[0] for item in manifest.missing_requirements}
    for item in manifest.evidence:
        key = (item.proposal_id, item.field_path)
        requirement = expected.get(key)
        if (
            requirement is None
            or counts[key] != 1
            or item.requirement_hash != requirement.requirement_hash
            or item.normalized_output != requirement.expected_output
            or item.evidence_class != requirement.evidence_class
        ):
            invalid.add(item.proposal_id)
    return frozenset(invalid)


def _generate_evidence(
    requirements,
    proposal_batch,
    source_index,
    bundle,
    store,
    policy,
    *,
    omit_fields,
):
    if (
        proposal_batch.bundle_hash != bundle.bundle_hash
        or proposal_batch.source_index_hash != source_index.index_hash
    ):
        raise ValueError("Java evidence input closure mismatch")
    nodes = declaration_by_node_id(source_index)
    documents = {item.document_id: item for item in bundle.documents}
    proposals = {item.proposal_id: item for item in proposal_batch.proposals}
    bindings = {item.proposal_id: item for item in proposal_batch.bindings}
    registry = (
        load_java_evidence_transformation_manifest()
        if policy.schema_version == 2
        else None
    )
    result = []
    for requirement in requirements:
        if requirement.field_path in omit_fields:
            continue
        declaration = nodes[requirement.parser_node_id]
        document = documents[declaration.document_id]
        raw = store.get_blob(document.bytes_hash)
        location = requirement.source_location
        span = raw[location.byte_start : location.byte_end]
        normalized_output = (
            normalized_transformation_output(
                requirement.transformation_id,
                requirement=requirement,
                declaration=declaration,
                proposal=proposals[requirement.proposal_id],
                binding=bindings[requirement.proposal_id],
                raw_source=raw,
            )
            if registry is not None
            else requirement.expected_output
        )
        transformation_hash = content_hash(
            {
                "policy_artifact_hash": policy.policy_artifact_hash,
                "policy_manifest_hash": policy.manifest_hash,
                "transformation_id": requirement.transformation_id,
                "extractor_version": JAVA_EVIDENCE_EXTRACTOR_VERSION,
                "transformation_registry_hash": (
                    registry.transformation_manifest_hash if registry else None
                ),
                "policy_rule_hash": requirement.policy_rule_hash,
            }
        )
        receipt_body = {
            "requirement_hash": requirement.requirement_hash,
            "proposal_hash": requirement.proposal_hash,
            "document_bytes_hash": declaration.source_snapshot_hash,
            "source_span_hash": bytes_hash(span),
            "semantic_identity_hash": declaration.declaration_hash,
            "transformation_hash": transformation_hash,
            "normalized_output": normalized_output,
            "output_hash": content_hash(normalized_output),
        }
        body = {
            "proposal_id": requirement.proposal_id,
            "proposal_hash": requirement.proposal_hash,
            "field_path": requirement.field_path,
            "evidence_class": requirement.evidence_class,
            "document_id": declaration.document_id,
            "document_bytes_hash": declaration.source_snapshot_hash,
            "source_location": location,
            "source_span_hash": bytes_hash(span),
            "parser_node_id": declaration.node_id,
            "semantic_identity_hash": declaration.declaration_hash,
            "requirement_hash": requirement.requirement_hash,
            "transformation_id": requirement.transformation_id,
            "transformation_version": JAVA_EVIDENCE_EXTRACTOR_VERSION,
            "transformation_hash": transformation_hash,
            "normalized_output": normalized_output,
            "derivation_receipt_hash": content_hash(receipt_body),
            "transformation_registry_hash": (
                registry.transformation_manifest_hash if registry else None
            ),
            "output_hash": content_hash(normalized_output),
        }
        result.append(JavaFieldEvidence(**body, evidence_hash=content_hash(body)))
    return tuple(sorted(result, key=lambda item: (item.proposal_id, item.field_path)))


def _manifest(
    proposal_batch,
    source_index,
    bundle,
    policy,
    requirements: tuple[JavaEvidenceRequirement, ...],
    evidence,
):
    required = {(item.proposal_id, item.field_path): item for item in requirements}
    counts = Counter((item.proposal_id, item.field_path) for item in evidence)
    present = {(item.proposal_id, item.field_path): item for item in evidence}
    duplicates = sum(value - 1 for value in counts.values() if value > 1)
    missing = tuple(sorted(set(required) - set(present)))
    extra = tuple(sorted(set(present) - set(required)))
    exact = sum(
        item.requirement_hash == required[key].requirement_hash
        and item.normalized_output == required[key].expected_output
        and item.evidence_class == required[key].evidence_class
        for key, item in present.items()
        if key in required and counts[key] == 1
    )
    wrong = len(set(required).intersection(present)) - exact
    requirement_manifest = tuple(
        (item.proposal_id, item.field_path, item.requirement_hash)
        for item in requirements
    )
    denominator = len(required)
    exact_denominator = len(evidence)
    if policy.schema_version == 2:
        _requirements, coverage = match_java_evidence_policy(
            proposal_batch, source_index, policy
        )
        registry_hash = (
            load_java_evidence_transformation_manifest().transformation_manifest_hash
        )
        coverage_hash = coverage.coverage_hash
    else:
        registry_hash = None
        coverage_hash = None
    body = {
        "bundle_hash": bundle.bundle_hash,
        "source_index_hash": source_index.index_hash,
        "proposal_manifest_hash": proposal_batch.proposal_manifest_hash,
        "evidence_policy_hash": policy.manifest_hash,
        "requirement_manifest_hash": content_hash(requirement_manifest),
        "required_field_count": denominator,
        "evidence_count": len(evidence),
        "exact_count": exact,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "duplicate_count": duplicates,
        "wrong_count": wrong,
        "completeness_ratio": _ratio(denominator - len(missing), denominator),
        "exactness_ratio": _ratio(exact, exact_denominator),
        "missing_requirements": missing,
        "evidence": tuple(evidence),
        "transformation_registry_hash": registry_hash,
        "policy_coverage_hash": coverage_hash,
    }
    return JavaFieldEvidenceManifest(**body, manifest_hash=content_hash(body))


def _ratio(numerator: int, denominator: int) -> str:
    return "N/A" if denominator == 0 else f"{numerator / denominator:.6f}"
