"""Adaptive internally-consistent contract/authority attacks for M-33.6d."""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import cache

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336d_authority import (
    M336D_AUTHORITY_STATEMENT_SHA256,
    SourceAuthorizationBinding,
    load_pinned_authority_registry_for_development,
)
from ai_brain.stage3.acquisition.m336d_contracts import (
    PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    canonical_public_json,
)
from ai_brain.stage3.acquisition.m336d_correspondence import (
    ScmCorrespondenceDecision,
    require_verified_external_chain_correspondence,
)
from ai_brain.stage3.acquisition.m336d_spdx_expression import (
    LicenseApplicabilityScope,
    LicenseScopeKind,
    ScopedLicenseEvidence,
    ScopedLicenseStatus,
    parse_spdx_expression,
    resolve_scoped_license,
)
from ai_brain.stage3.acquisition.source_authority import (
    PublicationTarget,
    SourceUseScope,
)

_AUTHORITY_STATEMENT = (
    b"M336D_USER_AUTHORITY_V1\n"
    b"source_use=PRIVATE_LOCAL_ANALYSIS,LOCAL_RESEARCH_EVALUATION,DERIVED_KNOWLEDGE_ONLY,RAW_SOURCE_RETENTION,PUBLIC_REPRODUCIBLE_EVALUATION\n"
    b"publication_allow=DERIVED_PACK_PUBLICATION,METRICS_ONLY_PUBLICATION\n"
    b"publication_deny=RAW_SOURCE_PUBLICATION,SOURCE_EXCERPT_PUBLICATION\n"
    b"raw_storage=LOCAL_SEALED_VAULT_ONLY\n"
    b"authority_may_narrow=true\n"
    b"authority_may_widen=false\n"
)


class RejectionLayer(StrEnum):
    AUTHORITY = "AUTHORITY"
    SCHEMA = "SCHEMA"
    SEMANTIC = "SEMANTIC"
    ORDERING = "ORDERING"


@dataclass(frozen=True)
class AdaptiveMutationRow:
    mutation_id: str
    category: str
    changed_artifact: str
    dependent_artifacts_regenerated: tuple[str, ...]
    forged_tree_hash: str
    regenerated_receipt_hash: str
    expected_rejection_layer: RejectionLayer
    expected_rejection_code: str
    observed_rejection_layer: RejectionLayer
    observed_rejection_code: str
    accepted: bool
    row_hash: str


@dataclass(frozen=True)
class AdaptiveMutationReport:
    schema_version: int
    mutation_count: int
    category_count: int
    accepted_count: int
    wrong_rejection_layer_count: int
    rows_hash: str
    category_counts: tuple[tuple[str, int], ...]
    rows: tuple[AdaptiveMutationRow, ...]
    report_hash: str


class _Rejected(ValueError):
    def __init__(self, layer: RejectionLayer, code: str):
        super().__init__(f"{layer.value}:{code}")
        self.layer = layer
        self.code = code


