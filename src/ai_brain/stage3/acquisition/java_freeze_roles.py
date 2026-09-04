"""Immutable role-aware disclosure policy for future Java freezes."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

FREEZE_ROLE_SCHEMA_VERSION = 2


class FinalArtifactRole(StrEnum):
    FINAL_SOURCE_BYTES = "FINAL_SOURCE_BYTES"
    FINAL_SOURCE_RECEIPT = "FINAL_SOURCE_RECEIPT"
    FINAL_SELECTOR_OUTPUT = "FINAL_SELECTOR_OUTPUT"
    FINAL_PHYSICAL_CENSUS = "FINAL_PHYSICAL_CENSUS"
    FINAL_PRODUCTION_OUTPUT = "FINAL_PRODUCTION_OUTPUT"
    FINAL_CANDIDATE_PACK = "FINAL_CANDIDATE_PACK"
    FINAL_ORACLE_OUTPUT = "FINAL_ORACLE_OUTPUT"
    FINAL_GOLDEN = "FINAL_GOLDEN"
    FINAL_EVALUATION = "FINAL_EVALUATION"
    FINAL_APPROVAL = "FINAL_APPROVAL"
    FINAL_INSTALLATION = "FINAL_INSTALLATION"
    FINAL_DECISION = "FINAL_DECISION"
    PROCESS_AUDIT = "PROCESS_AUDIT"
    QUALITY_LOG = "QUALITY_LOG"
    HUMAN_READABLE_REPORT = "HUMAN_READABLE_REPORT"
    REPORT = "REPORT"
    GENERIC_EMPTY_RESULT = "GENERIC_EMPTY_RESULT"


PROTECTED_FINAL_ROLES = frozenset(
    {
        FinalArtifactRole.FINAL_SOURCE_BYTES,
        FinalArtifactRole.FINAL_SOURCE_RECEIPT,
        FinalArtifactRole.FINAL_SELECTOR_OUTPUT,
        FinalArtifactRole.FINAL_PHYSICAL_CENSUS,
        FinalArtifactRole.FINAL_PRODUCTION_OUTPUT,
        FinalArtifactRole.FINAL_CANDIDATE_PACK,
        FinalArtifactRole.FINAL_ORACLE_OUTPUT,
        FinalArtifactRole.FINAL_GOLDEN,
        FinalArtifactRole.FINAL_EVALUATION,
        FinalArtifactRole.FINAL_APPROVAL,
        FinalArtifactRole.FINAL_INSTALLATION,
        FinalArtifactRole.FINAL_DECISION,
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
    derived_protected_token_count: int
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
    derived_tokens = derive_protected_disclosure_tokens(h_values, role_manifest)
    normalized_tokens = tuple(sorted({*derived_tokens, *protected_tokens}))
    f_text = b"\n".join(f_values.values()).decode("utf-8", errors="ignore")
    leaked_tokens = tuple(item for item in normalized_tokens if item and item in f_text)
    passed = not leaked_paths and not leaked_tokens
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
    value = _canonical_path(path)
    name = PurePosixPath(value).name
    if "/source_snapshots/" in f"/{value}" and name.endswith(".java"):
        return FinalArtifactRole.FINAL_SOURCE_BYTES
    if name in {"source_acquisition_receipts.json", "jdk_provider_receipt.json"}:
        return FinalArtifactRole.FINAL_SOURCE_RECEIPT
    if name in {"selector_receipt.json", "selection_execution.json"}:
        return FinalArtifactRole.FINAL_SELECTOR_OUTPUT
    if name == "physical_census.json":
        return FinalArtifactRole.FINAL_PHYSICAL_CENSUS
    if name in {
        "production_output.json",
        "production_counts.json",
        "component_manifest.json",
        "packability_report.json",
        "trust_closure.json",
        "candidate_replay.json",
        "platform_comparison.json",
        "production_summary.json",
    }:
        return FinalArtifactRole.FINAL_PRODUCTION_OUTPUT
    if "/candidate_pack/" in f"/{value}" or name in {
        "candidate_pack.json",
        "candidate_pack_tree.json",
    }:
        return FinalArtifactRole.FINAL_CANDIDATE_PACK
    if "/oracle/" in f"/{value}" and "golden" in name:
        return FinalArtifactRole.FINAL_GOLDEN
    if "/oracle/" in f"/{value}":
        return FinalArtifactRole.FINAL_ORACLE_OUTPUT
    if "/goldens/" in f"/{value}" or name.startswith("golden_"):
        return FinalArtifactRole.FINAL_GOLDEN
    if name.startswith(("evaluation", "metrics_")) or name in {
        "semantic_metrics.json",
        "trust_metrics.json",
        "source_overlap.json",
        "input.json",
        "role_manifest.json",
        "disclosure_report.json",
        "corpus_census.json",
        "diagnostic_metrics.json",
        "replay_mutations.json",
        "final_metrics.json",
        "final_gate.json",
    }:
        return FinalArtifactRole.FINAL_EVALUATION
    if name in {"approval.json", "release_approval.json"}:
        return FinalArtifactRole.FINAL_APPROVAL
    if "/installed_pack/" in f"/{value}" or name in {
        "installation.json",
        "runtime_proof.json",
    }:
        return FinalArtifactRole.FINAL_INSTALLATION
    if name in {"outcome.json", "blocked_result.json", "final_decision.json"}:
        return FinalArtifactRole.FINAL_DECISION
    if name in {"physical_census.json", "final_corpus_census.json"}:
        return FinalArtifactRole.FINAL_PHYSICAL_CENSUS
    if name in {"generic_empty_result.json", "empty_result.json"}:
        return FinalArtifactRole.GENERIC_EMPTY_RESULT
    if "audit" in name:
        return FinalArtifactRole.PROCESS_AUDIT
    if value.startswith("evaluation/m344_final_java/platform/") and name.endswith(
        ".json"
    ):
        return FinalArtifactRole.PROCESS_AUDIT
    if name.endswith((".log", ".txt")):
        return FinalArtifactRole.QUALITY_LOG
    if name.endswith(".md") and value.startswith(("docs/", "runs/")):
        return FinalArtifactRole.HUMAN_READABLE_REPORT
    raise ValueError(f"unknown final artifact role: {value}")


def derive_protected_disclosure_tokens(
    h_artifacts: dict[str, bytes], role_manifest: FinalArtifactRoleManifest
) -> tuple[str, ...]:
    """Derive release-sensitive values from protected H artifacts themselves."""

    roles = {item.relative_path: item.role for item in role_manifest.bindings}
    if set(roles) != {_canonical_path(path) for path in h_artifacts}:
        raise ValueError("role manifest does not cover protected token inputs")
    tokens = set()
    for path, raw in h_artifacts.items():
        canonical = _canonical_path(path)
        if roles[canonical] not in PROTECTED_FINAL_ROLES:
            continue
        tokens.add(bytes_hash(raw))
        try:
            value = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        _collect_disclosure_tokens(value, tokens)
    return tuple(sorted(tokens))


def _collect_disclosure_tokens(value, tokens: set[str], key: str = "") -> None:
    if isinstance(value, dict):
        for child_key, child in value.items():
            _collect_disclosure_tokens(child, tokens, str(child_key).casefold())
        return
    if isinstance(value, list):
        for child in value:
            _collect_disclosure_tokens(child, tokens, key)
        return
    if not isinstance(value, str):
        return
    sensitive_key = any(
        marker in key
        for marker in (
            "archive",
            "hash",
            "identity",
            "relative_path",
            "selected",
            "source_unit",
            "target_id",
            "tree",
        )
    )
    if (
        re.fullmatch(r"[0-9a-f]{64}", value)
        or value.startswith("java:")
        or (sensitive_key and (value.endswith(".java") or len(value) >= 16))
    ):
        tokens.add(value)


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
