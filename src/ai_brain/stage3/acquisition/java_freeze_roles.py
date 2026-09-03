"""Immutable role-aware disclosure policy for future Java freezes."""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

FREEZE_ROLE_SCHEMA_VERSION = 1


class FinalArtifactRole(StrEnum):
    FINAL_SOURCE_BYTES = "FINAL_SOURCE_BYTES"
    FINAL_SOURCE_RECEIPT = "FINAL_SOURCE_RECEIPT"
    FINAL_SELECTOR_OUTPUT = "FINAL_SELECTOR_OUTPUT"
    FINAL_PHYSICAL_CENSUS = "FINAL_PHYSICAL_CENSUS"
    FINAL_PRODUCTION_OUTPUT = "FINAL_PRODUCTION_OUTPUT"
    FINAL_ORACLE_OUTPUT = "FINAL_ORACLE_OUTPUT"
    FINAL_GOLDEN = "FINAL_GOLDEN"
    FINAL_EVALUATION = "FINAL_EVALUATION"
    PROCESS_AUDIT = "PROCESS_AUDIT"
    QUALITY_LOG = "QUALITY_LOG"
    REPORT = "REPORT"
    GENERIC_EMPTY_RESULT = "GENERIC_EMPTY_RESULT"


PROTECTED_FINAL_ROLES = frozenset(
    {
        FinalArtifactRole.FINAL_SOURCE_BYTES,
        FinalArtifactRole.FINAL_SOURCE_RECEIPT,
        FinalArtifactRole.FINAL_SELECTOR_OUTPUT,
        FinalArtifactRole.FINAL_PHYSICAL_CENSUS,
        FinalArtifactRole.FINAL_PRODUCTION_OUTPUT,
        FinalArtifactRole.FINAL_ORACLE_OUTPUT,
        FinalArtifactRole.FINAL_GOLDEN,
        FinalArtifactRole.FINAL_EVALUATION,
    }
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
    neutral_reuse_count: int
    leaked_paths: tuple[str, ...]
    leaked_hashes: tuple[str, ...]
    leaked_tokens: tuple[str, ...]
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
    normalized_tokens = tuple(sorted(set(protected_tokens)))
    f_text = b"\n".join(f_values.values()).decode("utf-8", errors="ignore")
    leaked_tokens = tuple(item for item in normalized_tokens if item and item in f_text)
    passed = not leaked_paths and not leaked_tokens
    body = {
        "role_manifest_hash": role_manifest.manifest_hash,
        "protected_artifact_count": sum(
            role in PROTECTED_FINAL_ROLES for role in roles.values()
        ),
        "neutral_reuse_count": neutral_reuse,
        "leaked_paths": tuple(sorted(leaked_paths)),
        "leaked_hashes": tuple(sorted(set(leaked_hashes))),
        "leaked_tokens": leaked_tokens,
        "passed": passed,
    }
    return RoleAwareDisclosureReport(**body, report_hash=content_hash(body))


def classify_final_artifact_role(path: str) -> FinalArtifactRole:
    value = _canonical_path(path)
    name = PurePosixPath(value).name
    if "/source_snapshots/" in f"/{value}":
        return FinalArtifactRole.FINAL_SOURCE_BYTES
    if name == "source_acquisition_receipts.json":
        return FinalArtifactRole.FINAL_SOURCE_RECEIPT
    if name == "selector_receipt.json":
        return FinalArtifactRole.FINAL_SELECTOR_OUTPUT
    if name == "physical_census.json":
        return FinalArtifactRole.FINAL_PHYSICAL_CENSUS
    if name in {"production_output.json", "production_counts.json"}:
        return FinalArtifactRole.FINAL_PRODUCTION_OUTPUT
    if "/oracle/" in f"/{value}" and "golden" in name:
        return FinalArtifactRole.FINAL_GOLDEN
    if "/oracle/" in f"/{value}":
        return FinalArtifactRole.FINAL_ORACLE_OUTPUT
    if name.startswith(("evaluation", "metrics_")) or name == "outcome.json":
        return FinalArtifactRole.FINAL_EVALUATION
    if "audit" in name:
        return FinalArtifactRole.PROCESS_AUDIT
    if name.endswith((".log", ".txt")):
        return FinalArtifactRole.QUALITY_LOG
    if name.endswith(".md"):
        return FinalArtifactRole.REPORT
    return FinalArtifactRole.REPORT


def _verify_role_manifest(manifest, h_artifacts) -> None:
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    expected = build_final_artifact_role_manifest(h_artifacts)
    paths = tuple(item.relative_path for item in manifest.bindings)
    if (
        manifest.schema_version != FREEZE_ROLE_SCHEMA_VERSION
        or content_hash(body) != claimed
        or manifest.protected_roles != tuple(sorted(PROTECTED_FINAL_ROLES, key=str))
        or paths != tuple(sorted(paths))
        or len(paths) != len(set(paths))
        or set(paths) != {_canonical_path(item) for item in h_artifacts}
        or manifest != expected
    ):
        raise ValueError("incomplete or weakened final artifact role manifest")


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