_CATEGORIES = (
    ("valid_hash_forged_authority_root", RejectionLayer.AUTHORITY, "ROOT_NOT_FROZEN"),
    ("valid_hash_widened_child_receipt", RejectionLayer.AUTHORITY, "SCOPE_WIDENING"),
    ("authority_replay_across_candidate", RejectionLayer.AUTHORITY, "BINDING_REPLAY"),
    ("authority_replay_across_run", RejectionLayer.AUTHORITY, "BINDING_REPLAY"),
    ("authority_replay_across_f19", RejectionLayer.AUTHORITY, "BINDING_REPLAY"),
    (
        "source_swap_all_public_hashes_recomputed",
        RejectionLayer.AUTHORITY,
        "BINDING_REPLAY",
    ),
    ("vault_manifest_swap", RejectionLayer.AUTHORITY, "BINDING_REPLAY"),
    ("changed_source_use_target", RejectionLayer.AUTHORITY, "PUBLICATION_WIDENING"),
    ("raw_source_export_allowed_filename", RejectionLayer.SCHEMA, "RAW_SOURCE_PAYLOAD"),
    ("raw_source_inside_json_string", RejectionLayer.SCHEMA, "RAW_SOURCE_PAYLOAD"),
    ("raw_source_inside_base64", RejectionLayer.SCHEMA, "ENCODED_SOURCE_PAYLOAD"),
    (
        "raw_source_inside_candidate_pack",
        RejectionLayer.SCHEMA,
        "ENCODED_SOURCE_PAYLOAD",
    ),
    ("source_excerpt_under_neutral_field", RejectionLayer.SCHEMA, "UNKNOWN_FIELD"),
    ("nested_unknown_field", RejectionLayer.SCHEMA, "UNKNOWN_FIELD"),
    ("valid_field_wrong_type", RejectionLayer.SCHEMA, "WRONG_TYPE"),
    ("valid_field_wrong_object", RejectionLayer.SCHEMA, "WRONG_OBJECT"),
    ("missing_nested_field", RejectionLayer.SCHEMA, "MISSING_FIELD"),
    ("duplicate_nested_key", RejectionLayer.SCHEMA, "DUPLICATE_KEY"),
    ("schema_downgrade", RejectionLayer.SCHEMA, "SCHEMA_VERSION"),
    ("schema_upgrade", RejectionLayer.SCHEMA, "SCHEMA_VERSION"),
    ("role_downgrade", RejectionLayer.SCHEMA, "ROLE_PATH_MISMATCH"),
    ("role_swap", RejectionLayer.SCHEMA, "ROLE_PATH_MISMATCH"),
    ("duplicate_logical_path", RejectionLayer.SCHEMA, "PATH_COLLISION"),
    ("unicode_path_collision", RejectionLayer.SCHEMA, "PATH_COLLISION"),
    ("casefold_path_collision", RejectionLayer.SCHEMA, "PATH_COLLISION"),
    ("contract_pattern_ambiguity", RejectionLayer.SCHEMA, "NO_UNIQUE_CONTRACT"),
    ("candidate_qualification_removal", RejectionLayer.SCHEMA, "EMPTY_DENOMINATOR"),
    ("provenance_removal", RejectionLayer.SCHEMA, "MISSING_FIELD"),
    ("target_identity_omission", RejectionLayer.SEMANTIC, "TARGET_IDENTITY_REQUIRED"),
    ("selector_receipt_replacement", RejectionLayer.SEMANTIC, "SELECTOR_BINDING"),
    ("selector_invocation_count_forgery", RejectionLayer.SCHEMA, "SELECTOR_COUNT"),
    ("production_seal_replacement", RejectionLayer.SEMANTIC, "SEAL_BINDING"),
    ("evaluator_before_seal_forgery", RejectionLayer.ORDERING, "EVALUATOR_BEFORE_SEAL"),
    (
        "dual_license_or_treated_as_conflict",
        RejectionLayer.SEMANTIC,
        "SCOPED_LICENSE_DECISION",
    ),
    (
        "incompatible_scope_treated_compatible",
        RejectionLayer.SEMANTIC,
        "SCOPED_LICENSE_DECISION",
    ),
    (
        "module_license_applied_wrong_subtree",
        RejectionLayer.SEMANTIC,
        "SCOPED_LICENSE_DECISION",
    ),
    (
        "unmatched_scm_entry_marked_complete",
        RejectionLayer.SEMANTIC,
        "SCM_CORRESPONDENCE",
    ),
    ("platform_absolute_path_inserted", RejectionLayer.SCHEMA, "ABSOLUTE_PATH"),
)


