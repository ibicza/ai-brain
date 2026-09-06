"""Source-free public Java pack and sealed-vault publication primitives.

The public commitment deliberately contains only content identities.  Source
bytes and host-local observations live behind explicit private roles and are
never accepted by public writers.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import json
import re
import stat
import unicodedata
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_identity import (
    CanonicalVaultPath,
    SourceEntryBinding,
    verify_source_entry_binding,
)
from ai_brain.stage3.acquisition.models import SourceMediaType
from ai_brain.stage3.acquisition.sources import _canonical_text

JAVA_PUBLIC_REPLAY_COMMITMENT_SCHEMA_VERSION = 1
JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME = "java_replay_commitment.json"
JAVA_PUBLIC_REPLAY_COMMITMENT_DEPENDENCY_PREFIX = "java-production-replay-commitment."
JAVA_PUBLIC_PACK_MANIFEST_SCHEMA_VERSION = 2
SEALED_JAVA_REPLAY_INPUT_SCHEMA_VERSION = 1

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_DRIVE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_WINDOWS_UNC = re.compile(r"(?:^|[\"'\s])\\\\(?!\?\\)[^\\\s]+\\[^\\\s]+")
_WINDOWS_EXTENDED = re.compile(r"(?:^|[\"'\s])\\\\\?\\")
_POSIX_KNOWN = re.compile(r"(?:^|[\"'\s])/(?:home|tmp|opt|mnt)(?:/|\Z)")
_FILE_URI = re.compile(r"(?i)file://")
_HOME_RELATIVE = re.compile(r"(?:^|[\"'\s])~[/\\]")
_PARENT_TRAVERSAL = re.compile(r"(?:^|[/\\])\.\.(?:[/\\]|\Z)")
_PATH_KEY = re.compile(
    r"(?i)(?:path|root|home|directory|executable|workspace|worktree|location)"
)
_PRIVATE_KEYS = frozenset(
    {
        "raw_source_blobs",
        "canonical_text_blobs",
        "source_blobs",
        "source_body",
        "source_bytes",
        "private_replay_manifest",
        "vault_relative_path",
        "private_jdk_observation",
    }
)
_PRIVATE_ROLE_NAMES = frozenset({"PRIVATE_SOURCE_INPUT", "PRIVATE_HOST_OBSERVATION"})
_SOURCE_MARKERS = (
    b"PK\x03\x04",
    b"public class ",
    b"public interface ",
    b"package java.",
)
_JAVA_EXCERPT = re.compile(
    r"(?m)(?:^|\n)\s*(?:package\s+[A-Za-z_$][\w.$]*\s*;|"
    r"import\s+(?:static\s+)?[A-Za-z_$][\w.$*]*\s*;|"
    r"(?:public|protected|private)\s+"
    r"(?:(?:static|final|abstract|sealed)\s+)*"
    r"(?:class|interface|enum|record)\s+[A-Za-z_$][\w$]*)"
)


class ArtifactConfidentialityRole(StrEnum):
    PUBLIC_DERIVED_PACK = "PUBLIC_DERIVED_PACK"
    PUBLIC_COMMITMENT = "PUBLIC_COMMITMENT"
    PUBLIC_SAFE_RECEIPT = "PUBLIC_SAFE_RECEIPT"
    PUBLIC_PLATFORM_TELEMETRY = "PUBLIC_PLATFORM_TELEMETRY"
    PRIVATE_SOURCE_INPUT = "PRIVATE_SOURCE_INPUT"
    PRIVATE_HOST_OBSERVATION = "PRIVATE_HOST_OBSERVATION"


PUBLIC_ROLES = frozenset(
    {
        ArtifactConfidentialityRole.PUBLIC_DERIVED_PACK,
        ArtifactConfidentialityRole.PUBLIC_COMMITMENT,
        ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT,
        ArtifactConfidentialityRole.PUBLIC_PLATFORM_TELEMETRY,
    }
)
PRIVATE_ROLES = frozenset(
    {
        ArtifactConfidentialityRole.PRIVATE_SOURCE_INPUT,
        ArtifactConfidentialityRole.PRIVATE_HOST_OBSERVATION,
    }
)


@dataclass(frozen=True)
class JavaPublicReplayContext:
    selected_source_manifest_hash: str
    source_entry_binding_manifest_hash: str
    document_manifest_hash: str
    aggregate_source_closure_manifest_hash: str
    source_count: int


@dataclass(frozen=True)
class JavaPublicReplayCommitment:
    schema_version: int
    contract_role: str
    deterministic_production_run_identity: str
    selected_source_manifest_hash: str
    source_entry_binding_manifest_hash: str
    document_manifest_hash: str
    source_count: int
    aggregate_source_closure_manifest_hash: str
    release_identity_hash: str
    parser_artifact_manifest_hash: str
    compiler_semantic_identity_hash: str
    compiler_policy_hash: str
    compiler_report_hash: str
    compilation_trust_gate_hash: str
    evidence_policy_hash: str
    field_evidence_manifest_hash: str
    proposal_manifest_hash: str
    trust_closure_hash: str
    expected_production_artifact_manifest_hash: str
    commitment_hash: str


@dataclass(frozen=True)
class SealedJavaReplayInputEntry:
    source_entry_identity_hash: str
    candidate_family_id: str
    vault_relative_path: str
    selected_relative_path: str
    raw_source_content_hash: str
    canonical_source_content_hash: str
    byte_length: int
    production_document_identity: str
    row_hash: str


@dataclass(frozen=True)
class SealedJavaReplayInputManifest:
    schema_version: int
    contract_role: str
    selected_source_manifest_hash: str
    source_entry_binding_manifest_hash: str
    compiler_semantic_identity_hash: str
    entries: tuple[SealedJavaReplayInputEntry, ...]
    source_count: int
    aggregate_source_closure_manifest_hash: str
    manifest_hash: str


@dataclass(frozen=True)
class JavaPublicCandidatePackVerificationReceipt:
    schema_version: int
    contract_role: str
    candidate_pack_content_hash: str
    candidate_pack_tree_hash: str
    replay_commitment_hash: str
    validated_entry_count: int
    unknown_entry_count: int
    source_bearing_entry_count: int
    private_role_entry_count: int
    absolute_path_count: int
    reversible_source_payload_count: int
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class PublicationBoundaryAudit:
    schema_version: int
    classified_artifact_count: int
    private_source_artifacts_in_public_roots: int
    private_host_artifacts_in_public_roots: int
    unknown_artifact_roles: int
    public_artifacts_without_contract: int
    audit_hash: str


@dataclass(frozen=True)
class PublicationBoundaryReceipt:
    schema_version: int
    contract_role: str
    audit_hash: str
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class JavaPublicPackEntryContract:
    entry_name: str
    media_type: str
    required: bool
    maximum_bytes: int
    contract_hash: str


@dataclass(frozen=True)
class JavaPublicPackEntryContractRegistry:
    schema_version: int
    contracts: tuple[JavaPublicPackEntryContract, ...]
    registry_hash: str


@dataclass(frozen=True)
class JavaPublicCandidatePackContract:
    schema_version: int
    allowed_entries: tuple[str, ...]
    required_entries: tuple[str, ...]
    optional_entries: tuple[str, ...]
    entry_contract_registry_hash: str
    contract_hash: str


@dataclass(frozen=True)
class JavaPublicPackContractValidation:
    schema_version: int
    contract_role: str
    candidate_pack_contract_hash: str
    entry_contract_registry_hash: str
    candidate_pack_integrity_receipt_hash: str
    public_producer_count: int
    covered_producer_count: int
    declared_producer_variant_count: int
    tested_producer_variant_count: int
    pack_entry_producer_count: int
    covered_pack_entry_producer_count: int
    declared_pack_entry_variant_count: int
    tested_pack_entry_variant_count: int
    unknown_candidate_pack_entry_count: int
    uncontracted_public_artifact_count: int
    uncontracted_produced_artifact_count: int
    contract_type_without_producer_or_legacy_count: int
    ambiguous_path_contract_count: int
    status: str
    report_hash: str


def _require_hash(value: str, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is not a SHA-256 identity")
    return value


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _canonical_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("relative identity must be non-empty POSIX text")
    if value != unicodedata.normalize("NFC", value):
        raise ValueError("relative identity must be NFC")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or parsed.as_posix() != value:
        raise ValueError("relative identity escapes its root")
    return value


def build_java_public_replay_context(
    *,
    batch,
    source_entry_bindings: tuple[SourceEntryBinding, ...] = (),
    selected_source_manifest_hash: str | None = None,
    source_entry_binding_manifest_hash: str | None = None,
) -> JavaPublicReplayContext:
    """Build a path-independent commitment context from verified identities."""

    documents = tuple(
        sorted(batch.bundle.documents, key=lambda item: item.relative_path)
    )
    if source_entry_bindings:
        by_selected = {}
        for binding in source_entry_bindings:
            verify_source_entry_binding(binding)
            if binding.selected_path in by_selected:
                raise ValueError(
                    "replay context contains a duplicate selected identity"
                )
            by_selected[binding.selected_path] = binding
        if set(by_selected) != {item.relative_path for item in documents}:
            raise ValueError("replay context source binding denominator mismatch")
        rows = tuple(
            (
                by_selected[item.relative_path].source_entry_id.identity_hash,
                by_selected[item.relative_path].source_entry_id.raw_source_sha256,
                by_selected[item.relative_path].source_entry_id.canonical_source_sha256,
                by_selected[item.relative_path].production_document_identity,
                content_hash(_canonical_relative(item.relative_path)),
            )
            for item in documents
        )
        derived_binding_hash = content_hash(
            tuple(item.binding_hash for item in source_entry_bindings)
        )
    else:
        rows = tuple(
            (
                content_hash(("source-entry", item.document_id)),
                item.bytes_hash,
                item.canonical_text_hash,
                item.document_id,
                content_hash(_canonical_relative(item.relative_path)),
            )
            for item in documents
        )
        derived_binding_hash = content_hash(rows)
    selected_hash = selected_source_manifest_hash or content_hash(
        tuple(row[0] for row in rows)
    )
    binding_hash = source_entry_binding_manifest_hash or derived_binding_hash
    _require_hash(selected_hash, "selected source manifest hash")
    _require_hash(binding_hash, "source-entry binding manifest hash")
    document_manifest_hash = content_hash(
        tuple((item.document_id, item.document_hash) for item in documents)
    )
    return JavaPublicReplayContext(
        selected_source_manifest_hash=selected_hash,
        source_entry_binding_manifest_hash=binding_hash,
        document_manifest_hash=document_manifest_hash,
        aggregate_source_closure_manifest_hash=content_hash(rows),
        source_count=len(rows),
    )


def build_java_public_replay_commitment(
    batch, context: JavaPublicReplayContext, expected_production_artifacts: dict
) -> JavaPublicReplayCommitment:
    for name, value in asdict(context).items():
        if name != "source_count":
            _require_hash(value, name)
    compiler_report = batch.compiler_report
    compilation_gate = batch.compilation_trust_gate
    compiler_identity = (
        compiler_report.compiler_identity_hash
        if compiler_report is not None
        else content_hash(("legacy-production", batch.release_identity.identity_hash))
    )
    compiler_policy = (
        content_hash(compiler_report.compiler_policy_version)
        if compiler_report is not None
        else content_hash("legacy-production-no-compiler-report")
    )
    body = {
        "schema_version": JAVA_PUBLIC_REPLAY_COMMITMENT_SCHEMA_VERSION,
        "contract_role": ArtifactConfidentialityRole.PUBLIC_COMMITMENT.value,
        "deterministic_production_run_identity": batch.closure.deterministic_run_id,
        "selected_source_manifest_hash": context.selected_source_manifest_hash,
        "source_entry_binding_manifest_hash": (
            context.source_entry_binding_manifest_hash
        ),
        "document_manifest_hash": context.document_manifest_hash,
        "source_count": context.source_count,
        "aggregate_source_closure_manifest_hash": (
            context.aggregate_source_closure_manifest_hash
        ),
        "release_identity_hash": batch.release_identity.identity_hash,
        "parser_artifact_manifest_hash": batch.parser_common_artifact.manifest_hash,
        "compiler_semantic_identity_hash": compiler_identity,
        "compiler_policy_hash": compiler_policy,
        "compiler_report_hash": (
            compiler_report.report_hash
            if compiler_report is not None
            else content_hash("legacy-production-no-compiler-report")
        ),
        "compilation_trust_gate_hash": (
            compilation_gate.gate_hash
            if compilation_gate is not None
            else content_hash("legacy-production-no-compilation-gate")
        ),
        "evidence_policy_hash": batch.evidence_policy.manifest_hash,
        "field_evidence_manifest_hash": batch.field_evidence.manifest_hash,
        "proposal_manifest_hash": batch.proposal_batch.proposal_manifest_hash,
        "trust_closure_hash": batch.closure.closure_hash,
        "expected_production_artifact_manifest_hash": content_hash(
            expected_production_artifacts
        ),
    }
    return JavaPublicReplayCommitment(**body, commitment_hash=content_hash(body))


def java_public_replay_commitment_from_dict(value: dict):
    if not isinstance(value, dict) or set(value) != set(
        JavaPublicReplayCommitment.__dataclass_fields__
    ):
        raise ValueError("public replay commitment schema changed")
    result = JavaPublicReplayCommitment(**value)
    body = asdict(result)
    claimed = body.pop("commitment_hash")
    if (
        result.schema_version != JAVA_PUBLIC_REPLAY_COMMITMENT_SCHEMA_VERSION
        or result.contract_role != ArtifactConfidentialityRole.PUBLIC_COMMITMENT.value
        or result.source_count <= 0
        or content_hash(body) != claimed
        or any(
            _SHA256.fullmatch(item) is None
            for name, item in body.items()
            if name.endswith("_hash")
        )
    ):
        raise ValueError("public replay commitment is invalid")
    _reject_private_payload(value)
    return result


def build_sealed_java_replay_input_manifest(
    *,
    bindings: tuple[SourceEntryBinding, ...],
    selected_paths: tuple[str, ...],
    vault_root: Path,
    selected_source_manifest_hash: str,
    source_entry_binding_manifest_hash: str,
    compiler_semantic_identity_hash: str,
) -> SealedJavaReplayInputManifest:
    """Create a portable private manifest containing identities, never source."""

    root = vault_root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink() or _is_reparse_point(root):
        raise ValueError("sealed replay vault root is unsafe")
    selected = tuple(_canonical_relative(item) for item in selected_paths)
    if len(selected) != len(set(selected)):
        raise ValueError("sealed replay selection contains duplicates")
    by_selected = {}
    for binding in bindings:
        verify_source_entry_binding(binding)
        if binding.selected_path in selected:
            by_selected[binding.selected_path] = binding
    if set(selected) != set(by_selected):
        raise ValueError("sealed replay binding denominator mismatch")
    entries = []
    aggregate_rows = []
    for selected_path in sorted(selected, key=lambda item: item.encode("utf-8")):
        binding = by_selected[selected_path]
        relative = CanonicalVaultPath.parse(binding.vault_path).canonical_posix_path
        path = root.joinpath(*relative.split("/"))
        resolved = path.resolve(strict=True)
        if (
            not resolved.is_file()
            or resolved.is_symlink()
            or _is_reparse_point(resolved)
            or not resolved.is_relative_to(root)
        ):
            raise ValueError("sealed replay source escapes the vault")
        raw = resolved.read_bytes()
        canonical = _canonical_text(raw, SourceMediaType.JAVA_SOURCE).encode("utf-8")
        identity = binding.source_entry_id
        if (
            bytes_hash(raw) != identity.raw_source_sha256
            or bytes_hash(canonical) != identity.canonical_source_sha256
        ):
            raise ValueError("sealed replay source identity mismatch")
        row_body = {
            "source_entry_identity_hash": identity.identity_hash,
            "candidate_family_id": identity.candidate_family_id,
            "vault_relative_path": relative,
            "selected_relative_path": selected_path,
            "raw_source_content_hash": identity.raw_source_sha256,
            "canonical_source_content_hash": identity.canonical_source_sha256,
            "byte_length": len(raw),
            "production_document_identity": binding.production_document_identity,
        }
        entries.append(
            SealedJavaReplayInputEntry(**row_body, row_hash=content_hash(row_body))
        )
        aggregate_rows.append(
            (
                identity.identity_hash,
                identity.raw_source_sha256,
                identity.canonical_source_sha256,
                binding.production_document_identity,
                content_hash(selected_path),
            )
        )
    body = {
        "schema_version": SEALED_JAVA_REPLAY_INPUT_SCHEMA_VERSION,
        "contract_role": ArtifactConfidentialityRole.PRIVATE_SOURCE_INPUT.value,
        "selected_source_manifest_hash": _require_hash(
            selected_source_manifest_hash, "selected source manifest hash"
        ),
        "source_entry_binding_manifest_hash": _require_hash(
            source_entry_binding_manifest_hash, "source-entry binding manifest hash"
        ),
        "compiler_semantic_identity_hash": _require_hash(
            compiler_semantic_identity_hash, "compiler semantic identity hash"
        ),
        "entries": tuple(entries),
        "source_count": len(entries),
        "aggregate_source_closure_manifest_hash": content_hash(tuple(aggregate_rows)),
    }
    return SealedJavaReplayInputManifest(**body, manifest_hash=content_hash(body))


def sealed_java_replay_input_manifest_from_dict(value: dict):
    if not isinstance(value, dict) or set(value) != set(
        SealedJavaReplayInputManifest.__dataclass_fields__
    ):
        raise ValueError("private replay manifest schema changed")
    if not isinstance(value["entries"], list | tuple):
        raise TypeError("private replay entries must be an array")
    entries = tuple(SealedJavaReplayInputEntry(**item) for item in value["entries"])
    result = SealedJavaReplayInputManifest(**{**value, "entries": entries})
    for entry in entries:
        body = asdict(entry)
        claimed = body.pop("row_hash")
        _canonical_relative(entry.vault_relative_path)
        _canonical_relative(entry.selected_relative_path)
        if content_hash(body) != claimed or entry.byte_length <= 0:
            raise ValueError("private replay input row is invalid")
    body = asdict(result)
    claimed = body.pop("manifest_hash")
    if (
        result.schema_version != SEALED_JAVA_REPLAY_INPUT_SCHEMA_VERSION
        or result.contract_role
        != ArtifactConfidentialityRole.PRIVATE_SOURCE_INPUT.value
        or result.source_count != len(entries)
        or len({item.source_entry_identity_hash for item in entries}) != len(entries)
        or len({item.selected_relative_path for item in entries}) != len(entries)
        or content_hash(body) != claimed
    ):
        raise ValueError("private replay input manifest is invalid")
    return result


class SealedJavaReplaySourceProvider:
    """Verify vault bytes before admitting them to an isolated replay store."""

    def __init__(self, vault_root: Path, manifest: SealedJavaReplayInputManifest):
        self.vault_root = vault_root.resolve(strict=True)
        self.manifest = sealed_java_replay_input_manifest_from_dict(
            json.loads(canonical_json(asdict(manifest)))
        )
        if (
            not self.vault_root.is_dir()
            or self.vault_root.is_symlink()
            or _is_reparse_point(self.vault_root)
        ):
            raise ValueError("sealed replay vault root is unsafe")

    def materialize_verified(self, target_root: Path, store) -> tuple[Path, ...]:
        target = target_root.resolve(strict=False)
        target.mkdir(parents=True, exist_ok=False)
        if target.is_symlink() or _is_reparse_point(target):
            raise ValueError("sealed replay target root is unsafe")
        verified = []
        for entry in self.manifest.entries:
            source = self.vault_root.joinpath(*entry.vault_relative_path.split("/"))
            resolved = source.resolve(strict=True)
            if (
                not resolved.is_file()
                or resolved.is_symlink()
                or _is_reparse_point(resolved)
                or not resolved.is_relative_to(self.vault_root)
            ):
                raise ValueError("sealed replay source escapes the vault")
            raw = resolved.read_bytes()
            canonical = _canonical_text(raw, SourceMediaType.JAVA_SOURCE).encode(
                "utf-8"
            )
            if (
                bytes_hash(raw) != entry.raw_source_content_hash
                or bytes_hash(canonical) != entry.canonical_source_content_hash
                or len(raw) != entry.byte_length
            ):
                raise ValueError("sealed replay source bytes differ from commitment")
            verified.append((entry, raw, canonical))
        paths = []
        for entry, raw, canonical in verified:
            store.put_blob(raw, expected_hash=entry.raw_source_content_hash)
            store.put_blob(canonical, expected_hash=entry.canonical_source_content_hash)
            destination = target.joinpath(*entry.selected_relative_path.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            paths.append(destination)
        return tuple(paths)


def assert_private_destination(
    destination: Path,
    *,
    git_worktrees: tuple[Path, ...] = (),
    public_roots: tuple[Path, ...] = (),
    installation_roots: tuple[Path, ...] = (),
) -> Path:
    """Fail closed if a private output could enter a public ancestry."""

    parent = destination.parent.resolve(strict=True)
    target = (parent / destination.name).resolve(strict=False)
    protected = (*git_worktrees, *public_roots, *installation_roots)
    for root in protected:
        known = root.resolve(strict=True)
        if target == known or target.is_relative_to(known):
            raise ValueError("private artifact destination is inside a protected root")
    if parent.is_symlink() or _is_reparse_point(parent):
        raise ValueError("private artifact destination ancestry is unsafe")
    return target


def write_sealed_java_replay_input_manifest(
    destination: Path,
    manifest: SealedJavaReplayInputManifest,
    *,
    git_worktrees: tuple[Path, ...] = (),
    public_roots: tuple[Path, ...] = (),
    installation_roots: tuple[Path, ...] = (),
) -> Path:
    target = assert_private_destination(
        destination,
        git_worktrees=git_worktrees,
        public_roots=public_roots,
        installation_roots=installation_roots,
    )
    sealed_java_replay_input_manifest_from_dict(
        json.loads(canonical_json(asdict(manifest)))
    )
    if target.exists():
        raise FileExistsError("private replay manifest destination exists")
    target.write_text(
        canonical_json(asdict(manifest)) + "\n", encoding="utf-8", newline="\n"
    )
    return target


def _entry_contract(name: str, media_type: str, required: bool, maximum_bytes: int):
    body = {
        "entry_name": name,
        "media_type": media_type,
        "required": required,
        "maximum_bytes": maximum_bytes,
    }
    return JavaPublicPackEntryContract(**body, contract_hash=content_hash(body))


JAVA_PUBLIC_PACK_ENTRY_CONTRACTS = (
    _entry_contract("manifest.json", "application/json", True, 4 * 1024 * 1024),
    _entry_contract("knowledge.jsonl", "application/x-ndjson", True, 64 * 1024 * 1024),
    _entry_contract("concept_graph.json", "application/json", True, 64 * 1024 * 1024),
    _entry_contract(
        "exercise_families.json", "application/json", True, 16 * 1024 * 1024
    ),
    _entry_contract(
        "capability_requirements.json", "application/json", True, 4 * 1024 * 1024
    ),
    _entry_contract("adapter_bindings.json", "application/json", True, 4 * 1024 * 1024),
    _entry_contract(
        "evaluation_manifest.json", "application/json", True, 4 * 1024 * 1024
    ),
    _entry_contract("source_bindings.json", "application/json", True, 64 * 1024 * 1024),
    _entry_contract(
        "alias_semantics.json", "application/json", False, 64 * 1024 * 1024
    ),
    _entry_contract("pack_manifest.json", "application/json", True, 4 * 1024 * 1024),
    _entry_contract(
        JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME,
        "application/json",
        True,
        4 * 1024 * 1024,
    ),
)
JAVA_PUBLIC_PACK_ENTRY_CONTRACT_REGISTRY_HASH = content_hash(
    JAVA_PUBLIC_PACK_ENTRY_CONTRACTS
)
JAVA_PUBLIC_PACK_ENTRY_CONTRACT_REGISTRY = JavaPublicPackEntryContractRegistry(
    schema_version=1,
    contracts=JAVA_PUBLIC_PACK_ENTRY_CONTRACTS,
    registry_hash=JAVA_PUBLIC_PACK_ENTRY_CONTRACT_REGISTRY_HASH,
)


def java_public_candidate_pack_contract() -> JavaPublicCandidatePackContract:
    allowed = tuple(item.entry_name for item in JAVA_PUBLIC_PACK_ENTRY_CONTRACTS)
    required = tuple(
        item.entry_name for item in JAVA_PUBLIC_PACK_ENTRY_CONTRACTS if item.required
    )
    optional = tuple(
        item.entry_name
        for item in JAVA_PUBLIC_PACK_ENTRY_CONTRACTS
        if not item.required
    )
    body = {
        "schema_version": 1,
        "allowed_entries": allowed,
        "required_entries": required,
        "optional_entries": optional,
        "entry_contract_registry_hash": JAVA_PUBLIC_PACK_ENTRY_CONTRACT_REGISTRY_HASH,
    }
    return JavaPublicCandidatePackContract(**body, contract_hash=content_hash(body))


def _strict_json_bytes(raw: bytes):
    if b"\r" in raw or not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise ValueError("public JSON must use exact UTF-8/LF framing")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("public JSON contains a duplicate key")
            result[key] = value
        return result

    value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=unique)
    if (canonical_json(value) + "\n").encode("utf-8") != raw:
        raise ValueError("public JSON is not canonical")
    return value


def public_path_count(value, *, key: str = "") -> int:
    if isinstance(value, dict):
        return sum(public_path_count(item, key=name) for name, item in value.items())
    if isinstance(value, list):
        return sum(public_path_count(item, key=key) for item in value)
    if not isinstance(value, str):
        return 0
    detected = bool(
        _WINDOWS_DRIVE.search(value)
        or _WINDOWS_UNC.search(value)
        or _WINDOWS_EXTENDED.search(value)
        or _POSIX_KNOWN.search(value)
        or _FILE_URI.search(value)
        or _HOME_RELATIVE.search(value)
        or _PARENT_TRAVERSAL.search(value)
    )
    if _PATH_KEY.search(key) and value.startswith("/") and not value.startswith("//"):
        detected = True
    return int(detected)


def _decoded_source_payload_count(value) -> int:
    pending = [value]
    count = 0
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str):
            compact = "".join(item.split())
            decoded = []
            if len(compact) >= 24 and len(compact) % 4 == 0:
                try:
                    decoded.append(base64.b64decode(compact, validate=True))
                except (ValueError, binascii.Error):
                    pass
            if len(compact) >= 32 and len(compact) % 2 == 0:
                try:
                    decoded.append(bytes.fromhex(compact))
                except ValueError:
                    pass
            count += int(any(_decoded_payload_is_forbidden(raw) for raw in decoded))
    return count


def _decoded_payload_is_forbidden(raw: bytes) -> bool:
    if any(marker in raw for marker in _SOURCE_MARKERS):
        return True
    if raw.startswith(b"\x1f\x8b"):
        try:
            gzip.decompress(raw)
        except (EOFError, OSError):
            return False
        return True
    return False


def _reject_private_payload(value) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if _PRIVATE_KEYS & {str(key).casefold() for key in item}:
                raise ValueError("public artifact contains a private source field")
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str):
            if item in _PRIVATE_ROLE_NAMES:
                raise ValueError("public artifact contains a private artifact role")
            if _JAVA_EXCERPT.search(item):
                raise ValueError("public artifact contains a Java source excerpt")
    if _decoded_source_payload_count(value):
        raise ValueError("public artifact contains a reversible source payload")
    if public_path_count(value):
        raise ValueError("public artifact contains a host-local filesystem path")


def _contract_by_name() -> dict[str, JavaPublicPackEntryContract]:
    return {item.entry_name: item for item in JAVA_PUBLIC_PACK_ENTRY_CONTRACTS}


def build_java_public_pack_manifest(root: Path, *, manifest) -> dict:
    contracts = _contract_by_name()
    names = {item.name for item in root.iterdir() if item.is_file()}
    if "pack_manifest.json" in names:
        raise ValueError("public pack manifest must be written exactly once")
    required = {name for name, item in contracts.items() if item.required}
    required.remove("pack_manifest.json")
    if required - names or names - set(contracts):
        raise ValueError("public candidate-pack entry set is not contract-closed")
    rows = tuple(
        (
            name,
            bytes_hash((root / name).read_bytes()),
            contracts[name].contract_hash,
        )
        for name in sorted(names, key=lambda item: item.encode("utf-8"))
    )
    commitment = java_public_replay_commitment_from_dict(
        _strict_json_bytes((root / JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME).read_bytes())
    )
    return {
        "schema_version": JAVA_PUBLIC_PACK_MANIFEST_SCHEMA_VERSION,
        "domain_id": manifest.domain_id,
        "pack_content_hash": manifest.pack_content_hash,
        "pack_version": manifest.pack_version,
        "entry_contract_registry_hash": (JAVA_PUBLIC_PACK_ENTRY_CONTRACT_REGISTRY_HASH),
        "entry_hashes": rows,
        "candidate_pack_tree_hash": content_hash(rows),
        "public_replay_commitment_hash": commitment.commitment_hash,
    }


def verify_java_public_candidate_pack(
    root: Path,
) -> JavaPublicCandidatePackVerificationReceipt:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink() or _is_reparse_point(resolved):
        raise ValueError("public candidate-pack root is unsafe")
    contracts = _contract_by_name()
    entries = tuple(resolved.iterdir())
    if any(
        item.is_symlink() or _is_reparse_point(item) or not item.is_file()
        for item in entries
    ):
        raise ValueError("public candidate pack contains a link or non-file entry")
    names = {item.name for item in entries}
    required = {name for name, item in contracts.items() if item.required}
    unknown = names - set(contracts)
    if required - names or unknown:
        raise ValueError("public candidate-pack entry set is not exact")
    private_roles = absolute_paths = reversible = source_entries = 0
    for path in entries:
        contract = contracts[path.name]
        raw = path.read_bytes()
        if len(raw) > contract.maximum_bytes:
            raise ValueError("public candidate-pack entry exceeds its size contract")
        values = []
        if contract.media_type == "application/json":
            values.append(_strict_json_bytes(raw))
        elif contract.media_type == "application/x-ndjson":
            if b"\r" in raw or (raw and not raw.endswith(b"\n")):
                raise ValueError("public JSONL must use exact UTF-8/LF framing")
            for line in raw.splitlines():
                value = json.loads(line.decode("utf-8", errors="strict"))
                if canonical_json(value).encode("utf-8") != line:
                    raise ValueError("public JSONL row is not canonical")
                values.append(value)
        for value in values:
            private_roles += _count_private_roles(value)
            absolute_paths += public_path_count(value)
            reversible += _decoded_source_payload_count(value)
            try:
                _reject_private_payload(value)
            except ValueError as error:
                if "source" in str(error).casefold():
                    source_entries += 1
                raise
    manifest = _strict_json_bytes((resolved / "pack_manifest.json").read_bytes())
    if set(manifest) != {
        "schema_version",
        "domain_id",
        "pack_content_hash",
        "pack_version",
        "entry_contract_registry_hash",
        "entry_hashes",
        "candidate_pack_tree_hash",
        "public_replay_commitment_hash",
    }:
        raise ValueError("public pack manifest schema changed")
    rows = tuple(tuple(item) for item in manifest["entry_hashes"])
    expected_names = names - {"pack_manifest.json"}
    if (
        manifest["schema_version"] != JAVA_PUBLIC_PACK_MANIFEST_SCHEMA_VERSION
        or manifest["entry_contract_registry_hash"]
        != JAVA_PUBLIC_PACK_ENTRY_CONTRACT_REGISTRY_HASH
        or {item[0] for item in rows} != expected_names
        or rows != tuple(sorted(rows, key=lambda item: item[0].encode("utf-8")))
        or any(
            len(item) != 3
            or bytes_hash((resolved / item[0]).read_bytes()) != item[1]
            or contracts[item[0]].contract_hash != item[2]
            for item in rows
        )
        or content_hash(rows) != manifest["candidate_pack_tree_hash"]
    ):
        raise ValueError("public pack manifest entry closure mismatch")
    commitment = java_public_replay_commitment_from_dict(
        _strict_json_bytes(
            (resolved / JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME).read_bytes()
        )
    )
    if manifest["public_replay_commitment_hash"] != commitment.commitment_hash:
        raise ValueError("public pack manifest binds another replay commitment")
    from ai_brain.stage3.domains.loader import load_pack

    pack = load_pack(resolved)
    if (
        pack.manifest.pack_content_hash != manifest["pack_content_hash"]
        or pack.manifest.domain_id != manifest["domain_id"]
        or pack.manifest.pack_version != manifest["pack_version"]
        or tuple(
            item
            for item in pack.manifest.dependency_packs
            if item.startswith(JAVA_PUBLIC_REPLAY_COMMITMENT_DEPENDENCY_PREFIX)
        )
        != (
            JAVA_PUBLIC_REPLAY_COMMITMENT_DEPENDENCY_PREFIX
            + commitment.commitment_hash,
        )
    ):
        raise ValueError("public pack does not bind its exact replay commitment")
    body = {
        "schema_version": 1,
        "contract_role": ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT.value,
        "candidate_pack_content_hash": pack.manifest.pack_content_hash,
        "candidate_pack_tree_hash": manifest["candidate_pack_tree_hash"],
        "replay_commitment_hash": commitment.commitment_hash,
        "validated_entry_count": len(entries),
        "unknown_entry_count": len(unknown),
        "source_bearing_entry_count": source_entries,
        "private_role_entry_count": private_roles,
        "absolute_path_count": absolute_paths,
        "reversible_source_payload_count": reversible,
        "status": "PASS",
    }
    return JavaPublicCandidatePackVerificationReceipt(
        **body, receipt_hash=content_hash(body)
    )


def run_java_public_pack_contract_validation(
    legacy_acquisition_value: dict,
    candidate_pack_root: Path,
) -> JavaPublicPackContractValidation:
    """Close the inherited producer gate and every internal pack entry."""

    from ai_brain.stage3.acquisition.m336f_contracts import (
        run_m336f_producer_contract_gate,
    )

    top_level = run_m336f_producer_contract_gate(legacy_acquisition_value)
    integrity = verify_java_public_candidate_pack(candidate_pack_root)
    candidate_contract = java_public_candidate_pack_contract()
    root = candidate_pack_root.resolve(strict=True)
    names = {
        item.name
        for item in root.iterdir()
        if item.is_file() and not item.is_symlink() and not _is_reparse_point(item)
    }
    contract_names = {
        item.entry_name for item in JAVA_PUBLIC_PACK_ENTRY_CONTRACT_REGISTRY.contracts
    }
    covered_entries = names & contract_names
    unknown_entries = names - contract_names
    uncontracted = contract_names - names - set(candidate_contract.optional_entries)
    pack_entry_producer_count = len(names)
    tested_pack_entry_variants = len(covered_entries)
    status = (
        "PASS"
        if top_level.status == "PASS"
        and top_level.public_producer_count == top_level.covered_producer_count
        and top_level.declared_producer_variant_count
        == top_level.tested_producer_variant_count
        and top_level.public_producer_count >= 14
        and top_level.declared_producer_variant_count >= 41
        and pack_entry_producer_count == len(covered_entries)
        and tested_pack_entry_variants == pack_entry_producer_count
        and not unknown_entries
        and not uncontracted
        else "FAIL"
    )
    body = {
        "schema_version": 1,
        "contract_role": ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT.value,
        "candidate_pack_contract_hash": candidate_contract.contract_hash,
        "entry_contract_registry_hash": JAVA_PUBLIC_PACK_ENTRY_CONTRACT_REGISTRY_HASH,
        "candidate_pack_integrity_receipt_hash": integrity.receipt_hash,
        "public_producer_count": top_level.public_producer_count,
        "covered_producer_count": top_level.covered_producer_count,
        "declared_producer_variant_count": top_level.declared_producer_variant_count,
        "tested_producer_variant_count": top_level.tested_producer_variant_count,
        "pack_entry_producer_count": pack_entry_producer_count,
        "covered_pack_entry_producer_count": len(covered_entries),
        "declared_pack_entry_variant_count": pack_entry_producer_count,
        "tested_pack_entry_variant_count": tested_pack_entry_variants,
        "unknown_candidate_pack_entry_count": len(unknown_entries),
        "uncontracted_public_artifact_count": len(uncontracted),
        "uncontracted_produced_artifact_count": (
            top_level.uncontracted_produced_artifact_count + len(uncontracted)
        ),
        "contract_type_without_producer_or_legacy_count": (
            top_level.contract_type_without_producer_or_legacy_count
        ),
        "ambiguous_path_contract_count": top_level.ambiguous_path_contract_count,
        "status": status,
    }
    return JavaPublicPackContractValidation(**body, report_hash=content_hash(body))


def _count_private_roles(value) -> int:
    pending = [value]
    count = 0
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key, nested in item.items():
                if (
                    key in {"contract_role", "artifact_role", "role"}
                    and isinstance(nested, str)
                    and nested in _PRIVATE_ROLE_NAMES
                ):
                    count += 1
                if isinstance(nested, (dict, list)):
                    pending.append(nested)
        elif isinstance(item, list):
            pending.extend(item)
    return count


def selected_source_entry_identities(value: dict) -> frozenset[str]:
    """Return semantic selection identity independent of manifest envelope."""

    identities = tuple(item["source_entry_identity_hash"] for item in value["files"])
    if len(identities) != len(set(identities)):
        raise ValueError("selected source manifest contains duplicate SourceEntryId")
    return frozenset(identities)


def public_artifact_inventory_identity(
    *, platform_role: str, root_role: str, relative_path: str, sha256: str
) -> str:
    """Identify one public artifact instance without serializing a host path."""

    if platform_role not in {"windows", "karina"}:
        raise ValueError("public artifact inventory has an unknown platform role")
    if root_role not in {"production", "evaluation"}:
        raise ValueError("public artifact inventory has an unknown root role")
    canonical = _canonical_relative(relative_path)
    _require_hash(sha256, "public artifact sha256")
    return content_hash((platform_role, root_role, canonical, sha256))


def audit_publication_boundary(
    classified_artifacts: tuple[tuple[str, ArtifactConfidentialityRole, bool], ...],
) -> tuple[PublicationBoundaryAudit, PublicationBoundaryReceipt]:
    """Audit `(identity, role, in_public_root)` rows without serializing paths."""

    if len({item[0] for item in classified_artifacts}) != len(classified_artifacts):
        raise ValueError("publication audit contains duplicate artifact identities")
    unknown = sum(
        not isinstance(role, ArtifactConfidentialityRole)
        for _identity, role, _public in classified_artifacts
    )
    private_source = sum(
        role is ArtifactConfidentialityRole.PRIVATE_SOURCE_INPUT and public
        for _identity, role, public in classified_artifacts
    )
    private_host = sum(
        role is ArtifactConfidentialityRole.PRIVATE_HOST_OBSERVATION and public
        for _identity, role, public in classified_artifacts
    )
    uncontracted = sum(
        role in PUBLIC_ROLES and not identity
        for identity, role, _public in classified_artifacts
    )
    body = {
        "schema_version": 1,
        "classified_artifact_count": len(classified_artifacts),
        "private_source_artifacts_in_public_roots": private_source,
        "private_host_artifacts_in_public_roots": private_host,
        "unknown_artifact_roles": unknown,
        "public_artifacts_without_contract": uncontracted,
    }
    audit = PublicationBoundaryAudit(**body, audit_hash=content_hash(body))
    status = (
        "PASS"
        if not (private_source + private_host + unknown + uncontracted)
        else "FAIL"
    )
    receipt_body = {
        "schema_version": 1,
        "contract_role": ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT.value,
        "audit_hash": audit.audit_hash,
        "status": status,
    }
    receipt = PublicationBoundaryReceipt(
        **receipt_body, receipt_hash=content_hash(receipt_body)
    )
    return audit, receipt
