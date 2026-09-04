"""Immutable role-aware disclosure policy for future Java freezes."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.final_artifact_contract import (
    FINAL_ARTIFACT_CONTRACT_REGISTRY,
    FinalArtifactRole,
)

FREEZE_ROLE_SCHEMA_VERSION = 2


PROTECTED_FINAL_ROLES = frozenset(
    FINAL_ARTIFACT_CONTRACT_REGISTRY.contract.protected_roles
)


@dataclass(frozen=True)
class FinalArtifactRoleBinding:
    relative_path: str
    role: FinalArtifactRole


@dataclass(frozen=True)
class FinalArtifactRoleManifest:
    schema_version: int
    bindings: tuple[FinalArtifactRoleBinding, ...]
    protected_roles: tuple[FinalArtifactRole, ...]
    manifest_hash: str


@dataclass(frozen=True)
class RoleAwareDisclosureReport:
    role_manifest_hash: str
    protected_artifact_count: int
    derived_protected_token_count: int
    neutral_reuse_count: int
    leaked_paths: tuple[str, ...]
    leaked_hashes: tuple[str, ...]
    leaked_tokens: tuple[str, ...]
    passed: bool
    report_hash: str


class DisclosureClaimKind(StrEnum):
    FINAL_ARCHIVE_HASH = "FINAL_ARCHIVE_HASH"
    FINAL_RAW_SOURCE_HASH = "FINAL_RAW_SOURCE_HASH"
    FINAL_CANONICAL_SOURCE_HASH = "FINAL_CANONICAL_SOURCE_HASH"
    FINAL_SELECTED_RELATIVE_PATH = "FINAL_SELECTED_RELATIVE_PATH"
    FINAL_SOURCE_TREE_HASH = "FINAL_SOURCE_TREE_HASH"
    FINAL_TARGET_IDENTITY = "FINAL_TARGET_IDENTITY"
    FINAL_PRODUCTION_OUTPUT_HASH = "FINAL_PRODUCTION_OUTPUT_HASH"
    FINAL_CANDIDATE_PACK_HASH = "FINAL_CANDIDATE_PACK_HASH"
    FINAL_ORACLE_HASH = "FINAL_ORACLE_HASH"
    FINAL_GOLDEN_HASH = "FINAL_GOLDEN_HASH"
    FINAL_EVALUATION_HASH = "FINAL_EVALUATION_HASH"
    FINAL_DECISION_HASH = "FINAL_DECISION_HASH"
    FINAL_POM_HASH = "FINAL_POM_HASH"
    FINAL_SCM_REVISION = "FINAL_SCM_REVISION"
    FINAL_SELECTOR_OUTPUT_HASH = "FINAL_SELECTOR_OUTPUT_HASH"
    FINAL_PROPOSAL_MANIFEST_HASH = "FINAL_PROPOSAL_MANIFEST_HASH"
    FINAL_TRUST_CLOSURE_HASH = "FINAL_TRUST_CLOSURE_HASH"


@dataclass(frozen=True)
class DisclosureClaim:
    claim_kind: DisclosureClaimKind
    source_artifact_role: FinalArtifactRole
    source_path: str
    field_path: str
    value: str
    value_hash: str
    secrecy_class: str
    predeclared: bool
    claim_hash: str


@dataclass(frozen=True)
class ProtectedRoleClaimReport:
    role: FinalArtifactRole
    protected_artifact_count: int
    required_claim_count: int
    extracted_claim_count: int
    missing_claim_count: int
    extra_claim_count: int
    report_hash: str


@dataclass(frozen=True)
class SchemaBoundDisclosureReport:
    role_reports: tuple[ProtectedRoleClaimReport, ...]
    required_claim_count: int
    extracted_claim_count: int
    missing_claim_count: int
    extra_claim_count: int
    passed: bool
    report_hash: str


def build_final_artifact_role_manifest(paths) -> FinalArtifactRoleManifest:
    raw_paths = tuple(paths)
    normalized_paths = tuple(_canonical_path(item) for item in raw_paths)
    if len(normalized_paths) != len(set(normalized_paths)):
        raise ValueError("normalized final artifact path duplicate")
    bindings = tuple(
        FinalArtifactRoleBinding(path, classify_final_artifact_role(path))
        for path in sorted(normalized_paths)
    )
    body = {
        "schema_version": FREEZE_ROLE_SCHEMA_VERSION,
        "bindings": bindings,
        "protected_roles": tuple(sorted(PROTECTED_FINAL_ROLES, key=str)),
    }
    return FinalArtifactRoleManifest(**body, manifest_hash=content_hash(body))


def dump_final_artifact_role_manifest(manifest: FinalArtifactRoleManifest) -> bytes:
    verify_final_artifact_role_manifest(manifest)
    return (canonical_json(asdict(manifest)) + "\n").encode("utf-8")


def load_final_artifact_role_manifest(raw: bytes | str) -> FinalArtifactRoleManifest:
    """Load canonical JSON into exact enums/tuples and reject duplicate keys."""

    encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
    try:
        value = json.loads(
            encoded.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed final artifact role manifest JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "bindings",
        "protected_roles",
        "manifest_hash",
    }:
        raise ValueError("invalid final artifact role manifest field set")
    if not isinstance(value["bindings"], list) or not isinstance(
        value["protected_roles"], list
    ):
        raise TypeError("role manifest arrays must be JSON arrays")
    bindings = []
    for row in value["bindings"]:
        if not isinstance(row, dict) or set(row) != {"relative_path", "role"}:
            raise ValueError("invalid role binding field set")
        if not isinstance(row["relative_path"], str) or not isinstance(
            row["role"], str
        ):
            raise TypeError("invalid role binding type")
        try:
            role = FinalArtifactRole(row["role"])
        except ValueError as exc:
            raise ValueError("unknown final artifact role") from exc
        bindings.append(
            FinalArtifactRoleBinding(_canonical_path(row["relative_path"]), role)
        )
    try:
        protected = tuple(FinalArtifactRole(item) for item in value["protected_roles"])
    except (TypeError, ValueError) as exc:
        raise ValueError("unknown protected final artifact role") from exc
    manifest = FinalArtifactRoleManifest(
        schema_version=value["schema_version"],
        bindings=tuple(bindings),
        protected_roles=protected,
        manifest_hash=value["manifest_hash"],
    )
    verify_final_artifact_role_manifest(manifest)
    if dump_final_artifact_role_manifest(manifest) != encoded:
        raise ValueError("role manifest JSON is not canonical and byte-identical")
    return manifest


def verify_final_artifact_role_manifest(
    manifest: FinalArtifactRoleManifest, h_artifacts=None
) -> None:
    if not isinstance(manifest, FinalArtifactRoleManifest):
        raise TypeError("role manifest must be typed")
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    paths = tuple(item.relative_path for item in manifest.bindings)
    expected_roles = tuple(sorted(PROTECTED_FINAL_ROLES, key=str))
    if (
        type(manifest.schema_version) is not int
        or manifest.schema_version != FREEZE_ROLE_SCHEMA_VERSION
        or not isinstance(claimed, str)
        or content_hash(body) != claimed
        or manifest.protected_roles != expected_roles
        or paths != tuple(sorted(paths))
        or len(paths) != len(set(paths))
        or any(
            item.role is not classify_final_artifact_role(item.relative_path)
            for item in manifest.bindings
        )
    ):
        raise ValueError("incomplete or weakened final artifact role manifest")
    if h_artifacts is not None:
        normalized = {_canonical_path(item) for item in h_artifacts}
        if set(paths) != normalized:
            raise ValueError("incomplete or weakened final artifact role manifest")


def verify_role_aware_disclosure(
    f_artifacts: dict[str, bytes],
    h_artifacts: dict[str, bytes],
    role_manifest: FinalArtifactRoleManifest,
    *,
    protected_tokens: tuple[str, ...] = (),
) -> RoleAwareDisclosureReport:
    """Reject pre-freeze knowledge, while permitting role-neutral byte reuse."""

    _verify_role_manifest(role_manifest, h_artifacts)
    f_values = {_canonical_path(path): value for path, value in f_artifacts.items()}
    h_values = {_canonical_path(path): value for path, value in h_artifacts.items()}
    roles = {item.relative_path: item.role for item in role_manifest.bindings}
    f_hashes = {bytes_hash(value) for value in f_values.values()}
    leaked_paths = []
    leaked_hashes = []
    neutral_reuse = 0
    for path, raw in h_values.items():
        digest = bytes_hash(raw)
        if digest not in f_hashes:
            continue
        if roles[path] in PROTECTED_FINAL_ROLES:
            leaked_paths.append(path)
            leaked_hashes.append(digest)
        else:
            neutral_reuse += 1
    contract_invalid = False
    try:
        claims = extract_disclosure_claims(h_values, role_manifest)
    except (TypeError, ValueError):
        claims = ()
        contract_invalid = True
    derived_tokens = tuple(
        sorted({item.value for item in claims if not item.predeclared})
    )
    normalized_tokens = tuple(sorted({*derived_tokens, *protected_tokens}))
    token_bytes = tuple(
        (item, item.encode("utf-8")) for item in normalized_tokens if item
    )
    leaked_tokens = tuple(
        item
        for item, encoded in token_bytes
        if any(encoded in raw for raw in f_values.values())
    )
    passed = not leaked_paths and not leaked_tokens and not contract_invalid
    body = {
        "role_manifest_hash": role_manifest.manifest_hash,
        "protected_artifact_count": sum(
            role in PROTECTED_FINAL_ROLES for role in roles.values()
        ),
        "derived_protected_token_count": len(derived_tokens),
        "neutral_reuse_count": neutral_reuse,
        "leaked_paths": tuple(sorted(leaked_paths)),
        "leaked_hashes": tuple(sorted(set(leaked_hashes))),
        "leaked_tokens": leaked_tokens,
        "passed": passed,
    }
    return RoleAwareDisclosureReport(**body, report_hash=content_hash(body))


def classify_final_artifact_role(path: str) -> FinalArtifactRole:
    canonical = _canonical_path(path)
    try:
        return FINAL_ARTIFACT_CONTRACT_REGISTRY.match(canonical).role
    except ValueError as exc:
        raise ValueError(f"unknown final artifact role: {canonical}") from exc


def derive_protected_disclosure_tokens(
    h_artifacts: dict[str, bytes], role_manifest: FinalArtifactRoleManifest
) -> tuple[str, ...]:
    """Derive release-sensitive values from protected H artifacts themselves."""

    return tuple(
        sorted(
            {
                item.value
                for item in extract_disclosure_claims(h_artifacts, role_manifest)
                if not item.predeclared
            }
        )
    )


def extract_disclosure_claims(
    h_artifacts: dict[str, bytes], role_manifest: FinalArtifactRoleManifest
) -> tuple[DisclosureClaim, ...]:
    """Extract secrets only from explicit role/field semantics."""

    verify_final_artifact_role_manifest(role_manifest, h_artifacts)
    roles = {item.relative_path: item.role for item in role_manifest.bindings}
    claims = []
    for raw_path, raw in sorted(h_artifacts.items()):
        path = _canonical_path(raw_path)
        role = roles[path]
        if role is FinalArtifactRole.FINAL_SOURCE_BYTES:
            claims.append(
                _claim(
                    DisclosureClaimKind.FINAL_RAW_SOURCE_HASH,
                    role,
                    path,
                    "$bytes",
                    bytes_hash(raw),
                )
            )
            claims.append(
                _claim(
                    DisclosureClaimKind.FINAL_CANONICAL_SOURCE_HASH,
                    role,
                    path,
                    "$canonical_bytes",
                    bytes_hash(_canonical_source_bytes(raw)),
                )
            )
            claims.append(
                _claim(
                    DisclosureClaimKind.FINAL_SELECTED_RELATIVE_PATH,
                    role,
                    path,
                    "$git_relative_path",
                    path,
                )
            )
            continue
        if role is FinalArtifactRole.FINAL_ACQUISITION_BYTES:
            claims.append(
                _claim(
                    DisclosureClaimKind.FINAL_ARCHIVE_HASH,
                    role,
                    path,
                    "$bytes",
                    bytes_hash(raw),
                )
            )
            continue
        if role not in PROTECTED_FINAL_ROLES:
            _verify_neutral_artifact_schema(path, raw)
            continue
        if role is FinalArtifactRole.FINAL_EVALUATION and path.endswith(
            "role_manifest.json"
        ):
            continue
        try:
            value = json.loads(
                raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"protected structured artifact is not strict JSON: {path}"
            ) from exc
        if not isinstance(value, dict):
            raise TypeError(f"protected structured artifact is not an object: {path}")
        claims.extend(_claims_for_role(role, path, value))
    return tuple(
        sorted(claims, key=lambda item: (item.source_path, item.field_path, item.value))
    )


def verify_disclosure_claim_set(
    h_artifacts: dict[str, bytes],
    role_manifest: FinalArtifactRoleManifest,
    claims: tuple[DisclosureClaim, ...],
) -> None:
    expected = extract_disclosure_claims(h_artifacts, role_manifest)
    for claim in claims:
        body = asdict(claim)
        claimed_hash = body.pop("claim_hash")
        if claim.predeclared or claim.secrecy_class != "FINAL_OBSERVED_VALUE":
            raise ValueError("derived final secret cannot be caller-marked predeclared")
        if content_hash(body) != claimed_hash:
            raise ValueError("disclosure claim hash mismatch")
    if claims != expected:
        raise ValueError("incomplete or caller-modified disclosure claim set")


def verify_schema_bound_disclosure(
    h_artifacts: dict[str, bytes],
    role_manifest: FinalArtifactRoleManifest,
) -> SchemaBoundDisclosureReport:
    """Recompute mandatory claim denominators for every protected role."""

    claims = extract_disclosure_claims(h_artifacts, role_manifest)
    roles = {item.relative_path: item.role for item in role_manifest.bindings}
    reports = []
    for role in sorted(PROTECTED_FINAL_ROLES, key=str):
        paths = tuple(path for path, item_role in roles.items() if item_role is role)
        role_claims = tuple(
            item for item in claims if item.source_artifact_role is role
        )
        observed_kinds = {item.claim_kind for item in role_claims}
        mandatory = {
            DisclosureClaimKind(item)
            for item in FINAL_ARTIFACT_CONTRACT_REGISTRY.required_claim_kinds(role)
        }
        missing_kinds = mandatory - observed_kinds if paths else set()
        extra_count = _unexpected_protected_field_count(h_artifacts, paths, role_claims)
        body = {
            "role": role,
            "protected_artifact_count": len(paths),
            "required_claim_count": len(role_claims) + len(missing_kinds),
            "extracted_claim_count": len(role_claims),
            "missing_claim_count": len(missing_kinds),
            "extra_claim_count": extra_count,
        }
        reports.append(ProtectedRoleClaimReport(**body, report_hash=content_hash(body)))
    required = sum(item.required_claim_count for item in reports)
    extracted = sum(item.extracted_claim_count for item in reports)
    missing = sum(item.missing_claim_count for item in reports)
    extra = sum(item.extra_claim_count for item in reports)
    body = {
        "role_reports": tuple(reports),
        "required_claim_count": required,
        "extracted_claim_count": extracted,
        "missing_claim_count": missing,
        "extra_claim_count": extra,
        "passed": required > 0 and missing == 0 and extra == 0,
    }
    return SchemaBoundDisclosureReport(**body, report_hash=content_hash(body))


def _claims_for_role(role, path, value) -> tuple[DisclosureClaim, ...]:
    raw = (canonical_json(value) + "\n").encode("utf-8")
    result = []
    for (
        kind,
        field_path,
        item,
    ) in FINAL_ARTIFACT_CONTRACT_REGISTRY.disclosure_claim_specs(path, raw):
        typed_kind = DisclosureClaimKind(kind)
        if _is_secret_value(typed_kind, item):
            result.append(_claim(typed_kind, role, path, field_path, item))
    return tuple(result)


def _claim(kind, role, source_path, field_path, value) -> DisclosureClaim:
    body = {
        "claim_kind": kind,
        "source_artifact_role": role,
        "source_path": source_path,
        "field_path": field_path,
        "value": value,
        "value_hash": bytes_hash(value.encode("utf-8")),
        "secrecy_class": "FINAL_OBSERVED_VALUE",
        "predeclared": False,
    }
    return DisclosureClaim(**body, claim_hash=content_hash(body))


def _is_secret_value(kind: DisclosureClaimKind, value: str) -> bool:
    if kind is DisclosureClaimKind.FINAL_SELECTED_RELATIVE_PATH:
        return value.endswith(".java")
    if kind is DisclosureClaimKind.FINAL_TARGET_IDENTITY:
        return value.startswith("java:")
    if kind is DisclosureClaimKind.FINAL_SCM_REVISION:
        return bool(re.fullmatch(r"[0-9a-f]{40}", value))
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _unexpected_protected_field_count(h_artifacts, paths, claims) -> int:
    count = 0
    for path in paths:
        try:
            validation = FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
                path, h_artifacts[path]
            )
        except (TypeError, ValueError):
            count += 1
            continue
        count += len(validation.unexpected_fields) + len(validation.unclassified_fields)
    return count


def _canonical_source_bytes(raw: bytes) -> bytes:
    text = raw.decode("utf-8-sig", errors="strict")
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return (text.rstrip() + "\n").encode("utf-8")


def _verify_neutral_artifact_schema(path: str, raw: bytes) -> None:
    if not path.endswith(".json"):
        return
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    secret_names = FINAL_ARTIFACT_CONTRACT_REGISTRY.disclosure_field_names()
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if set(item) & secret_names:
                raise ValueError(
                    f"protected structured fields placed under neutral role: {path}"
                )
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def _verify_role_manifest(manifest, h_artifacts) -> None:
    verify_final_artifact_role_manifest(manifest, h_artifacts)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical_path(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or "\\" in normalized:
        raise ValueError("non-canonical final artifact path")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe final artifact path")
    if path.as_posix() != normalized:
        raise ValueError("normalized final artifact path duplicate")
    return normalized