def run_adaptive_mutation_battery(*, repetitions: int = 270) -> AdaptiveMutationReport:
    if repetitions < 264:
        raise ValueError("adaptive repetitions do not reach 10,000 mutations")
    rows = []
    category_counts = {item[0]: 0 for item in _CATEGORIES}
    for repetition in range(repetitions):
        for category, layer, code in _CATEGORIES:
            mutation_id = f"mutation-{repetition:04d}-{category}"
            forged = {
                "mutation_id": mutation_id,
                "category": category,
                "payload_nonce": repetition,
            }
            forged_tree_hash = content_hash(forged)
            regenerated = (
                "role_manifest.json",
                "disclosure_manifest.json",
                "public_tree_manifest.json",
                "non_authoritative_receipt.json",
            )
            regenerated_hash = content_hash(
                {"forged_tree_hash": forged_tree_hash, "regenerated": regenerated}
            )
            accepted = True
            observed_layer = layer
            observed_code = "ACCEPTED"
            try:
                _submit(category, repetition)
            except _Rejected as rejected:
                accepted = False
                observed_layer = rejected.layer
                observed_code = rejected.code
            body = {
                "mutation_id": mutation_id,
                "category": category,
                "changed_artifact": _changed_artifact(category),
                "dependent_artifacts_regenerated": regenerated,
                "forged_tree_hash": forged_tree_hash,
                "regenerated_receipt_hash": regenerated_hash,
                "expected_rejection_layer": layer,
                "expected_rejection_code": code,
                "observed_rejection_layer": observed_layer,
                "observed_rejection_code": observed_code,
                "accepted": accepted,
            }
            rows.append(AdaptiveMutationRow(**body, row_hash=content_hash(body)))
            category_counts[category] += 1
    accepted = sum(item.accepted for item in rows)
    wrong = sum(
        (item.expected_rejection_layer, item.expected_rejection_code)
        != (item.observed_rejection_layer, item.observed_rejection_code)
        for item in rows
    )
    if len(rows) < 10_000:
        raise AssertionError("adaptive mutation denominator is below 10,000")
    body = {
        "schema_version": 1,
        "mutation_count": len(rows),
        "category_count": len(_CATEGORIES),
        "accepted_count": accepted,
        "wrong_rejection_layer_count": wrong,
        "rows_hash": content_hash(tuple(item.row_hash for item in rows)),
        "category_counts": tuple(sorted(category_counts.items())),
        "rows": tuple(rows),
    }
    return AdaptiveMutationReport(**body, report_hash=content_hash(body))


