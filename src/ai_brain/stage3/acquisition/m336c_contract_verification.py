"""Contract-generated H-stage views and fail-closed mutation verification."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.final_artifact_contract import (
    FINAL_ARTIFACT_CONTRACT_REGISTRY,
    FinalArtifactRole,
    contract_binary_claim,
)


@dataclass(frozen=True)
class ContractTreeArtifact:
    relative_path: str
    raw: bytes


@dataclass(frozen=True)
class ContractTreeVerification:
    artifact_count: int
    unknown_path_count: int
    missing_role_binding_count: int
    missing_protected_field_count: int
    extra_protected_field_count: int
    disclosure_claim_mismatch_count: int
    duplicate_path_count: int
    status: str
    report_hash: str


@dataclass(frozen=True)
class ContractMutationReport:
    mutation_count: int
    rejected_count: int
    accepted_count: int
    categories: tuple[tuple[str, int, int], ...]
    status: str
    report_hash: str


_ROLE_MANIFEST_PATH = "evaluation/m336c_h/role_manifest.json"
_DISCLOSURE_PATH = "evaluation/m336c_h/disclosure_report.json"


def build_contract_role_manifest(
    artifacts: tuple[ContractTreeArtifact, ...],
) -> bytes:
    bindings = tuple(
        (
            item.relative_path,
            FINAL_ARTIFACT_CONTRACT_REGISTRY.match(item.relative_path).role.value,
            FINAL_ARTIFACT_CONTRACT_REGISTRY.match(item.relative_path).artifact_type,
            bytes_hash(item.raw),
        )
        for item in sorted(artifacts, key=lambda value: value.relative_path)
    )
    body = {
        "schema_version": 1,
        "contract_hash": FINAL_ARTIFACT_CONTRACT_REGISTRY.contract.contract_hash,
        "bindings": bindings,
    }
    return (
        canonical_json({**body, "manifest_hash": content_hash(body)}) + "\n"
    ).encode()


def build_contract_disclosure_report(
    artifacts: tuple[ContractTreeArtifact, ...],
) -> bytes:
    claims = []
    for artifact in artifacts:
        contract = FINAL_ARTIFACT_CONTRACT_REGISTRY.match(artifact.relative_path)
        if contract.role in {
            FinalArtifactRole.FINAL_SOURCE_BYTES,
            FinalArtifactRole.FINAL_ACQUISITION_BYTES,
        }:
            claims.append(contract_binary_claim(artifact.relative_path, artifact.raw))
        elif contract.media_type == "application/json":
            claims.extend(
                FINAL_ARTIFACT_CONTRACT_REGISTRY.disclosure_claim_specs(
                    artifact.relative_path, artifact.raw
                )
            )
    ordered = tuple(sorted(set(claims)))
    body = {
        "schema_version": 1,
        "contract_hash": FINAL_ARTIFACT_CONTRACT_REGISTRY.contract.contract_hash,
        "claims": ordered,
        "minimum_claim_denominator": len(ordered),
    }
    return (canonical_json({**body, "report_hash": content_hash(body)}) + "\n").encode()


def complete_hypothetical_h_stage() -> tuple[ContractTreeArtifact, ...]:
    json_value = lambda value: (canonical_json(value) + "\n").encode()
    artifacts = (
        ContractTreeArtifact(
            "evaluation/m336c_h/source_snapshots/example/Example.java",
            b"package example; public final class Example {}\n",
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/acquisition_bundle/candidates/example/source.jar",
            b"m336c-hypothetical-source-archive",
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/acquisition_bundle/candidates/example/provenance.json",
            json_value(
                {
                    "schema_version": 1,
                    "artifact_authenticity_mode": "MULTI_CHANNEL_VERIFIED",
                    "artifact_digest": {"source_archive_sha256": "a" * 64},
                    "audit_event": {},
                    "conflicts": [],
                    "coordinate": "example:example:1",
                    "correspondence": {
                        "raw_sha256": "r" * 64,
                        "canonical_sha256": "n" * 64,
                    },
                    "envelope_hash": "e" * 64,
                    "license_claims": [],
                    "license_evidence_mode": "SPDX_TEMPLATE",
                    "license_status": "CORROBORATED",
                    "license_texts": [],
                    "pom_digest": {"pom_sha256": "p" * 64},
                    "pom_repository_metadata": {},
                    "repository_metadata": {},
                    "scm_revision": {
                        "immutable_commit": "c" * 40,
                        "source_tree_hash": "t" * 64,
                    },
                    "semantic_identity_hash": "i" * 64,
                }
            ),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/selector_receipt.json",
            json_value(
                {
                    "schema_version": 1,
                    "selected_relative_paths": ["example/Example.java"],
                    "raw_sha256": "r" * 64,
                    "canonical_sha256": "n" * 64,
                    "selector_output_hash": "s" * 64,
                }
            ),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/physical_census.json",
            json_value(
                {
                    "schema_version": 1,
                    "downloaded_candidate_count": 6,
                    "eligible_distinct_root_count": 6,
                    "real_callable_source_file_count": 1,
                    "real_callable_target_count": 1,
                    "reason": "DISCLOSED_DEVELOPMENT",
                    "report_hash": "h" * 64,
                    "selector_invocation_count": 1,
                    "status": "PASS",
                }
            ),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/production_output.json",
            json_value(
                {
                    "schema_version": 1,
                    "target_ids": ["java:example.Example"],
                    "proposal_manifest_hash": "p" * 64,
                    "trust_closure_hash": "t" * 64,
                    "candidate_pack_hash": "k" * 64,
                    "production_output_hash": "o" * 64,
                }
            ),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/candidate_pack/disclosure.json",
            json_value(
                {
                    "schema_version": 1,
                    "candidate_pack_hash": "k" * 64,
                    "target_ids": ["java:example.Example"],
                }
            ),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/oracle/output.json",
            json_value({"schema_version": 1, "oracle_hash": "o" * 64}),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/goldens/golden.json",
            json_value({"schema_version": 1, "golden_hash": "g" * 64}),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/evaluation_report.json",
            json_value({"schema_version": 1, "report_hash": "v" * 64}),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/release_approval.json",
            json_value({"schema_version": 1, "approval_hash": "a" * 64}),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/installation.json",
            json_value({"schema_version": 1, "installed_pack_hash": "k" * 64}),
        ),
        ContractTreeArtifact(
            "evaluation/m336c_h/final_decision.json",
            json_value({"schema_version": 1, "decision_hash": "d" * 64}),
        ),
    )
    manifest = ContractTreeArtifact(
        _ROLE_MANIFEST_PATH, build_contract_role_manifest(artifacts)
    )
    disclosure = ContractTreeArtifact(
        _DISCLOSURE_PATH, build_contract_disclosure_report(artifacts)
    )
    return (*artifacts, manifest, disclosure)


def verify_contract_tree(
    artifacts: tuple[ContractTreeArtifact, ...],
) -> ContractTreeVerification:
    paths = tuple(item.relative_path for item in artifacts)
    duplicate_count = len(paths) - len(set(paths))
    unknown = 0
    validation_failures = 0
    for artifact in artifacts:
        try:
            validation = FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
                artifact.relative_path, artifact.raw
            )
            validation_failures += int(validation.status != "PASS")
        except (ValueError, TypeError, UnicodeDecodeError):
            unknown += 1
    if unknown or validation_failures or duplicate_count:
        body = {
            "artifact_count": len(artifacts),
            "unknown_path_count": unknown,
            "missing_role_binding_count": 0,
            "missing_protected_field_count": validation_failures,
            "extra_protected_field_count": validation_failures,
            "disclosure_claim_mismatch_count": 0,
            "duplicate_path_count": duplicate_count,
            "status": "FAIL",
        }
        return ContractTreeVerification(**body, report_hash=content_hash(body))
    core = tuple(
        item
        for item in artifacts
        if item.relative_path not in {_ROLE_MANIFEST_PATH, _DISCLOSURE_PATH}
    )
    by_path = {item.relative_path: item.raw for item in artifacts}
    expected_manifest = build_contract_role_manifest(core)
    expected_disclosure = build_contract_disclosure_report(core)
    role_mismatch = int(by_path.get(_ROLE_MANIFEST_PATH) != expected_manifest)
    disclosure_mismatch = int(by_path.get(_DISCLOSURE_PATH) != expected_disclosure)
    claims_by_role: dict[FinalArtifactRole, set[str]] = {}
    observed_roles = set()
    for artifact in core:
        contract = FINAL_ARTIFACT_CONTRACT_REGISTRY.match(artifact.relative_path)
        observed_roles.add(contract.role)
        claims_by_role.setdefault(contract.role, set()).update(
            item[0] for item in _artifact_claims(artifact)
        )
    protected_roles = set(FINAL_ARTIFACT_CONTRACT_REGISTRY.contract.protected_roles)
    missing_roles = len(protected_roles - observed_roles)
    missing_claims = sum(
        len(
            FINAL_ARTIFACT_CONTRACT_REGISTRY.required_claim_kinds(role)
            - claims_by_role.get(role, set())
        )
        for role in protected_roles
    )
    body = {
        "artifact_count": len(artifacts),
        "unknown_path_count": unknown,
        "missing_role_binding_count": role_mismatch + missing_roles,
        "missing_protected_field_count": validation_failures + missing_claims,
        "extra_protected_field_count": validation_failures,
        "disclosure_claim_mismatch_count": disclosure_mismatch,
        "duplicate_path_count": duplicate_count,
        "status": "PASS"
        if not (
            unknown
            or validation_failures
            or missing_claims
            or role_mismatch
            or missing_roles
            or disclosure_mismatch
            or duplicate_count
        )
        else "FAIL",
    }
    return ContractTreeVerification(**body, report_hash=content_hash(body))


def _artifact_claims(artifact: ContractTreeArtifact):
    contract = FINAL_ARTIFACT_CONTRACT_REGISTRY.match(artifact.relative_path)
    if contract.role in {
        FinalArtifactRole.FINAL_SOURCE_BYTES,
        FinalArtifactRole.FINAL_ACQUISITION_BYTES,
    }:
        return (contract_binary_claim(artifact.relative_path, artifact.raw),)
    if contract.media_type == "application/json":
        return FINAL_ARTIFACT_CONTRACT_REGISTRY.disclosure_claim_specs(
            artifact.relative_path, artifact.raw
        )
    return ()


_MUTATION_CATEGORIES = (
    "UNKNOWN_ROOT_JSON",
    "RENAMED_ARTIFACT",
    "MISSING_QUALIFICATION_RECEIPT",
    "ADDITIONAL_SECRET_FIELD",
    "SECRET_UNDER_NEUTRAL_NAME",
    "ROLE_DOWNGRADE",
    "MISSING_SOURCE_HASH",
    "OMITTED_TARGET_IDENTITIES",
    "DUPLICATE_PATH",
    "MALFORMED_JSON",
    "DUPLICATE_JSON_KEY",
    "CHANGED_SCHEMA_VERSION",
    "INCOMPLETE_ROLE_MANIFEST",
    "INCOMPLETE_DISCLOSURE_CLAIMS",
)


def run_contract_mutation_battery(count: int = 1_008) -> ContractMutationReport:
    if count < 1_000:
        raise ValueError("contract mutation denominator must be at least 1000")
    baseline = complete_hypothetical_h_stage()
    if verify_contract_tree(baseline).status != "PASS":
        raise ValueError("hypothetical H-stage baseline is not valid")
    results: dict[str, list[int]] = {
        category: [0, 0] for category in _MUTATION_CATEGORIES
    }
    for index in range(count):
        category = _MUTATION_CATEGORIES[index % len(_MUTATION_CATEGORIES)]
        mutated = _mutate(baseline, category, index)
        rejected = verify_contract_tree(mutated).status == "FAIL"
        results[category][0] += 1
        results[category][1] += int(rejected)
    categories = tuple(
        (name, values[0], values[1]) for name, values in sorted(results.items())
    )
    rejected_count = sum(item[2] for item in categories)
    body = {
        "mutation_count": count,
        "rejected_count": rejected_count,
        "accepted_count": count - rejected_count,
        "categories": categories,
        "status": "PASS" if rejected_count == count else "FAIL",
    }
    return ContractMutationReport(**body, report_hash=content_hash(body))


def _mutate(
    baseline: tuple[ContractTreeArtifact, ...], category: str, index: int
) -> tuple[ContractTreeArtifact, ...]:
    values = list(baseline)
    production_path = "evaluation/m336c_h/production_output.json"
    provenance_path = (
        "evaluation/m336c_h/acquisition_bundle/candidates/example/provenance.json"
    )
    if category == "UNKNOWN_ROOT_JSON":
        values.append(ContractTreeArtifact(f"unknown-{index}.json", b"{}\n"))
    elif category == "RENAMED_ARTIFACT":
        values[0] = ContractTreeArtifact(
            f"evaluation/m336c_h/source_snapshots/example/Renamed{index}.txt",
            values[0].raw,
        )
    elif category == "MISSING_QUALIFICATION_RECEIPT":
        values = [item for item in values if item.relative_path != provenance_path]
    elif category in {"ADDITIONAL_SECRET_FIELD", "SECRET_UNDER_NEUTRAL_NAME"}:
        name = (
            "secret_token"
            if category == "ADDITIONAL_SECRET_FIELD"
            else f"neutral_{index}"
        )
        values = _json_add(values, production_path, name, f"SECRET:{index}")
    elif category in {"ROLE_DOWNGRADE", "INCOMPLETE_ROLE_MANIFEST"}:
        values = _replace_raw(values, _ROLE_MANIFEST_PATH, b'{"schema_version":1}\n')
    elif category == "MISSING_SOURCE_HASH":

        def remove_source_hash(body):
            body["correspondence"].pop("raw_sha256", None)
            return body

        values = _json_change(values, provenance_path, remove_source_hash)
    elif category == "OMITTED_TARGET_IDENTITIES":
        values = _json_remove(values, production_path, "target_ids")
    elif category == "DUPLICATE_PATH":
        values.append(values[0])
    elif category == "MALFORMED_JSON":
        values = _replace_raw(values, production_path, b"{")
    elif category == "DUPLICATE_JSON_KEY":
        values = _replace_raw(
            values, production_path, b'{"schema_version":1,"schema_version":1}\n'
        )
    elif category == "CHANGED_SCHEMA_VERSION":
        values = _json_set(values, production_path, "schema_version", 99)
    elif category == "INCOMPLETE_DISCLOSURE_CLAIMS":
        values = _replace_raw(values, _DISCLOSURE_PATH, b'{"schema_version":1}\n')
    else:
        raise ValueError("unknown contract mutation category")
    return tuple(values)


def _replace_raw(values, path, raw):
    return [
        ContractTreeArtifact(item.relative_path, raw)
        if item.relative_path == path
        else item
        for item in values
    ]


def _json_add(values, path, name, value):
    return _json_change(values, path, lambda body: {**body, name: value})


def _json_set(values, path, name, value):
    return _json_change(values, path, lambda body: {**body, name: value})


def _json_remove(values, path, name):
    def change(body):
        body.pop(name, None)
        return body

    return _json_change(values, path, change)


def _json_change(values, path, change):
    result = []
    for item in values:
        if item.relative_path == path:
            body = change(json.loads(item.raw))
            result.append(
                ContractTreeArtifact(path, (canonical_json(body) + "\n").encode())
            )
        else:
            result.append(item)
    return result