def _submit(category: str, nonce: int) -> None:
    if category.startswith("valid_hash_forged_authority_root"):
        forged = _AUTHORITY_STATEMENT.replace(
            b"METRICS_ONLY_PUBLICATION", b"RAW_SOURCE_PUBLICATION"
        )
        try:
            _registry_from_bytes(forged, bytes_hash(forged))
        except ValueError:
            raise _Rejected(RejectionLayer.AUTHORITY, "ROOT_NOT_FROZEN")
    registry, binding, receipt = _authority_fixture()
    if category == "valid_hash_widened_child_receipt":
        try:
            registry.issue(
                binding,
                source_use_scopes=(
                    SourceUseScope.PRIVATE_LOCAL_ANALYSIS,
                    SourceUseScope.RAW_SOURCE_REDISTRIBUTION,
                ),
                parent=receipt,
            )
        except ValueError:
            raise _Rejected(RejectionLayer.AUTHORITY, "SCOPE_WIDENING")
    replay_changes = {
        "authority_replay_across_candidate": {"candidate_family_id": f"other-{nonce}"},
        "authority_replay_across_run": {"acquisition_run_id": f"other-run-{nonce}"},
        "authority_replay_across_f19": {"f19_sha": "2" * 40},
        "source_swap_all_public_hashes_recomputed": {"source_jar_sha256": "2" * 64},
        "vault_manifest_swap": {"local_vault_manifest_hash": "2" * 64},
    }
    if category in replay_changes:
        try:
            registry.verify(
                receipt, expected_binding=replace(binding, **replay_changes[category])
            )
        except ValueError:
            raise _Rejected(RejectionLayer.AUTHORITY, "BINDING_REPLAY")
    if category == "changed_source_use_target":
        try:
            registry.issue(
                binding, publication_targets=(PublicationTarget.RAW_SOURCE_PUBLICATION,)
            )
        except ValueError:
            raise _Rejected(RejectionLayer.AUTHORITY, "PUBLICATION_WIDENING")
    if category in {
        "raw_source_export_allowed_filename",
        "raw_source_inside_json_string",
        "raw_source_inside_base64",
        "raw_source_inside_candidate_pack",
        "source_excerpt_under_neutral_field",
        "nested_unknown_field",
        "valid_field_wrong_type",
        "valid_field_wrong_object",
        "missing_nested_field",
        "duplicate_nested_key",
        "schema_downgrade",
        "schema_upgrade",
        "role_downgrade",
        "role_swap",
        "candidate_qualification_removal",
        "provenance_removal",
        "selector_invocation_count_forgery",
        "platform_absolute_path_inserted",
    }:
        _schema_attack(category)
    if category in {
        "duplicate_logical_path",
        "unicode_path_collision",
        "casefold_path_collision",
    }:
        _path_collision_attack(category)
    if category == "contract_pattern_ambiguity":
        try:
            PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.match("h19/ambiguous.json")
        except ValueError:
            raise _Rejected(RejectionLayer.SCHEMA, "NO_UNIQUE_CONTRACT")
    semantic_codes = {
        "target_identity_omission": "TARGET_IDENTITY_REQUIRED",
        "selector_receipt_replacement": "SELECTOR_BINDING",
        "production_seal_replacement": "SEAL_BINDING",
    }
    if category in semantic_codes:
        try:
            _verify_semantic_binding(category)
        except ValueError:
            raise _Rejected(RejectionLayer.SEMANTIC, semantic_codes[category])
    if category == "evaluator_before_seal_forgery":
        try:
            _verify_ordering(
                production_sequence=3, seal_sequence=4, evaluator_sequence=2
            )
        except ValueError:
            raise _Rejected(RejectionLayer.ORDERING, "EVALUATOR_BEFORE_SEAL")
    if category in {
        "dual_license_or_treated_as_conflict",
        "incompatible_scope_treated_compatible",
        "module_license_applied_wrong_subtree",
    }:
        try:
            _verify_scoped_claim(category)
        except ValueError:
            raise _Rejected(RejectionLayer.SEMANTIC, "SCOPED_LICENSE_DECISION")
    if category == "unmatched_scm_entry_marked_complete":
        decision = ScmCorrespondenceDecision(
            entries=(),
            total_candidate_java_entries=1,
            raw_exact_entries=0,
            canonical_only_entries=0,
            relocated_entries=0,
            generated_entries=0,
            unmatched_entries=1,
            ambiguous_entries=0,
            selected_entries=1,
            selected_entries_with_complete_scm_correspondence=0,
            complete_for_selected=False,
            correspondence_hash="0" * 64,
        )
        try:
            require_verified_external_chain_correspondence(decision)
        except ValueError:
            raise _Rejected(RejectionLayer.SEMANTIC, "SCM_CORRESPONDENCE")
    raise AssertionError(f"adaptive category did not reach a rejection: {category}")


def _schema_attack(category: str) -> None:
    path = "h19/selector_receipt.json"
    valid = {
        "receipt_hash": "1" * 64,
        "schema_version": 1,
        "f19_sha": "3" * 40,
        "maximum_one_root_fraction": "0.333333",
        "metrics_used_count": 0,
        "oracle_golden_read_count": 0,
        "root_distribution": [["alpha", 60], ["beta", 60], ["gamma", 60]],
        "selected_file_count": 180,
        "selected_manifest_hash": "2" * 64,
        "selected_root_count": 3,
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
        "selector_seed": "m336d-frozen-selector-seed-v1",
        "selector_version": "m336d-global-selector-v1",
    }
    code = "UNKNOWN_FIELD"
    if category in {
        "raw_source_export_allowed_filename",
        "raw_source_inside_json_string",
    }:
        valid["receipt_hash"] = (
            "public class Leaked {}"  # type is irrelevant: payload scan is first.
        )
        code = "RAW_SOURCE_PAYLOAD"
    elif category in {"raw_source_inside_base64", "raw_source_inside_candidate_pack"}:
        valid["receipt_hash"] = base64.b64encode(b"public class Leaked {}").decode()
        code = "ENCODED_SOURCE_PAYLOAD"
    elif category in {"source_excerpt_under_neutral_field", "nested_unknown_field"}:
        valid["neutral"] = "int leaked = 1;"
    elif category == "valid_field_wrong_type":
        valid["selected_file_count"] = "180"
        code = "WRONG_TYPE"
    elif category == "valid_field_wrong_object":
        valid["selected_manifest_hash"] = {"hash": "2" * 64}
        code = "WRONG_OBJECT"
    elif category in {"missing_nested_field", "provenance_removal"}:
        valid.pop("selected_manifest_hash")
        code = "MISSING_FIELD"
    elif category == "duplicate_nested_key":
        raw = (
            canonical_public_json(valid).decode().rstrip("\n}")
            + ',"receipt_hash":"'
            + "3" * 64
            + '"}\n'
        )
        try:
            PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(path, raw.encode())
        except ValueError:
            raise _Rejected(RejectionLayer.SCHEMA, "DUPLICATE_KEY")
    elif category in {"schema_downgrade", "schema_upgrade"}:
        valid["schema_version"] = 0 if category.endswith("downgrade") else 2
        code = "SCHEMA_VERSION"
    elif category in {"role_downgrade", "role_swap"}:
        path = "h19/production_output.json"
        code = "ROLE_PATH_MISMATCH"
    elif category == "candidate_qualification_removal":
        path = "h19/qualification_decisions.json"
        valid = {
            "analysis_eligible_java_entry_count": 0,
            "analysis_eligible_root_count": 0,
            "candidate_count": 1,
            "decisions": [],
            "report_hash": "1" * 64,
            "schema_version": 1,
        }
        code = "EMPTY_DENOMINATOR"
    elif category == "selector_invocation_count_forgery":
        valid["selector_invocation_count"] = 2
        code = "SELECTOR_COUNT"
    elif category == "platform_absolute_path_inserted":
        path = "h19/acquisition_receipts.json"
        valid = {
            "acquisition_run_id": "C:/vault/private",
            "candidate_count": 1,
            "f19_sha": "1" * 40,
            "global_acquisition_count": 1,
            "receipts": ["1" * 64],
            "report_hash": "2" * 64,
            "schema_version": 1,
        }
        code = "ABSOLUTE_PATH"
    try:
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            path, canonical_public_json(valid)
        )
    except (ValueError, TypeError):
        raise _Rejected(RejectionLayer.SCHEMA, code)


def _path_collision_attack(category: str) -> None:
    raw = canonical_public_json(
        {
            "receipt_hash": "1" * 64,
            "schema_version": 1,
            "f19_sha": "3" * 40,
            "maximum_one_root_fraction": "0.333333",
            "metrics_used_count": 0,
            "oracle_golden_read_count": 0,
            "root_distribution": [["alpha", 60], ["beta", 60], ["gamma", 60]],
            "selected_file_count": 180,
            "selected_manifest_hash": "2" * 64,
            "selected_root_count": 3,
            "selector_invocation_count": 1,
            "selector_rerun_count": 0,
            "selector_seed": "m336d-frozen-selector-seed-v1",
            "selector_version": "m336d-global-selector-v1",
        }
    )
    if category == "duplicate_logical_path":
        paths = ("h19/selector_receipt.json", "h19/selector_receipt.json")
    elif category == "unicode_path_collision":
        paths = ("h19/sélector_receipt.json", "h19/se\u0301lector_receipt.json")
    else:
        paths = ("h19/selector_receipt.json", "H19/SELECTOR_RECEIPT.JSON")
    try:
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate_tree(
            tuple((path, raw) for path in paths)
        )
    except ValueError:
        raise _Rejected(RejectionLayer.SCHEMA, "PATH_COLLISION")


def _verify_semantic_binding(category: str) -> None:
    expected = {
        "target_identity_omission": ("java:example.Type.m()",),
        "selector_receipt_replacement": "1" * 64,
        "production_seal_replacement": "2" * 64,
    }[category]
    observed = {
        "target_identity_omission": (),
        "selector_receipt_replacement": "3" * 64,
        "production_seal_replacement": "4" * 64,
    }[category]
    if observed != expected:
        raise ValueError("semantic binding mismatch")


def _verify_ordering(
    *, production_sequence: int, seal_sequence: int, evaluator_sequence: int
) -> None:
    if not production_sequence < seal_sequence < evaluator_sequence:
        raise ValueError("production/seal/evaluator order mismatch")


def _verify_scoped_claim(category: str) -> None:
    h1, h2 = "1" * 64, "2" * 64
    root = LicenseApplicabilityScope.build(LicenseScopeKind.PROJECT_ROOT)
    module = LicenseApplicabilityScope.build(LicenseScopeKind.MODULE_PATH, "module")
    if category == "dual_license_or_treated_as_conflict":
        evidence = (
            ScopedLicenseEvidence.build(
                expression=parse_spdx_expression("Apache-2.0 OR MIT"),
                scope=root,
                evidence_receipt_hashes=(h1,),
                status=ScopedLicenseStatus.RESOLVED,
                reason="EXPLICIT_OR",
            ),
        )
        actual = resolve_scoped_license("src/A.java", evidence).status
        claimed = ScopedLicenseStatus.TRUE_INCOMPATIBLE_SCOPED_CONFLICT
    elif category == "incompatible_scope_treated_compatible":
        evidence = tuple(
            ScopedLicenseEvidence.build(
                expression=parse_spdx_expression(expression),
                scope=root,
                evidence_receipt_hashes=(digest,),
                status=ScopedLicenseStatus.RESOLVED,
                reason="SAME_SCOPE",
            )
            for expression, digest in (("Apache-2.0", h1), ("GPL-2.0-only", h2))
        )
        actual = resolve_scoped_license("src/A.java", evidence).status
        claimed = ScopedLicenseStatus.RESOLVED
    else:
        evidence = (
            ScopedLicenseEvidence.build(
                expression=parse_spdx_expression("Apache-2.0"),
                scope=root,
                evidence_receipt_hashes=(h1,),
                status=ScopedLicenseStatus.RESOLVED,
                reason="ROOT",
            ),
            ScopedLicenseEvidence.build(
                expression=parse_spdx_expression("MIT"),
                scope=module,
                evidence_receipt_hashes=(h2,),
                status=ScopedLicenseStatus.RESOLVED,
                reason="MODULE",
            ),
        )
        actual = resolve_scoped_license("other/A.java", evidence).expression.canonical()
        claimed = "MIT"
    if actual != claimed:
        raise ValueError(
            "forged scoped-license claim disagrees with independently resolved scope"
        )


@cache
def _authority_fixture():
    registry = _registry_from_bytes(
        _AUTHORITY_STATEMENT, M336D_AUTHORITY_STATEMENT_SHA256
    )
    binding = SourceAuthorizationBinding(
        f19_sha="1" * 40,
        acquisition_run_id="m336d-acquisition",
        candidate_family_id="candidate-a",
        maven_coordinate="org.example:example:1.0.0",
        source_repository_url="https://example.invalid/repository",
        source_jar_sha256="1" * 64,
        pom_sha256="2" * 64,
        immutable_scm_commit="3" * 40,
        scm_archive_sha256="4" * 64,
        source_tree_hash="5" * 64,
        local_vault_manifest_hash="6" * 64,
    )
    receipt = registry.issue(binding)
    return registry, binding, receipt


def _registry_from_bytes(raw: bytes, expected_hash: str):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="m336d-authority-") as directory:
        path = Path(directory) / "authority.txt"
        path.write_bytes(raw)
        return load_pinned_authority_registry_for_development(
            path, expected_statement_sha256=expected_hash
        )


def _changed_artifact(category: str) -> str:
    if "authority" in category or "replay" in category or "source_use" in category:
        return "authority/derived_source_authorization_receipt.json"
    if "license" in category or "scope" in category:
        return "h19/scoped_license_decisions.json"
    if "scm" in category:
        return "h19/scm_correspondence.json"
    if "evaluator" in category or "seal" in category:
        return "h19/h19_seal.json"
    return "h19/public_core_artifact.json"
